"""User job-search preferences — used by CLI and web app."""

from dataclasses import dataclass, field, asdict
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


@dataclass
class UserProfile:
    email: str = ""
    location: str = "London"
    remote_ok: bool = True
    salary_min: int = 20_000
    salary_max: int = 45_000
    education: str = "MBA (University of East London, 2025), BBA (India)"
    level: str = "entry-level / graduate; full UK right to work; no visa sponsorship needed"
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
        """Keywords for filter matching — built from user skills and titles."""
        base = [
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
        extra = []
        for skill in self.skills:
            extra.append(skill.lower())
        for title in self.target_titles:
            extra.append(title.lower())
        return list(dict.fromkeys(base + extra))

    def llm_summary(self) -> str:
        """Profile text sent to DeepSeek for scoring."""
        track_a = ", ".join(self.target_titles[:6])
        track_b = "Junior/Graduate Developer, Full Stack Developer, Web Developer"
        skills = ", ".join(self.skills)
        remote = "Greater London or UK remote" if self.remote_ok else self.location

        lines = [
            "Candidate profile:",
            f"- Location: {self.location} — open to {remote}",
            f"- Education: {self.education}" if self.education else "- Education: not specified",
            f"- Level: {self.level}",
            f"- Salary target: £{self.salary_min:,}–£{self.salary_max:,}",
            f"- Track A (analytics/business): {track_a}",
        ]
        if self.include_track_b:
            lines.append(f"- Track B (full stack): {track_b}")
        lines.extend([
            f"- Skills: {skills}",
            "- Avoid: senior/lead roles, paid training bootcamp schemes disguised as jobs,",
            "  unrelated engineering (civil/mechanical), sales-only roles with no analyst/dev work",
        ])
        return "\n".join(lines)

    def search_queries(self) -> tuple[list[str], list[str]]:
        track_b = self.track_b_queries if self.include_track_b else []
        return self.track_a_queries, track_b
