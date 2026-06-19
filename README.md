# Bots Over Bosses

Daily UK job search agent that finds entry-level roles, scores them with AI, and delivers a mobile-friendly digest to Telegram — with tailored CVs and cover letters for the top matches.

## What it does

Each run:

1. **Searches** Adzuna for UK jobs posted in the last 24 hours
2. **Filters** by salary (£20k–£45k), seniority, location, and profile keywords
3. **Scores** matches with DeepSeek (0–10 fit + punchy summary)
4. **Sends** a Telegram digest (top 20 jobs, split across messages if needed)
5. **Generates** tailored CV + cover letter `.docx` for the top 5 jobs
6. **Uploads** documents to Google Drive and links them in the digest

## Quick start

### 1. Install

```bash
cd bots_over_bosses
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure `.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Yes | [Adzuna API](https://developer.adzuna.com/) credentials |
| `DEEPSEEK_API_KEY` | Yes | [DeepSeek](https://platform.deepseek.com/) API key |
| `TELEGRAM_BOT_TOKEN` | Yes | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram chat ID |
| `GOOGLE_DOCS_FOLDER_ID` | For CVs | Google Drive folder for uploads |
| `GOOGLE_SHEETS_ID` | Optional | Job log spreadsheet |

### 3. Google Drive (one-time)

Personal Gmail uploads need OAuth (service accounts cannot write to personal Drive):

```bash
# Place client_secret.json in project root (from Google Cloud Console)
python3 auth_google_drive.py
```

This saves `google_token.json`. Set `GOOGLE_DOCS_FOLDER_ID` to your target folder.

### 4. Run

```bash
python3 main.py                  # Full run + Telegram digest
python3 main.py --no-telegram    # Print results only
```

Tailored documents are saved to `outputs/`.

## Automatic daily runs (GitHub Actions)

The repo includes `.github/workflows/daily.yml` — runs at **06:00 UTC** daily (≈ 6 AM UK winter / 7 AM UK summer).

**Push secrets from your machine:**

```bash
bash scripts/setup_github_actions.sh
```

**Manual trigger:**

```bash
gh workflow run "Daily UK Job Search"
```

Or use **Actions → Daily UK Job Search → Run workflow** on GitHub.

> GitHub scheduled runs are best-effort and can be delayed by 30–60+ minutes at peak times. The full URL is kept in apply links for Adzuna attribution; Telegram shows clean `[View & Apply]` labels.

## Local schedule (Mac alternative)

For exact local timing with OAuth on your machine:

```bash
bash scripts/install_schedule.sh   # Daily 07:00 local time
bash scripts/uninstall_schedule.sh
```

## Telegram digest format

Each job block includes:

- Bold title + score badge
- Company, location, salary (deduplicated when min = max)
- 2–3 line AI summary (what the role involves + why it fits)
- `[Tailored CV]` / `[Cover Letter]` / `[View & Apply]` Markdown links
- Visual dividers between jobs

## Project structure

```
main.py              CLI entrypoint
pipeline.py          Orchestrates search → filter → score → tailor → send
search_jobs.py       Adzuna API queries
filters.py           Salary, seniority, keyword filtering
score_jobs.py        DeepSeek scoring + summaries
resume_tailor.py     CV + cover letter generation, Drive upload
send_digest.py       Telegram digest formatting and delivery
config/resume.txt    Base CV used for tailoring
scripts/             GitHub secrets setup, local cron helpers
.github/workflows/   Daily GitHub Actions schedule
app/                 Optional FastAPI web app (multi-user)
```

## Your job search preferences

Each user configures **what roles to target** — this drives Adzuna searches, filtering, and AI scoring.

### CLI / GitHub Actions (single user)

Edit `config/profile.json` (created automatically on first run from `config/profile.example.json`):

```bash
cp config/profile.example.json config/profile.json   # or just run main.py once
```

Key fields:

| Field | What it controls |
|-------|------------------|
| `target_titles` | Roles you want (shown in scoring prompt) |
| `track_a_queries` / `track_b_queries` | Adzuna search keywords |
| `skills` | Filter matching + AI scoring |
| `salary_min` / `salary_max` | Salary filter (£) |
| `location` / `remote_ok` | Where to search |
| `level` / `education` | AI scoring context |

Friends using the repo copy `profile.example.json` → `profile.json` and edit their own targets.  
For GitHub Actions, commit your personal `profile.json` or keep it local and use the example defaults in CI.

### Web app (multiple users)

Sign up at `/` — each user sets preferences in the dashboard. Stored per user in SQLite.

### Base CV

Edit `config/resume.txt` for tailored CV/cover letter generation.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No Telegram message | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` |
| Drive upload fails | Re-run `python3 auth_google_drive.py`, then `bash scripts/setup_github_actions.sh` |
| Google Sheets errors | Enable Sheets API; share sheet with service account email as Editor |
| Few jobs in digest | Normal — seniority + keyword filters are strict; most listings are removed |
| OAuth token expired in CI | Refresh locally and re-run `setup_github_actions.sh` |

## License

Private project — personal job search automation.
