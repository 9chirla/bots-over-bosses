"""
Google Drive OAuth credentials for personal Gmail uploads.
Service accounts cannot store files on personal Drive — use this instead.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    OAUTH_AVAILABLE = True
except ImportError:
    OAUTH_AVAILABLE = False


def _token_path() -> Path:
    return Path(os.getenv("GOOGLE_OAUTH_TOKEN", "google_token.json"))


def _client_secrets_path() -> Path:
    return Path(os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "client_secret.json"))


def get_drive_credentials():
    """
    Return valid OAuth credentials for Drive uploads.
    Refreshes expired tokens automatically. Returns None if not configured.
    """
    if not OAUTH_AVAILABLE:
        print(
            "Google Drive OAuth: install google-auth-oauthlib "
            "(pip install google-auth-oauthlib)."
        )
        return None

    token_file = _token_path()
    creds = None

    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), DRIVE_SCOPES)
        except (ValueError, OSError) as exc:
            print(f"Google Drive OAuth: could not read {token_file} ({exc}).")

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_file.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as exc:
            print(f"Google Drive OAuth: token refresh failed ({exc}).")

    secrets_file = _client_secrets_path()
    if not secrets_file.exists():
        print("Google Drive OAuth: not authorised yet.")
        print(f"  1. Download OAuth client JSON from Google Cloud Console")
        print(f"  2. Save it as: {secrets_file}")
        print(f"  3. Run: python auth_google_drive.py")
        return None

    print("Google Drive OAuth: opening browser to sign in...")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), DRIVE_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    token_file.write_text(creds.to_json(), encoding="utf-8")
    print(f"Google Drive OAuth: saved token to {token_file}")
    return creds


def authorize_drive_interactive():
    """Force browser sign-in and save a new token. Used by auth_google_drive.py."""
    if not OAUTH_AVAILABLE:
        raise RuntimeError("google-auth-oauthlib is not installed.")

    secrets_file = _client_secrets_path()
    if not secrets_file.exists():
        raise FileNotFoundError(
            f"Missing {secrets_file}. Create an OAuth Desktop client in Google Cloud "
            "Console and download the JSON file."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), DRIVE_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    token_path = _token_path()
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Authorised. Token saved to {token_path}")
    return creds
