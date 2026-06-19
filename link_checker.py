import requests


def is_job_likely_live(url: str, timeout: int = 5) -> bool:
    """
    Lightweight check to catch hard-dead job listings before spending
    API cost tailoring a resume for them. Fails open — any ambiguity
    (timeout, network error, unsupported method) is treated as "assume
    live" so we never lose a good job over a flaky check.
    Only catches clear failures: 404, 410, or a final redirect destination
    matching a known "expired listing" URL pattern from major UK job
    boards (reed.co.uk, totaljobs.com, cv-library.co.uk, indeed.co.uk —
    these are common Adzuna redirect destinations).
    """
    try:
        resp = requests.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"},
        )

        if resp.status_code == 405:
            # Some servers reject HEAD — retry with GET
            resp = requests.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"},
            )

        if resp.status_code in (404, 410):
            return False

        # Check final landing URL for known "expired" redirect patterns
        final_url = resp.url.lower()
        expired_patterns = [
            "/expired",
            "job-not-found",
            "vacancy-closed",
            "no-longer-available",
            "/search?",
            "jobs-not-found",
        ]
        if any(pattern in final_url for pattern in expired_patterns):
            return False

        return True

    except requests.RequestException as e:
        print(f"Link check failed (assuming live): {url} — {str(e)}")
        return True  # fail open — network hiccup is not proof the job is dead
