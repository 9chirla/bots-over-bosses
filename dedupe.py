"""
Remember which job listings you've already seen so they don't repeat daily.
Phase 2, Step 5: stores Adzuna job IDs in seen_jobs.json.
"""

import json
import os
from datetime import datetime, timezone

DEFAULT_SEEN_FILE = "seen_jobs.json"


def _default_store():
    return {"seen_ids": [], "last_updated": None}


def load_seen_ids(path=DEFAULT_SEEN_FILE):
    """Load previously seen job IDs from disk."""
    if not os.path.exists(path):
        return set()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"Warning: could not read {path}, starting with an empty seen list.")
        return set()

    seen = data.get("seen_ids", [])
    return {str(job_id) for job_id in seen}


def save_seen_ids(seen_ids, path=DEFAULT_SEEN_FILE):
    """Save the full set of seen job IDs to disk."""
    payload = {
        "seen_ids": sorted(seen_ids),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def split_new_jobs(jobs, seen_ids):
    """
    Separate jobs into new (not seen before) and already seen.
    Returns (new_jobs, skipped_count).
    """
    new_jobs = []
    skipped = 0

    for job in jobs:
        job_id = job.get("id")
        if job_id is None:
            new_jobs.append(job)
            continue

        if str(job_id) in seen_ids:
            skipped += 1
        else:
            new_jobs.append(job)

    return new_jobs, skipped


def record_job_ids(jobs, path=DEFAULT_SEEN_FILE):
    """Add job IDs from this run to the seen store."""
    seen_ids = load_seen_ids(path)

    for job in jobs:
        job_id = job.get("id")
        if job_id is not None:
            seen_ids.add(str(job_id))

    save_seen_ids(seen_ids, path)
    return len(seen_ids)


def reset_seen_jobs(path=DEFAULT_SEEN_FILE):
    """Clear the seen jobs file (useful for testing)."""
    if os.path.exists(path):
        os.remove(path)
    print(f"Cleared {path}")


if __name__ == "__main__":
    import sys

    from filters import filter_jobs
    from search_jobs import fetch_all_jobs, format_salary, load_credentials

    if "--reset" in sys.argv:
        reset_seen_jobs()
        sys.exit(0)

    app_id, app_key = load_credentials()
    print("Fetching jobs...\n")
    all_jobs = fetch_all_jobs(app_id, app_key)

    seen_ids = load_seen_ids()
    new_jobs, skipped = split_new_jobs(all_jobs, seen_ids)
    print(f"Already seen: {skipped} jobs skipped\n")

    kept, rejected = filter_jobs(new_jobs)
    print(f"After filtering: {len(kept)} new jobs to show ({len(rejected)} filtered out)\n")

    if kept:
        for job in kept:
            print(job.get("title", "Untitled role"))
            print(f"  Company:  {job.get('company', {}).get('display_name', 'Unknown')}")
            print(f"  Salary:   {format_salary(job)}")
            print(f"  URL:      {job.get('redirect_url', 'No URL')}")
            print()
    else:
        print("No new jobs today — everything was already seen or filtered out.")

    total_seen = record_job_ids(all_jobs)
    print(f"Recorded {len(all_jobs)} job IDs. Total seen jobs stored: {total_seen}")
