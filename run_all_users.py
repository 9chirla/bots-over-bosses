#!/usr/bin/env python3
"""Run daily digest for all web-app users. Use with cron or GitHub Actions."""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
CRON_SECRET = os.getenv("CRON_SECRET", "")


def main():
    if not CRON_SECRET:
        print("Set CRON_SECRET in .env")
        sys.exit(1)

    response = requests.post(
        f"{BASE_URL.rstrip('/')}/api/cron/run-all",
        headers={"X-Cron-Secret": CRON_SECRET},
        timeout=600,
    )

    if not response.ok:
        print(f"Cron failed: HTTP {response.status_code}")
        print(response.text[:500])
        sys.exit(1)

    data = response.json()
    print(f"Processed {data['users_processed']} users")
    for result in data.get("results", []):
        print(f"  {result['email']}: kept={result.get('kept', 0)}, sent={result.get('sent', 0)}")


if __name__ == "__main__":
    main()
