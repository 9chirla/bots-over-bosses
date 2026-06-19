"""
Daily UK job search agent — single entrypoint.
Runs: search → filter today's jobs → score → top 20 Telegram digest.

Usage:
  python main.py              Top 20 jobs posted today
  python main.py --no-telegram   Print only, no Telegram
"""

import argparse
import sys

from pipeline import run_pipeline
from user_profile import ensure_profile_file, load_profile


def main():
    parser = argparse.ArgumentParser(description="Daily UK job search agent")
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Print results only, do not send Telegram message",
    )
    args = parser.parse_args()

    ensure_profile_file()
    profile = load_profile()

    run_pipeline(
        profile=profile,
        send_telegram=not args.no_telegram,
        print_jobs=True,
        use_db_dedupe=False,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
