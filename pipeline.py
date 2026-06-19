"""
Shared job search pipeline for CLI and web app.
"""

from pathlib import Path

from dedupe import record_job_ids as record_file_job_ids
from filters import filter_jobs, summarize_rejections
from score_jobs import score_jobs
from search_jobs import fetch_all_jobs, filter_jobs_posted_today, format_salary, load_credentials
from send_digest import send_cv_documents, send_digest
from user_profile import UserProfile

try:
    import sheets_logger
except ImportError:
    sheets_logger = None

try:
    import resume_tailor
except ImportError:
    resume_tailor = None

RESUME_PATH = Path("config/resume.txt")
TOP_DAILY_MATCHES = 20
TOP_CV_COUNT = 5


def fingerprint(job: dict) -> str:
    """Normalised company + title + location key for cross-source dedup."""
    company = job.get("company", "")
    if isinstance(company, dict):
        company = company.get("display_name", "")
    location = job.get("location", "")
    if isinstance(location, dict):
        location = location.get("display_name", "")
    raw = f"{company}|{job.get('title', '')}|{location}"
    return raw.lower().strip().replace(" ", "")


def _merge_job_sources(adzuna_jobs: list, reed_jobs: list) -> list:
    """Merge Adzuna + Reed jobs, deduping by fingerprint (Adzuna wins ties)."""
    merged: list = []
    seen_fingerprints: set[str] = set()

    for job in adzuna_jobs + reed_jobs:
        fp = fingerprint(job)
        if fp in seen_fingerprints:
            continue
        seen_fingerprints.add(fp)
        merged.append(job)

    return merged


def _print_jobs(ranked):
    for job in ranked:
        company = job.get("company", {}).get("display_name", "Unknown company")
        location = job.get("location", {}).get("display_name", "Unknown location")
        title = job.get("title", "Untitled role")
        url = job.get("redirect_url", "No URL")
        salary = format_salary(job)
        score = job.get("_score")
        score_label = f"{score:.0f}/10" if score is not None else "n/a"
        reason = job.get("_score_reason", "")

        print(f"[{score_label}] {title}")
        if reason:
            print(f"  Fit:       {reason}")
        print(f"  Company:   {company}")
        print(f"  Location:  {location}")
        print(f"  Salary:    {salary}")
        print(f"  URL:       {url}")
        print(f"  Track:     {job.get('_track')}")
        print(f"  Found via: {job.get('_found_via')}")
        print()


def _log_and_tailor(ranked: list, user_email: str | None = None) -> int:
    """Google Sheets logging and resume tailoring for top 5 jobs. Returns dead-link skip count."""
    if not ranked:
        return 0

    if sheets_logger:
        result = sheets_logger.log_jobs_to_sheets(ranked, user_email=user_email)
        if result["rows_added"]:
            print(f"Google Sheets: {result['rows_added']} rows added, {result['duplicates_skipped']} duplicates skipped.")

    if not resume_tailor or not getattr(resume_tailor, "TAILOR_ENABLED", False):
        return 0

    if not RESUME_PATH.exists():
        print("Skipping resume tailoring: config/resume.txt not found")
        return 0

    base_resume = RESUME_PATH.read_text(encoding="utf-8").strip()
    if not base_resume:
        print("Skipping resume tailoring: config/resume.txt is empty")
        return 0

    if resume_tailor.has_placeholders(base_resume):
        print("Skipping resume tailoring: config/resume.txt still has placeholder text like [YOUR NAME].")
        return 0

    scored = [j for j in ranked if j.get("_score") is not None]
    scored.sort(key=lambda j: j["_score"], reverse=True)
    top_five = scored[:TOP_CV_COUNT]

    if not top_five:
        return 0

    from link_checker import is_job_likely_live

    live_jobs = []
    skipped_dead_count = 0

    for job in top_five:
        apply_url = job.get("redirect_url") or job.get("apply_url", "")
        if not apply_url:
            live_jobs.append(job)
            continue

        if is_job_likely_live(apply_url):
            live_jobs.append(job)
        else:
            skipped_dead_count += 1
            company = (
                job.get("company", {}).get("display_name", "Unknown")
                if isinstance(job.get("company"), dict)
                else job.get("company", "Unknown")
            )
            print(f"Skipped (dead link): {job.get('title')} at {company} — {apply_url}")

    if skipped_dead_count:
        print(f"Link check: {skipped_dead_count} dead listing(s) removed before tailoring.\n")

    if not live_jobs:
        print("No live listings in top 5 — skipping resume tailoring.\n")
        return skipped_dead_count

    print(f"Tailoring resumes and cover letters for top {len(live_jobs)} jobs...\n")
    cv_urls = {}

    for job in live_jobs:
        tailored = resume_tailor.tailor_resume(base_resume, job)
        if tailored is None:
            job["tailored_cv_url"] = ""
        else:
            url = resume_tailor.save_and_upload_resume(tailored, job)
            job["tailored_cv_url"] = url or ""
            if url and sheets_logger:
                cv_urls[sheets_logger.job_id_for(job)] = url
                print(f"  CV uploaded: {job.get('title')}")

        letter = resume_tailor.write_cover_letter(base_resume, job)
        if letter is None:
            job["cover_letter_url"] = ""
        else:
            cl_url = resume_tailor.save_and_upload_cover_letter(letter, job)
            job["cover_letter_url"] = cl_url or ""
            if cl_url:
                print(f"  Cover letter uploaded: {job.get('title')}")

    if cv_urls and sheets_logger:
        sheets_logger.update_cv_urls(cv_urls)

    return skipped_dead_count


def run_pipeline(
    *,
    profile: UserProfile | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    telegram_chat_id: str | None = None,
    send_telegram: bool = True,
    print_jobs: bool = True,
    use_db_dedupe: bool = False,
) -> dict:
    """
    Run search → filter today's jobs → score → top 20 digest.
    Returns a summary dict for logging/API responses.
    """
    from user_profile import load_profile

    profile = profile or load_profile()
    app_id, app_key = load_credentials()
    skipped_dead_link = 0

    adzuna_jobs = fetch_all_jobs(app_id, app_key, profile=profile)

    track_a, track_b = profile.search_queries()
    reed_queries = list(track_a)
    if profile.include_track_b:
        reed_queries.extend(track_b)
    if profile.remote_ok:
        reed_queries.extend(f"remote {q}" for q in list(track_a) + (list(track_b) if profile.include_track_b else []))
    reed_locations = [profile.location or "London"]

    try:
        from search_jobs_reed import search_reed_jobs

        reed_jobs = search_reed_jobs(
            reed_queries,
            reed_locations,
            max_days_old=1,
            track_a_queries=track_a,
            track_b_queries=track_b if profile.include_track_b else [],
        )
    except Exception as exc:
        print(f"Reed search failed entirely, continuing with Adzuna only: {exc}")
        reed_jobs = []

    all_jobs = _merge_job_sources(adzuna_jobs, reed_jobs)
    print(
        f"Fetched {len(adzuna_jobs)} from Adzuna, {len(reed_jobs)} from Reed — "
        f"{len(all_jobs)} total after cross-source dedup\n"
    )

    if not all_jobs:
        if send_telegram:
            from send_digest import load_telegram_config

            _, env_chat_id = load_telegram_config()
            resolved = telegram_chat_id or env_chat_id
            if resolved:
                send_digest(
                    [],
                    chat_id=resolved,
                    empty_reason="No jobs posted in the last 24 hours on Adzuna.",
                )
        return {"fetched": 0, "kept": 0, "sent": 0, "jobs_skipped_dead_link": 0}

    today_jobs = filter_jobs_posted_today(all_jobs)
    print(
        f"Daily top {TOP_DAILY_MATCHES} — {len(today_jobs)} jobs posted today "
        f"({len(all_jobs)} fetched from Adzuna)\n"
    )

    jobs_to_filter = today_jobs
    skipped_seen = 0

    kept, rejected = filter_jobs(jobs_to_filter, profile=profile)
    rejection_counts = summarize_rejections(rejected)

    print(f"After filtering: {len(kept)} jobs to score, {len(rejected)} removed\n")

    if rejection_counts:
        print("Top removal reasons:")
        for reason, count in sorted(rejection_counts.items(), key=lambda x: -x[1])[:8]:
            print(f"  {count:>3}  {reason}")
        print()

    score_limit = min(len(kept), 50)
    if kept:
        ranked, score_stats = score_jobs(kept, profile=profile, max_jobs=score_limit)
    else:
        ranked, score_stats = [], {"jobs_skipped_clearance": 0}
    ranked = ranked[:TOP_DAILY_MATCHES]

    if ranked:
        print(f"Sending top {len(ranked)} matches (max {TOP_DAILY_MATCHES})\n")

    skipped_dead_link = _log_and_tailor(
        ranked, user_email=user_email or (profile.email if profile else None)
    )

    digest_title = f"UK Jobs — Top {TOP_DAILY_MATCHES} today"

    if send_telegram and ranked:
        from send_digest import load_telegram_config

        _, env_chat_id = load_telegram_config()
        resolved_chat_id = telegram_chat_id or env_chat_id
        if resolved_chat_id:
            send_cv_documents(ranked, chat_id=resolved_chat_id)

    if send_telegram:
        from send_digest import load_telegram_config

        _, env_chat_id = load_telegram_config()
        resolved_chat_id = telegram_chat_id or env_chat_id
        if resolved_chat_id:
            if not ranked:
                if not jobs_to_filter:
                    empty_reason = (
                        f"No jobs posted today ({len(all_jobs)} fetched were from earlier days). "
                        "Try again tomorrow."
                    )
                else:
                    empty_reason = (
                        f"{len(jobs_to_filter)} jobs posted today but none passed your filters "
                        "(salary, seniority, relevance)."
                    )
                send_digest([], chat_id=resolved_chat_id, empty_reason=empty_reason)
            else:
                send_digest(
                    ranked,
                    chat_id=resolved_chat_id,
                    digest_title=digest_title,
                    daily_top_n=True,
                )

    if use_db_dedupe and user_id:
        from app.database import record_job_ids

        record_job_ids(user_id, all_jobs)
    else:
        record_file_job_ids(all_jobs)

    if print_jobs and ranked:
        _print_jobs(ranked)
    elif not ranked:
        print("No jobs to show today.")

    sent_count = len(ranked)

    run_summary = {
        "fetched": len(all_jobs),
        "skipped_seen": skipped_seen,
        "kept": len(kept),
        "ranked": len(ranked),
        "sent": sent_count,
        "jobs_skipped_clearance": score_stats.get("jobs_skipped_clearance", 0),
        "jobs_skipped_dead_link": skipped_dead_link,
    }

    if sheets_logger:
        sheets_logger.log_run_summary(run_summary, user_email=user_email or (profile.email if profile else None))

    return run_summary
