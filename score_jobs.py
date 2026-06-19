"""
Score shortlisted jobs for profile fit using the DeepSeek API.
Phase 3, Step 7: returns a 0-10 relevance score and one-line reason per job.
"""

import json
import os
import re
import time

import requests
from dotenv import load_dotenv

from user_profile import UserProfile, load_profile

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_JOBS_TO_SCORE = 50
DESCRIPTION_LIMIT = 900
REQUEST_DELAY_SECONDS = 0.5

PROFILE_SUMMARY = load_profile().llm_summary()


def load_api_key():
    """Load DeepSeek API key from .env."""
    load_dotenv()
    return os.getenv("DEEPSEEK_API_KEY")


def _strip_html(text):
    """Remove HTML tags from job descriptions."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", clean).strip()


def _build_prompt(job, profile_summary: str):
    """Build the scoring prompt for one job."""
    title = job.get("title", "Unknown")
    company = job.get("company", {}).get("display_name", "Unknown")
    location = job.get("location", {}).get("display_name", "Unknown")
    description = _strip_html(job.get("description", ""))[:DESCRIPTION_LIMIT]

    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    if salary_min and salary_max:
        salary = f"£{int(salary_min):,} – £{int(salary_max):,}"
    elif salary_min:
        salary = f"from £{int(salary_min):,}"
    elif salary_max:
        salary = f"up to £{int(salary_max):,}"
    else:
        salary = "not listed"

    return f"""{profile_summary}

Job to score:
- Title: {title}
- Company: {company}
- Location: {location}
- Salary: {salary}
- Description: {description or "No description provided"}

Score how well this job fits the candidate (0 = irrelevant, 10 = excellent fit).
Return JSON only with this exact shape:
{{"score": <number 0-10>, "reason": "<one short sentence>", "summary": "<2-3 sentences>"}}

Also write a "summary" field: 2-3 short sentences in plain English describing what this role
actually involves day-to-day, written for someone quickly scrolling job listings on their phone.
Then state in one final sentence why it fits this candidate's background specifically.
No corporate jargon. No restating the job title. Write like you're texting a friend about a job
you found for them. Maximum 280 characters total for the summary field.

Keep "reason" as one short sentence for logging — do not remove or merge it with summary."""


def _parse_score_response(content):
    """Extract score, reason, and summary from the model response."""
    content = content.strip()

    def _extract(data):
        score = max(0, min(10, float(data["score"])))
        reason = str(data.get("reason", "")).strip() or "No reason given"
        summary = str(data.get("summary", "")).strip()
        return score, reason, summary

    try:
        return _extract(json.loads(content))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return _extract(json.loads(match.group()))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass

    return None, "Could not parse LLM response", ""


def score_job(job, api_key, profile_summary: str):
    """
    Score a single job. Returns (score, reason, summary).
    On failure, returns (None, error_message, "").
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a UK careers advisor. Reply with valid JSON only.",
            },
            {"role": "user", "content": _build_prompt(job, profile_summary)},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)

    if response.status_code == 401:
        return None, "Invalid DeepSeek API key", ""

    if not response.ok:
        return None, f"DeepSeek API error (HTTP {response.status_code})", ""

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError):
        return None, "Unexpected response from DeepSeek", ""

    return _parse_score_response(content)


def score_jobs(jobs, api_key=None, max_jobs=MAX_JOBS_TO_SCORE, profile: UserProfile | None = None):
    """
    Score up to max_jobs listings. Adds _score and _score_reason to each job.
    Returns jobs sorted by score (highest first). Unscored jobs go to the end.
    """
    api_key = api_key or load_api_key()
    profile_summary = profile.llm_summary() if profile else PROFILE_SUMMARY

    if not api_key:
        print("No DEEPSEEK_API_KEY in .env — skipping LLM scoring.")
        print("Get a free key at https://platform.deepseek.com/ and add it to .env\n")
        return jobs

    to_score = jobs[:max_jobs]
    print(f"Scoring {len(to_score)} jobs with DeepSeek...\n")

    for i, job in enumerate(to_score):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        title = job.get("title", "Untitled role")
        score, reason, summary = score_job(job, api_key, profile_summary)

        if score is None:
            print(f"  Failed to score '{title}': {reason}")
            job["_score"] = None
            job["_score_reason"] = reason
            job["_score_summary"] = ""
        else:
            job["_score"] = score
            job["_score_reason"] = reason
            job["_score_summary"] = summary
            print(f"  {score:.0f}/10 — {title}")

    scored = [j for j in to_score if j.get("_score") is not None]
    unscored = [j for j in to_score if j.get("_score") is None]
    remainder = jobs[max_jobs:]

    scored.sort(key=lambda j: j["_score"], reverse=True)
    return scored + unscored + remainder


if __name__ == "__main__":
    from dedupe import load_seen_ids, record_job_ids, split_new_jobs
    from filters import filter_jobs
    from search_jobs import fetch_all_jobs, format_salary, load_credentials

    app_id, app_key = load_credentials()
    all_jobs = fetch_all_jobs(app_id, app_key)

    seen_ids = load_seen_ids()
    new_jobs, skipped = split_new_jobs(all_jobs, seen_ids)
    print(f"Already seen: {skipped} jobs skipped\n")

    kept, _rejected = filter_jobs(new_jobs)
    if not kept:
        print("No new jobs to score.")
    else:
        ranked = score_jobs(kept)
        print()
        for job in ranked:
            score = job.get("_score")
            score_label = f"{score:.0f}/10" if score is not None else "n/a"
            print(f"[{score_label}] {job.get('title')}")
            print(f"  {job.get('_score_reason', '')}")
            print(f"  Salary: {format_salary(job)}")
            print(f"  URL: {job.get('redirect_url')}")
            print()

    record_job_ids(all_jobs)
