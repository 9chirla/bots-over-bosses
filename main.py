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


def main():
    parser = argparse.ArgumentParser(description="Daily UK job search agent")
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Print results only, do not send Telegram message",
    )
    args = parser.parse_args()

    run_pipeline(
        send_telegram=not args.no_telegram,
        print_jobs=True,
        use_db_dedupe=False,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
