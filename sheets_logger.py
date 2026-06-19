"""
Google Sheets job logging.
Fails gracefully — pipeline continues if Sheets is unavailable.
"""

import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()

SHEETS_ENABLED = False

try:
    import gspread
    from google.oauth2.service_account import Credentials

    SHEETS_ENABLED = True
except ImportError:
    print("Warning: gspread not installed — Google Sheets logging disabled.")

HEADER = [
    "job_id",
    "date_found",
    "job_title",
    "company",
    "location",
    "remote",
    "salary",
    "match_score",
    "score_reason",
    "status",
    "apply_url",
    "tailored_cv_url",
    "source",
    "user_email",
]

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_client():
    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not json_path or not os.path.exists(json_path):
        return None
    creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_sheet():
    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "")
    if not sheet_id:
        return None
    client = _get_client()
    if not client:
        return None
    spreadsheet = client.open_by_key(sheet_id)
    try:
        return spreadsheet.worksheet("Jobs")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title="Jobs", rows=1000, cols=len(HEADER))
        ws.append_row(HEADER, value_input_option="USER_ENTERED")
        return ws


def job_id_for(job: dict) -> str:
    if job.get("id") is not None:
        return str(job["id"])
    url = job.get("redirect_url", "")
    segment = url.rstrip("/").split("/")[-1].split("?")[0]
    return f"adzuna_{segment}" if segment else f"adzuna_{hash(url)}"


def _format_salary(job: dict) -> str:
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    if salary_min and salary_max:
        return f"£{int(salary_min):,}–£{int(salary_max):,}"
    if salary_min:
        return f"from £{int(salary_min):,}"
    if salary_max:
        return f"up to £{int(salary_max):,}"
    return "Not listed"


def _is_remote(job: dict) -> str:
    location = job.get("location", {}).get("display_name", "").lower()
    title = job.get("title", "").lower()
    found_via = job.get("_found_via", "").lower()
    if "remote" in location or "remote" in title or "remote" in found_via:
        return "yes"
    return "no"


def _job_to_row(job: dict, user_email: str | None) -> list:
    jid = job_id_for(job)
    url = job.get("redirect_url", "")
    apply_formula = f'=HYPERLINK("{url}","Apply")' if url else ""
    score = job.get("_score")
    return [
        jid,
        date.today().isoformat(),
        job.get("title", ""),
        job.get("company", {}).get("display_name", ""),
        job.get("location", {}).get("display_name", ""),
        _is_remote(job),
        _format_salary(job),
        score if score is not None else "",
        job.get("_score_reason", ""),
        "Not Applied",
        apply_formula,
        job.get("tailored_cv_url", ""),
        "adzuna",
        user_email or "cli",
    ]


def log_jobs_to_sheets(jobs, user_email=None):
    """Append new jobs to the Jobs tab. Returns stats dict, never raises."""
    if not SHEETS_ENABLED:
        return {"rows_added": 0, "duplicates_skipped": 0}

    try:
        ws = _get_sheet()
        if not ws:
            print("Google Sheets: missing GOOGLE_SHEETS_ID or service account JSON.")
            return {"rows_added": 0, "duplicates_skipped": 0}

        existing = ws.col_values(1)
        if not existing:
            ws.append_row(HEADER, value_input_option="USER_ENTERED")
            existing_ids = set()
        else:
            if existing[0] != "job_id":
                ws.insert_row(HEADER, index=1, value_input_option="USER_ENTERED")
            existing_ids = set(existing[1:])

        rows_to_add = []
        duplicates = 0

        for job in jobs:
            jid = job_id_for(job)
            if jid in existing_ids:
                duplicates += 1
                continue
            rows_to_add.append(_job_to_row(job, user_email))
            existing_ids.add(jid)

        if rows_to_add:
            ws.append_rows(rows_to_add, value_input_option="USER_ENTERED")

        return {"rows_added": len(rows_to_add), "duplicates_skipped": duplicates}

    except Exception as exc:
        print(f"Google Sheets logging error: {exc}")
        return {"rows_added": 0, "duplicates_skipped": 0}


def update_cv_urls(job_id_to_url: dict):
    """Update tailored_cv_url (column L) for matching job_ids. Never raises."""
    if not SHEETS_ENABLED or not job_id_to_url:
        return

    try:
        ws = _get_sheet()
        if not ws:
            return

        all_rows = ws.get_all_values()
        if not all_rows:
            return

        updates = []
        for row_idx, row in enumerate(all_rows[1:], start=2):
            if not row:
                continue
            jid = row[0]
            if jid in job_id_to_url:
                updates.append(
                    {
                        "range": f"L{row_idx}",
                        "values": [[job_id_to_url[jid]]],
                    }
                )

        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")

    except Exception as exc:
        print(f"Google Sheets CV URL update error: {exc}")
