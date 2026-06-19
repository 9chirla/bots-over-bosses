"""
Fetch fresh UK job listings from Adzuna across analytics and full-stack tracks.
Phase 1, Step 2: fetch and print only — no filtering yet.
"""

import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

from user_profile import UserProfile

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

UK_TZ = ZoneInfo("Europe/London") if ZoneInfo else None

ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs/gb/search/1"

TRACK_A_QUERIES = [
    "data analyst",
    "business analyst",
    "reporting analyst",
    "engagement officer",
    "crm",
    "marketing coordinator",
]

TRACK_B_QUERIES = [
    "junior developer",
    "graduate developer",
    "full stack developer",
    "software developer",
    "web developer",
]

REQUEST_DELAY_SECONDS = 0.5


def load_credentials():
    """Load Adzuna API credentials from .env."""
    load_dotenv()
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        print("Missing Adzuna credentials.")
        print("Copy .env.example to .env and add your app_id and app_key from:")
        print("  https://developer.adzuna.com/")
        sys.exit(1)

    return app_id, app_key


def fetch_jobs(app_id, app_key, what, where=None):
    """Call Adzuna search API for one query."""
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": what,
        "max_days_old": 1,
        "results_per_page": 50,
        "content-type": "application/json",
    }
    if where:
        params["where"] = where

    response = requests.get(ADZUNA_BASE_URL, params=params, timeout=30)

    if response.status_code == 401:
        print("Adzuna rejected your credentials (401). Check ADZUNA_APP_ID and ADZUNA_APP_KEY in .env.")
        sys.exit(1)

    if not response.ok:
        print(f"Adzuna API error: HTTP {response.status_code}")
        print(response.text[:500])
        sys.exit(1)

    return response.json()


def format_salary(job):
    """Return a readable salary string or 'Not listed'."""
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")

    if salary_min and salary_max:
        return f"£{int(salary_min):,} – £{int(salary_max):,}"
    if salary_min:
        return f"£{int(salary_min):,}+"
    if salary_max:
        return f"Up to £{int(salary_max):,}"
    return "Not listed"


def run_search(app_id, app_key, query, track, location_label, what, where=None):
    """Run one search and return raw jobs plus metadata."""
    data = fetch_jobs(app_id, app_key, what=what, where=where)
    jobs = data.get("results", [])
    total_count = data.get("count", len(jobs))

    for job in jobs:
        job["_track"] = track
        job["_found_via"] = f'"{query}" / {location_label}'

    return jobs, total_count


def fetch_all_jobs(app_id, app_key, profile: UserProfile | None = None):
    """Run all Adzuna searches and return deduplicated jobs."""
    track_a = TRACK_A_QUERIES
    track_b = TRACK_B_QUERIES
    location = "London"

    if profile:
        track_a, track_b = profile.search_queries()
        location = profile.location or "London"

    raw_count = 0
    seen_ids = set()
    unique_jobs = []

    search_plan = []
    for query in track_a:
        search_plan.append((query, "Track A", "London", query, location))
        if not profile or profile.remote_ok:
            search_plan.append((query, "Track A", "Remote", f"remote {query}", None))
    for query in track_b:
        search_plan.append((query, "Track B", "London", query, location))
        if not profile or profile.remote_ok:
            search_plan.append((query, "Track B", "Remote", f"remote {query}", None))

    print(f"Running {len(search_plan)} Adzuna searches (jobs posted in last 24 hours)...")

    for i, (query, track, location_label, what, where) in enumerate(search_plan):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        jobs, _total_count = run_search(app_id, app_key, query, track, location_label, what, where)
        raw_count += len(jobs)

        for job in jobs:
            job_id = job.get("id")
            if job_id is None or job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            unique_jobs.append(job)

    print(f"Fetched {len(unique_jobs)} unique jobs ({raw_count} raw before dedupe)\n")
    return unique_jobs


def filter_jobs_posted_today(jobs):
    """Keep only jobs whose Adzuna created date falls on today's calendar date (UK)."""
    if UK_TZ:
        today = datetime.now(UK_TZ).date()
    else:
        today = datetime.now().date()

    kept = []
    for job in jobs:
        created = job.get("created")
        if not created:
            kept.append(job)
            continue
        try:
            job_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if UK_TZ:
                job_date = job_date.astimezone(UK_TZ)
            if job_date.date() == today:
                kept.append(job)
        except ValueError:
            kept.append(job)

    return kept


def main():
    from main import run_pipeline

    run_pipeline()


if __name__ == "__main__":
    main()
