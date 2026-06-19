"""User job-search preferences — used by CLI and web app."""

import json
import os
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

DEFAULT_TRACK_A = [
    "data analyst",
    "business analyst",
    "reporting analyst",
    "engagement officer",
    "crm",
    "marketing coordinator",
]

DEFAULT_TRACK_B = [
    "junior developer",
    "graduate developer",
    "full stack developer",
    "software developer",
    "web developer",
]

DEFAULT_SKILLS = [
    "Power BI",
    "Excel",
    "CRM",
    "stakeholder reporting",
    "Python",
    "JavaScript",
    "React",
    "SQL",
]

DEFAULT_TARGET_TITLES = [
    "Data Analyst",
    "Business Analyst",
    "Reporting Analyst",
    "Engagement Officer",
    "CRM Executive",
    "Marketing Coordinator",
    "Junior Developer",
    "Full Stack Developer",
    "Web Developer",
]

DEFAULT_LEVEL = (
    "entry-level / graduate; full UK right to work; no visa sponsorship needed"
)

PROFILE_PATH = Path(os.getenv("PROFILE_PATH", "config/profile.json"))
PROFILE_EXAMPLE_PATH = Path("config/profile.example.json")


@dataclass
class UserProfile:
    email: str = ""
    location: str = "London"
    remote_ok: bool = True
    salary_min: int = 20_000
    salary_max: int = 45_000
    education: str = "MBA (University of East London, 2025), BBA (India)"
    level: str = DEFAULT_LEVEL
    track_a_queries: list[str] = field(default_factory=lambda: list(DEFAULT_TRACK_A))
    track_b_queries: list[str] = field(default_factory=lambda: list(DEFAULT_TRACK_B))
    skills: list[str] = field(default_factory=lambda: list(DEFAULT_SKILLS))
    target_titles: list[str] = field(default_factory=lambda: list(DEFAULT_TARGET_TITLES))
    include_track_b: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def relevance_keywords(self) -> list[str]:
        """Keywords for filter matching — built from this user's preferences only."""
        keywords: list[str] = []
        for query in self.track_a_queries:
            keywords.append(query.lower())
        if self.include_track_b:
            for query in self.track_b_queries:
                keywords.append(query.lower())
        for skill in self.skills:
            keywords.append(skill.lower())
        for title in self.target_titles:
            keywords.append(title.lower())
        return list(dict.fromkeys(k for k in keywords if k))

    def llm_summary(self) -> str:
        """Profile text sent to DeepSeek for scoring."""
        track_a = ", ".join(self.target_titles[:8]) or ", ".join(self.track_a_queries[:8])
        skills = ", ".join(self.skills)
        remote = "Greater London or UK remote" if self.remote_ok else self.location

        lines = [
            "Candidate profile:",
            f"- Location: {self.location} — open to {remote}",
            f"- Education: {self.education}" if self.education else "- Education: not specified",
            f"- Level: {self.level}",
            f"- Salary target: £{self.salary_min:,}–£{self.salary_max:,}",
            f"- Target roles: {track_a}",
        ]
        if self.include_track_b:
            track_b = ", ".join(self.track_b_queries[:6])
            lines.append(f"- Also considering: {track_b}")
        lines.extend([
            f"- Skills: {skills}",
            "- Avoid: senior/lead roles, paid training bootcamp schemes disguised as jobs,",
            "  unrelated engineering (civil/mechanical), sales-only roles with no analyst/dev work",
        ])
        return "\n".join(lines)

    def search_queries(self) -> tuple[list[str], list[str]]:
        track_b = self.track_b_queries if self.include_track_b else []
        return self.track_a_queries, track_b


def _read_profile_file(path: Path) -> UserProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return UserProfile.from_dict(data)


def ensure_profile_file(path: Path | None = None) -> Path:
    """
    Create config/profile.json from the example template if it does not exist.
    Returns the path that was ensured.
    """
    path = path or PROFILE_PATH
    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    if PROFILE_EXAMPLE_PATH.exists():
        shutil.copy(PROFILE_EXAMPLE_PATH, path)
        print(f"Created {path} — edit this file to set your job search preferences.\n")
    else:
        path.write_text(
            json.dumps(UserProfile().to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Created {path} with default preferences.\n")
    return path


def load_profile(path: str | Path | None = None, create_if_missing: bool = False) -> UserProfile:
    """
    Load job-search preferences from JSON.
    Falls back to profile.example.json, then built-in defaults.
    """
    resolved = Path(path or os.getenv("PROFILE_PATH", PROFILE_PATH))

    if create_if_missing and not resolved.exists():
        ensure_profile_file(resolved)

    if resolved.exists():
        return _read_profile_file(resolved)

    if PROFILE_EXAMPLE_PATH.exists():
        return _read_profile_file(PROFILE_EXAMPLE_PATH)

    return UserProfile()


def save_profile(profile: UserProfile, path: str | Path | None = None) -> Path:
    """Persist preferences to JSON."""
    resolved = Path(path or os.getenv("PROFILE_PATH", PROFILE_PATH))
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(profile.to_dict(), indent=2) + "\n", encoding="utf-8")
    return resolved


def profile_from_form(
    email: str,
    *,
    location: str,
    remote_ok: bool,
    salary_min: int,
    salary_max: int,
    education: str,
    level: str,
    skills: list[str],
    target_titles: list[str],
    track_a_queries: list[str] | None = None,
    track_b_queries: list[str] | None = None,
    include_track_b: bool = True,
) -> UserProfile:
    """Build a UserProfile from web form / API fields."""
    resolved_track_a = track_a_queries or [t.lower() for t in target_titles] or list(DEFAULT_TRACK_A)
    resolved_track_b = track_b_queries or (list(DEFAULT_TRACK_B) if include_track_b else [])

    return UserProfile(
        email=email,
        location=location.strip(),
        remote_ok=remote_ok,
        salary_min=salary_min,
        salary_max=salary_max,
        education=education.strip(),
        level=level.strip() or DEFAULT_LEVEL,
        skills=skills,
        target_titles=target_titles,
        track_a_queries=resolved_track_a,
        track_b_queries=resolved_track_b,
        include_track_b=include_track_b,
    )
