"""
Filter Adzuna job results to match an entry-level UK profile.
Phase 2, Step 4: remove senior, overpaid, irrelevant, and visa roles.
"""

from dataclasses import dataclass

from user_profile import UserProfile

SALARY_FLOOR = 20_000
SALARY_CEILING = 45_000

# Title words that usually mean the role is too senior for you.
SENIORITY_BLOCKLIST = [
    "senior",
    "sr.",
    "sr ",
    "head of",
    "director",
    "vice president",
    " vp",
    "principal",
    "staff ",
    " chief",
    "architect",
    "manager",
    "lead ",
    " lead",
    "team lead",
]

# Junior signals — if one of these is in the title, keep it even if "manager" etc. appears elsewhere.
JUNIOR_SIGNALS = [
    "junior",
    "graduate",
    "intern",
    "trainee",
    "entry level",
    "entry-level",
    "assistant",
    "coordinator",
    "analyst",
]

# Roles from broad searches that are not a fit for your profile.
IRRELEVANT_ROLE_BLOCKLIST = [
    "civil engineer",
    "mechanical engineer",
    "electrical engineer",
    "transport engineer",
    "quantity surveyor",
    "design engineer",
    "structural engineer",
    "copywriter",
    "client partner",
]

# Job must match at least one of these (title or description).
RELEVANCE_KEYWORDS = [
    # Track A — analytics / business
    "data analyst",
    "business analyst",
    "reporting analyst",
    "reporting",
    "engagement officer",
    "student engagement",
    "crm",
    "marketing coordinator",
    "campaign coordinator",
    "marketing campaign",
    "power bi",
    "excel",
    "stakeholder",
    # Track B — full stack
    "developer",
    "full stack",
    "fullstack",
    "software engineer",
    "web developer",
    "python",
    "javascript",
    "typescript",
    "react",
    "node",
    "api",
    "sql",
    ".net",
]

VISA_PATTERNS = [
    "visa sponsorship",
    "sponsor visa",
    "requires sponsorship",
    "no visa sponsorship",
]


@dataclass
class FilterSettings:
    salary_floor: int = SALARY_FLOOR
    salary_ceiling: int = SALARY_CEILING
    relevance_keywords: list = None

    def __post_init__(self):
        if self.relevance_keywords is None:
            self.relevance_keywords = list(RELEVANCE_KEYWORDS)


def settings_from_profile(profile: UserProfile | None) -> FilterSettings:
    if profile is None:
        return FilterSettings()
    return FilterSettings(
        salary_floor=profile.salary_min,
        salary_ceiling=profile.salary_max,
        relevance_keywords=profile.relevance_keywords(),
    )


def _job_text(job):
    """Combine title + description into one lowercase string."""
    title = job.get("title", "")
    description = job.get("description", "")
    return f"{title} {description}".lower()


def _has_junior_signal(title_lower):
    return any(signal in title_lower for signal in JUNIOR_SIGNALS)


def check_seniority(job):
    """Return rejection reason if the role looks too senior, else None."""
    title_lower = job.get("title", "").lower()

    if _has_junior_signal(title_lower):
        return None

    for term in SENIORITY_BLOCKLIST:
        if term in title_lower:
            return f"too senior (title contains '{term.strip()}')"

    return None


def check_salary(job, settings: FilterSettings):
    """Return rejection reason if salary is listed and outside your range, else None."""
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")

    if salary_min is None and salary_max is None:
        return None

    if salary_min is not None and salary_max is not None:
        if salary_min > settings.salary_ceiling:
            return f"salary too high (from £{int(salary_min):,})"
        if salary_max < settings.salary_floor:
            return f"salary too low (up to £{int(salary_max):,})"
        return None

    if salary_min is not None and salary_min > settings.salary_ceiling:
        return f"salary too high (from £{int(salary_min):,})"

    if salary_max is not None and salary_max < settings.salary_floor:
        return f"salary too low (up to £{int(salary_max):,})"

    return None


def check_visa(job):
    """Return rejection reason if listing mentions visa sponsorship needs, else None."""
    text = _job_text(job)
    for pattern in VISA_PATTERNS:
        if pattern in text:
            return "visa sponsorship mentioned"
    return None


def check_relevance(job, settings: FilterSettings):
    """Return rejection reason if the job doesn't match your target areas, else None."""
    title_lower = job.get("title", "").lower()
    text = _job_text(job)

    for blocked in IRRELEVANT_ROLE_BLOCKLIST:
        if blocked in title_lower:
            return f"irrelevant role type ('{blocked}')"

    if any(keyword in text for keyword in settings.relevance_keywords):
        return None

    return "no matching keywords for your profile"


def filter_job(job, settings: FilterSettings):
    """
    Run all filters on one job.
    Returns (keep: bool, reason: str | None).
    """
    checks = [
        lambda j: check_seniority(j),
        lambda j: check_salary(j, settings),
        lambda j: check_visa(j),
        lambda j: check_relevance(j, settings),
    ]

    for check in checks:
        reason = check(job)
        if reason:
            return False, reason

    return True, None


def filter_jobs(jobs, profile=None):
    """
    Split jobs into kept and rejected lists.
    Returns (kept_jobs, rejected_jobs) where rejected entries are (job, reason).
    """
    settings = settings_from_profile(profile)
    kept = []
    rejected = []

    for job in jobs:
        keep, reason = filter_job(job, settings)
        if keep:
            kept.append(job)
        else:
            rejected.append((job, reason))

    return kept, rejected


def summarize_rejections(rejected):
    """Count rejection reasons for a summary line."""
    counts = {}
    for _, reason in rejected:
        counts[reason] = counts.get(reason, 0) + 1
    return counts


if __name__ == "__main__":
    from search_jobs import fetch_all_jobs, format_salary, load_credentials

    app_id, app_key = load_credentials()
    print("Fetching jobs...\n")
    jobs = fetch_all_jobs(app_id, app_key)

    kept, rejected = filter_jobs(jobs)
    rejection_counts = summarize_rejections(rejected)

    print(f"Before filtering: {len(jobs)} unique jobs")
    print(f"After filtering:  {len(kept)} jobs kept, {len(rejected)} removed\n")

    if rejection_counts:
        print("Removed because:")
        for reason, count in sorted(rejection_counts.items(), key=lambda x: -x[1]):
            print(f"  {count:>3}  {reason}")
        print()

    if not kept:
        print("No jobs passed the filters. Try again tomorrow or loosen filters for testing.")
    else:
        for job in kept:
            company = job.get("company", {}).get("display_name", "Unknown company")
            location = job.get("location", {}).get("display_name", "Unknown location")
            print(job.get("title", "Untitled role"))
            print(f"  Company:   {company}")
            print(f"  Location:  {location}")
            print(f"  Salary:    {format_salary(job)}")
            print(f"  URL:       {job.get('redirect_url', 'No URL')}")
            print(f"  Track:     {job.get('_track')}")
            print()
