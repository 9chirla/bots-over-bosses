"""
Format and send the daily job digest via Telegram.
Phase 4, Step 9: sends top matches to your phone using the Telegram Bot API.
"""

import os
import re
from datetime import datetime

import requests
from dotenv import load_dotenv

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LENGTH = 4096
MAX_JOBS_IN_DIGEST = 20
MIN_SCORE_TO_SEND = 4
JD_SNIPPET_MAX = 380
COMPANY_SNIPPET_MAX = 220


def _strip_html(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", clean).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}…"


def _job_description_snippet(job: dict) -> str:
    return _truncate(_strip_html(job.get("description", "")), JD_SNIPPET_MAX)


def _company_about_snippet(job: dict) -> str:
    company = job.get("company", {}).get("display_name", "Unknown company")
    description = _strip_html(job.get("description", ""))
    if not description:
        return company

    company_lower = company.lower()
    for sentence in re.split(r"(?<=[.!?])\s+", description):
        if company_lower in sentence.lower():
            return _truncate(sentence.strip(), COMPANY_SNIPPET_MAX)

    return _truncate(f"{company}. {description}", COMPANY_SNIPPET_MAX)


def load_telegram_config():
    """Load Telegram bot token and chat ID from .env."""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    return token, chat_id


def format_salary(job):
    """Return a short salary string for the digest."""
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")

    if salary_min and salary_max:
        return f"£{int(salary_min):,}–£{int(salary_max):,}"
    if salary_min:
        return f"from £{int(salary_min):,}"
    if salary_max:
        return f"up to £{int(salary_max):,}"
    return "Salary not listed"


def format_job_block(job, index):
    """Format one job as a plain-text block."""
    title = job.get("title", "Untitled role")
    company = job.get("company", {}).get("display_name", "Unknown company")
    location = job.get("location", {}).get("display_name", "Unknown location")
    salary = format_salary(job)
    url = job.get("redirect_url", "")
    score = job.get("_score")
    reason = job.get("_score_reason", "")

    if score is not None:
        header = f"{index}. [{score:.0f}/10] {title}"
    else:
        header = f"{index}. {title}"

    lines = [
        header,
        f"   {company} · {location} · {salary}",
    ]

    if reason:
        lines.append(f"   {reason}")

    about = _company_about_snippet(job)
    if about:
        lines.append(f"   About company: {about}")

    jd = _job_description_snippet(job)
    if jd:
        lines.append(f"   Role: {jd}")

    cv_url = job.get("tailored_cv_url", "")
    if cv_url:
        lines.append(f"   📄 Tailored CV: {cv_url}")
    elif job.get("_cv_telegram_sent"):
        lines.append("   📄 Tailored CV: see file above")

    cl_url = job.get("cover_letter_url", "")
    if cl_url:
        lines.append(f"   ✉️ Cover letter: {cl_url}")
    elif job.get("_cover_letter_telegram_sent"):
        lines.append("   ✉️ Cover letter: see file above")

    if url:
        lines.append(f"   {url}")

    return "\n".join(lines)


def select_jobs_for_digest(jobs, daily_top_n: bool = False):
    """Pick jobs for the digest. daily_top_n=True sends top-ranked jobs up to 20."""
    if daily_top_n and jobs:
        return jobs[:MAX_JOBS_IN_DIGEST]

    scored = [j for j in jobs if j.get("_score") is not None]
    unscored = [j for j in jobs if j.get("_score") is None]

    if scored:
        good = [j for j in scored if j["_score"] >= MIN_SCORE_TO_SEND]
        chosen = good if good else scored[:3]
    else:
        chosen = unscored

    return chosen[:MAX_JOBS_IN_DIGEST]


def build_digest_messages(jobs, empty_reason=None, digest_title=None, daily_top_n: bool = False):
    """
    Build one or more Telegram messages from a job list.
    Splits automatically if the text exceeds Telegram's 4096 character limit.
    """
    selected = select_jobs_for_digest(jobs, daily_top_n=daily_top_n)
    today = datetime.now().strftime("%d %b %Y")
    title = digest_title or f"UK Jobs Digest — {today}"

    if not selected:
        if empty_reason:
            body = empty_reason
        else:
            body = "No strong new matches today. Check again tomorrow."
        return [f"{title}\n\n{body}"]

    header = (
        f"{title}\n"
        f"{len(selected)} match{'es' if len(selected) != 1 else ''}\n"
    )

    blocks = [format_job_block(job, i + 1) for i, job in enumerate(selected)]
    body = "\n\n".join(blocks)
    full_text = header + "\n" + body

    if len(full_text) <= MAX_MESSAGE_LENGTH:
        return [full_text]

    messages = []
    current = header + "\n"
    index = 1

    for job in selected:
        block = format_job_block(job, index)
        candidate = current + ("\n\n" if current.strip() else "") + block

        if len(candidate) > MAX_MESSAGE_LENGTH:
            if current.strip():
                messages.append(current.rstrip())
            current = f"UK Jobs Digest (continued)\n\n{block}"
        else:
            current = candidate

        index += 1

    if current.strip():
        messages.append(current.rstrip())

    return messages


def send_telegram_message(text, token, chat_id):
    """Send one message via the Telegram Bot API. Returns (ok, error_message)."""
    url = TELEGRAM_API_BASE.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    response = requests.post(url, json=payload, timeout=30)

    if response.status_code == 401:
        return False, "Invalid Telegram bot token"

    if not response.ok:
        try:
            detail = response.json().get("description", response.text[:200])
        except ValueError:
            detail = response.text[:200]
        return False, f"Telegram error: {detail}"

    return True, None


def send_digest(jobs, token=None, chat_id=None, empty_reason=None, digest_title=None, daily_top_n: bool = False):
    """
    Format and send the job digest to Telegram.
    Returns True if sent successfully, False otherwise.
    """
    token = token or load_telegram_config()[0]
    chat_id = chat_id or load_telegram_config()[1]

    if not token or not chat_id:
        print("No TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env — skipping Telegram.")
        print("Setup: message @BotFather on Telegram, create a bot, add credentials to .env\n")
        return False

    messages = build_digest_messages(
        jobs, empty_reason=empty_reason, digest_title=digest_title, daily_top_n=daily_top_n
    )

    for i, message in enumerate(messages):
        ok, error = send_telegram_message(message, token, chat_id)
        if not ok:
            print(f"Failed to send Telegram message: {error}")
            return False
        if len(messages) > 1:
            print(f"Sent Telegram message {i + 1}/{len(messages)}")

    print(f"Digest sent to Telegram ({len(messages)} message{'s' if len(messages) != 1 else ''}).")
    return True


def send_cv_documents(jobs, token=None, chat_id=None):
    """Send tailored CV and cover letter .docx files via Telegram."""
    token = token or load_telegram_config()[0]
    chat_id = chat_id or load_telegram_config()[1]

    if not token or not chat_id:
        return 0

    sent = 0
    scored = [j for j in jobs if j.get("_score") is not None]
    scored.sort(key=lambda j: j["_score"], reverse=True)
    doc_url = TELEGRAM_API_BASE.replace("/sendMessage", "/sendDocument").format(token=token)

    for job in scored[:5]:
        title = job.get("title", "Role")
        company = job.get("company", {}).get("display_name", "Company")

        for path_key, sent_flag, label, needs_drive_skip in (
            ("_cv_local_path", "_cv_telegram_sent", "Tailored CV", "tailored_cv_url"),
            ("_cover_letter_local_path", "_cover_letter_telegram_sent", "Cover letter", "cover_letter_url"),
        ):
            if job.get(needs_drive_skip):
                continue
            local_path = job.get(path_key)
            if not local_path or not os.path.exists(local_path):
                continue

            try:
                with open(local_path, "rb") as doc_file:
                    response = requests.post(
                        doc_url,
                        data={"chat_id": chat_id, "caption": f"{label}: {title} at {company}"},
                        files={"document": doc_file},
                        timeout=60,
                    )
                if response.ok:
                    job[sent_flag] = True
                    sent += 1
                    print(f"  {label} sent via Telegram: {title}")
                else:
                    print(f"  Failed to send {label.lower()} for '{title}': {response.text[:200]}")
            except OSError as exc:
                print(f"  Could not read {label.lower()} for '{title}': {exc}")

    if sent:
        print(f"Sent {sent} application file(s) via Telegram.\n")

    return sent


if __name__ == "__main__":
    from main import run_pipeline

    run_pipeline()
