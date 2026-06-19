"""
One-time Google Drive OAuth setup for personal Gmail.

Before running:
  1. Google Cloud Console -> APIs & Services -> Enable "Google Drive API"
  2. OAuth consent screen -> External -> add 9chirla@gmail.com as test user
  3. Credentials -> Create OAuth client ID -> Desktop app
  4. Download JSON -> save as client_secret.json in project root

Then run:
  python auth_google_drive.py
"""

from google_drive_auth import authorize_drive_interactive


def main():
    authorize_drive_interactive()


if __name__ == "__main__":
    main()
