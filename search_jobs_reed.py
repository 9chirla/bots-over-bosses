"""
Fetch UK job listings from Reed.co.uk API.
Parallel source to Adzuna — returns jobs normalised to the same dict shape.
"""

import os
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

REED_SEARCH_URL = "https://www.reed.co.uk/api/1.0/search"
REQUEST_DELAY_SECONDS = 0.5


def _reed_date_to_iso(date_str: str) -> str:
    """Convert Reed dd/mm/yyyy dates to ISO for filter_jobs_posted_today."""
    if not date_str:
        return ""
    try:
        parsed = datetime.strptime(date_str.strip(), "%d/%m/%Y")
        return parsed.strftime("%Y-%m-%dT00:00:00")
    except (ValueError, TypeError):
        return date_str


def _normalise_reed_job(raw: dict, *, track: str, found_via: str) -> dict:
    """
    Map Reed API fields to the Adzuna-compatible shape used by filters,
    score_jobs, send_digest, and sheets_logger.
    """
    salary_min = raw.get("minimumSalary")
    salary_max = raw.get("maximumSalary")
    description = raw.get("jobDescription", "") or ""

    return {
        "id": f"reed_{raw.get('jobId')}",
        "title": raw.get("jobTitle", ""),
        "company": {"display_name": raw.get("employerName", "") or "Unknown company"},
        "location": {"display_name": raw.get("locationName", "") or "Unknown location"},
        "description": description,
        "redirect_url": raw.get("jobUrl", ""),
        "salary_min": salary_min if salary_min else None,
        "salary_max": salary_max if salary_max else None,
        "created": _reed_date_to_iso(raw.get("date", "")),
        "source": "reed",
        "_track": track,
        "_found_via": found_via,
    }


def _track_for_query(query: str, track_a_queries: set[str], track_b_queries: set[str]) -> str:
    base = query.lower().removeprefix("remote ").strip()
    if base in track_b_queries:
        return "Track B"
    if base in track_a_queries:
        return "Track A"
    return "Track A"


def search_reed_jobs(
    queries: list[str],
    locations: list[str],
    max_days_old: int = 1,
    *,
    track_a_queries: list[str] | None = None,
    track_b_queries: list[str] | None = None,
) -> list[dict]:
    """
    Query Reed for each query × location combination.
    Returns deduplicated jobs normalised to the Adzuna job dict shape.
    """
    load_dotenv()
    api_key = os.getenv("REED_API_KEY")
    if not api_key:
        print("REED_API_KEY not set — skipping Reed search")
        return []

    track_a_set = {q.lower() for q in (track_a_queries or [])}
    track_b_set = {q.lower() for q in (track_b_queries or [])}
    cutoff_date = datetime.now() - timedelta(days=max_days_old)
    all_jobs: list[dict] = []
    seen_ids: set[str] = set()

    print(f"Running {len(queries) * len(locations)} Reed searches (jobs posted in last {max_days_old} day(s))...")

    for query in queries:
        for location in locations:
            try:
                resp = requests.get(
                    REED_SEARCH_URL,
                    auth=(api_key, ""),
                    params={
                        "keywords": query,
                        "locationName": location,
                        "resultsToTake": 20,
                        "datePosted": max_days_old,
                    },
                    timeout=10,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"},
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])

                for job in results:
                    posted_date = job.get("date", "")
                    try:
                        job_date = datetime.strptime(posted_date, "%d/%m/%Y")
                        if job_date < cutoff_date:
                            continue
                    except (ValueError, TypeError):
                        pass

                    job_id = f"reed_{job.get('jobId')}"
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    location_label = "Remote" if query.lower().startswith("remote ") else location
                    track = _track_for_query(query, track_a_set, track_b_set)
                    found_via = f'"{query}" / {location_label}'
                    all_jobs.append(_normalise_reed_job(job, track=track, found_via=found_via))

                time.sleep(REQUEST_DELAY_SECONDS)

            except requests.RequestException as exc:
                print(f"Reed search failed for '{query}' in '{location}': {exc}")
                continue

    print(f"Fetched {len(all_jobs)} unique jobs from Reed\n")
    return all_jobs
