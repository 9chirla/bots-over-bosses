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
MAX_SAFE_LENGTH = 4000
MAX_JOBS_IN_DIGEST = 20
MAX_JOBS_PER_SPLIT = 5
MIN_SCORE_TO_SEND = 4
JOB_DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def load_telegram_config():
    """Load Telegram bot token and chat ID from .env."""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    return token, chat_id


def _sanitize_markdown(text: str) -> str:
    """Strip characters that break Telegram legacy Markdown in dynamic fields."""
    if not text:
        return ""
    return (
        text.replace("\\", "")
        .replace("*", "×")
        .replace("_", " ")
        .replace("`", "'")
        .replace("[", "(")
        .replace("]", ")")
    )


def format_salary(job):
    """Return a clean salary string for the digest."""
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")

    if salary_min is not None and salary_max is not None:
        min_val = int(salary_min)
        max_val = int(salary_max)
        if min_val == max_val:
            return f"£{min_val:,}"
        return f"£{min_val:,}–£{max_val:,}"
    if salary_min is not None:
        return f"from £{int(salary_min):,}"
    if salary_max is not None:
        return f"up to £{int(salary_max):,}"
    return "Salary not specified"


def _job_summary(job: dict) -> str:
    """Punchy 2-3 line summary from scoring; fall back to reason if missing."""
    summary = (job.get("_score_summary") or "").strip()
    if summary:
        return _sanitize_markdown(summary)
    reason = (job.get("_score_reason") or "").strip()
    if reason:
        return _sanitize_markdown(reason)
    return "No summary available for this role."


def _build_doc_links(job: dict) -> str | None:
    """Inline Markdown links for CV and cover letter; omit missing URLs."""
    parts = []
    cv_url = (job.get("tailored_cv_url") or "").strip()
    cl_url = (job.get("cover_letter_url") or "").strip()
    if cv_url:
        parts.append(f"📄 [Tailored CV]({cv_url})")
    if cl_url:
        parts.append(f"✉️ [Cover Letter]({cl_url})")
    return "  ·  ".join(parts) if parts else None


def format_job_block(job, index):
    """Format one job as a Telegram Markdown block."""
    title = _sanitize_markdown(job.get("title", "Untitled role"))
    company = _sanitize_markdown(
        job.get("company", {}).get("display_name", "Unknown company")
    )
    location = _sanitize_markdown(
        job.get("location", {}).get("display_name", "Unknown location")
    )
    salary = format_salary(job)
    apply_url = (job.get("redirect_url") or "").strip()
    score = job.get("_score")
    summary = _job_summary(job)

    if score is not None:
        header = f"*{index}. {title}*  `{int(score)}/10`"
    else:
        header = f"*{index}. {title}*"

    lines = [
        header,
        f"🏢 {company} · 📍 {location}",
        f"💰 {salary}",
        "",
        summary,
    ]

    doc_links = _build_doc_links(job)
    if doc_links:
        lines.extend(["", doc_links])

    if apply_url:
        if doc_links:
            lines.append(f"🔗 [View & Apply]({apply_url})")
        else:
            lines.extend(["", f"🔗 [View & Apply]({apply_url})"])

    lines.extend(["", JOB_DIVIDER])
    return "\n".join(lines)


def _digest_header(selected_count: int, digest_title: str | None, part: int | None, total_parts: int | None) -> str:
    """Build the digest header with optional (1/N) split indicator."""
    if digest_title:
        title_text = digest_title
    else:
        today = datetime.now().strftime("%d %b %Y")
        title_text = f"UK Jobs Digest — {today}"

    if part is not None and total_parts is not None and total_parts > 1:
        title_text = f"{title_text} ({part}/{total_parts})"

    match_line = f"{selected_count} match{'es' if selected_count != 1 else ''}"
    return f"🇬🇧 *{title_text}*\n{match_line}\n{JOB_DIVIDER}"


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


def _assemble_message(header: str, blocks: list[str]) -> str:
    """Join header and job blocks into one message string."""
    body = "\n\n".join(blocks)
    return f"{header}\n\n{body}" if blocks else header


def _chunk_blocks(blocks: list[str], header: str) -> list[list[str]]:
    """
    Split job blocks into message-sized chunks.
    Prefer max MAX_JOBS_PER_SPLIT jobs per message; shrink chunks if still too long.
    """
    if not blocks:
        return [[]]

    chunks: list[list[str]] = []
    current: list[str] = []

    for block in blocks:
        candidate_blocks = current + [block]
        if len(current) >= MAX_JOBS_PER_SPLIT or (
            current and len(_assemble_message(header, candidate_blocks)) > MAX_SAFE_LENGTH
        ):
            chunks.append(current)
            current = [block]
        else:
            current = candidate_blocks

    if current:
        chunks.append(current)

    # If any chunk still exceeds the limit, split down to single-job messages.
    final: list[list[str]] = []
    for chunk in chunks:
        if len(_assemble_message(header, chunk)) <= MAX_SAFE_LENGTH:
            final.append(chunk)
            continue
        for block in chunk:
            final.append([block])
    return final or [[]]


def build_digest_messages(jobs, empty_reason=None, digest_title=None, daily_top_n: bool = False):
    """
    Build one or more Telegram messages from a job list.
    Splits when length exceeds MAX_SAFE_LENGTH (max 5 jobs per message).
    """
    selected = select_jobs_for_digest(jobs, daily_top_n=daily_top_n)

    if not selected:
        if empty_reason:
            body = _sanitize_markdown(empty_reason)
        else:
            body = "No strong new matches today. Check again tomorrow."
        title = digest_title or f"UK Jobs — {datetime.now().strftime('%d %b %Y')}"
        return [f"🇬🇧 *{title}*\n\n{body}"]

    blocks = [format_job_block(job, i + 1) for i, job in enumerate(selected)]
    base_header = _digest_header(len(selected), digest_title, None, None)

    if len(_assemble_message(base_header, blocks)) <= MAX_SAFE_LENGTH:
        return [_assemble_message(base_header, blocks)]

    chunks = _chunk_blocks(blocks, base_header)
    total_parts = len(chunks)
    messages = []
    job_offset = 0

    for part_idx, chunk in enumerate(chunks, start=1):
        header = _digest_header(len(selected), digest_title, part_idx, total_parts)
        messages.append(_assemble_message(header, chunk))
        job_offset += len(chunk)

    return messages


def send_telegram_message(text, token, chat_id):
    """Send one message via the Telegram Bot API. Returns (ok, error_message)."""
    url = TELEGRAM_API_BASE.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
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
