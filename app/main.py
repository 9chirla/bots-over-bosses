"""FastAPI web app — onboarding + dashboard + Telegram connect + daily cron."""

from pathlib import Path

import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from app import config, database
from pipeline import run_pipeline
from user_profile import UserProfile

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="UK Job Search Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_bot_username: str | None = None


def get_bot_username() -> str:
    global _bot_username
    if _bot_username:
        return _bot_username
    token = config.telegram_bot_token()
    if not token:
        return "your_bot"
    response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
    if response.ok:
        _bot_username = response.json()["result"]["username"]
        return _bot_username
    return "your_bot"


class SignupRequest(BaseModel):
    email: EmailStr
    location: str = "London"
    remote_ok: bool = True
    salary_min: int = Field(24000, ge=15000, le=100000)
    salary_max: int = Field(35000, ge=15000, le=150000)
    education: str = ""
    skills: str = "Power BI, Excel, CRM, Python, JavaScript, SQL"
    target_titles: str = "Data Analyst, Business Analyst, Junior Developer, Full Stack Developer"
    include_track_b: bool = True


class TelegramUpdate(BaseModel):
    update_id: int | None = None
    message: dict | None = None


class LoginRequest(BaseModel):
    email: EmailStr


class ProfileUpdateRequest(BaseModel):
    location: str = "London"
    remote_ok: bool = True
    salary_min: int = Field(24000, ge=15000, le=100000)
    salary_max: int = Field(35000, ge=15000, le=150000)
    education: str = ""
    skills: str = "Power BI, Excel, CRM, Python, JavaScript, SQL"
    target_titles: str = "Data Analyst, Business Analyst, Junior Developer, Full Stack Developer"
    include_track_b: bool = True


def _profile_from_form(email: str, body: SignupRequest | ProfileUpdateRequest) -> UserProfile:
    return UserProfile(
        email=email,
        location=body.location.strip(),
        remote_ok=body.remote_ok,
        salary_min=body.salary_min,
        salary_max=body.salary_max,
        education=body.education.strip(),
        skills=[s.strip() for s in body.skills.split(",") if s.strip()],
        target_titles=[t.strip() for t in body.target_titles.split(",") if t.strip()],
        include_track_b=body.include_track_b,
    )


@app.on_event("startup")
def startup():
    database.init_db()


@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(WEB_DIR / "dashboard.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/bot-info")
def bot_info():
    return {"bot_username": get_bot_username()}


@app.post("/api/signup")
def signup(body: SignupRequest):
    if body.salary_min > body.salary_max:
        raise HTTPException(400, "Minimum salary cannot be higher than maximum salary.")

    existing_id = database.get_user_by_email(body.email)
    profile = _profile_from_form(body.email, body)

    if existing_id:
        database.update_user_profile(existing_id, profile)
        user_id = existing_id
        created = False
    else:
        user_id = database.create_user(body.email, profile)
        created = True

    bot_username = get_bot_username()
    telegram_link = f"https://t.me/{bot_username}?start={user_id}"

    return {
        "user_id": user_id,
        "created": created,
        "telegram_link": telegram_link,
        "message": "Sign up saved. Connect Telegram to start receiving daily digests.",
    }


@app.post("/api/login")
def login(body: LoginRequest):
    user_id = database.get_user_by_email(body.email)
    if not user_id:
        raise HTTPException(404, "No account found for that email. Please sign up first.")
    return {"user_id": user_id}


@app.get("/api/users/{user_id}/profile")
def get_profile(user_id: str):
    profile = database.profile_to_api(user_id)
    if not profile:
        raise HTTPException(404, "User not found")
    status = database.user_status(user_id)
    status["telegram_link"] = f"https://t.me/{get_bot_username()}?start={user_id}"
    return {"profile": profile, "status": status}


@app.put("/api/users/{user_id}/profile")
def update_profile(user_id: str, body: ProfileUpdateRequest):
    if body.salary_min > body.salary_max:
        raise HTTPException(400, "Minimum salary cannot be higher than maximum salary.")

    status = database.user_status(user_id)
    if not status.get("found"):
        raise HTTPException(404, "User not found")

    profile = _profile_from_form(status["email"], body)
    database.update_user_profile(user_id, profile)
    return {"ok": True, "message": "Profile updated."}


@app.get("/api/users/{user_id}/digests")
def digest_history(user_id: str):
    if not database.user_status(user_id).get("found"):
        raise HTTPException(404, "User not found")
    return {"digests": database.get_digest_history(user_id, limit=7)}


@app.get("/api/users/{user_id}/status")
def user_status(user_id: str):
    status = database.user_status(user_id)
    if not status.get("found"):
        raise HTTPException(404, "User not found")
    status["bot_username"] = get_bot_username()
    status["telegram_link"] = f"https://t.me/{get_bot_username()}?start={user_id}"
    return status


@app.post("/api/telegram/webhook")
def telegram_webhook(update: TelegramUpdate):
    message = update.message or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not chat_id or not text.startswith("/start"):
        return {"ok": True}

    parts = text.split(maxsplit=1)
    user_id = parts[1].strip() if len(parts) > 1 else None

    if user_id and database.link_telegram(user_id, str(chat_id)):
        token = config.telegram_bot_token()
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": (
                    "You're connected! You'll receive a daily UK job digest each morning. "
                    "Your preferences are saved."
                ),
            },
            timeout=10,
        )
    elif user_id:
        requests.post(
            f"https://api.telegram.org/bot{config.telegram_bot_token()}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "That sign-up link is invalid. Please sign up again on the website.",
            },
            timeout=10,
        )

    return {"ok": True}


@app.post("/api/cron/run-all")
def cron_run_all(x_cron_secret: str | None = Header(default=None)):
    expected = config.cron_secret()
    if not expected or x_cron_secret != expected:
        raise HTTPException(401, "Invalid cron secret")

    users = database.list_active_users_with_telegram()
    results = []

    for user in users:
        profile = database.get_user_profile(user["id"])
        if not profile:
            continue
        summary = run_pipeline(
            profile=profile,
            user_id=user["id"],
            user_email=user["email"],
            telegram_chat_id=user["chat_id"],
            send_telegram=True,
            print_jobs=False,
            use_db_dedupe=True,
        )
        database.log_digest(user["id"], summary.get("sent", 0), "daily")
        results.append({"user_id": user["id"], "email": user["email"], **summary})

    return {"users_processed": len(results), "results": results}


@app.post("/api/users/{user_id}/run-now")
def run_now(user_id: str):
    profile = database.get_user_profile(user_id)
    if not profile:
        raise HTTPException(404, "User not found")
    chat_id = database.get_telegram_chat_id(user_id)
    if not chat_id:
        raise HTTPException(400, "Telegram not connected yet")

    summary = run_pipeline(
        profile=profile,
        user_id=user_id,
        user_email=profile.email,
        telegram_chat_id=chat_id,
        send_telegram=True,
        print_jobs=False,
        use_db_dedupe=True,
    )
    database.log_digest(user_id, summary.get("sent", 0), "daily")
    return summary
