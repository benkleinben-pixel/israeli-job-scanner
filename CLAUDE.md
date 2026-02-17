# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Start the full application (installs deps, fetches data if needed, starts server)
./run.sh

# Install Python dependencies
pip3 install -r fetch/requirements.txt

# Run data fetcher once (writes to data/)
python3 fetch/fetcher.py --once

# Run fetcher with periodic scheduling (every 3 hours via `schedule` library)
python3 fetch/fetcher.py

# Start web server (default port 8080, access at http://localhost:8080/web/)
python3 serve.py
python3 serve.py 9000  # custom port

# Install as macOS launchd background job (every 3 hours) + configure WhatsApp notifications
./install.sh

# Test seniority derivation patterns
python3 fetch/seniority.py
```

## Architecture

This is a job aggregation tool for Israeli tech positions. Three layers:

**Data Fetcher** (`fetch/fetcher.py`) — Aggregates jobs from three sources:
1. **TechMap** — CSV files from a GitHub repo (`mluggy/techmap`) covering 19 job categories, plus per-company JSON files for enrichment (ATS IDs, company metadata)
2. **Greenhouse API** — Public boards API, queried per-company using `greenhouseId` from TechMap company data
3. **Lever API** — Public postings API, queried per-company using `leverId` from TechMap company data

The fetch pipeline: TechMap jobs load first (lowest priority), then ATS jobs overwrite TechMap duplicates by matching on URL-hash IDs. Company data is cached locally in `data/company_cache.json` (24-hour TTL) to avoid re-downloading all company JSON files each cycle. Non-Israeli locations from ATS sources are filtered out via `is_israeli_location()`.

Outputs: `data/jobs.json`, `data/companies.json`, `data/metadata.json`.

**Notifications** (`fetch/notify.py`) — Optional WhatsApp alerts via Twilio when new jobs are found. Credentials stored in `fetch/.env` (not committed).

**HTTP Server** (`serve.py`) — Serves static files and exposes `POST /api/refresh` to trigger a re-fetch. Refresh is mutex-locked (returns 409 if already running).

**Frontend** (`web/`) — Vanilla JS single-page app (no build step). Loads JSON data directly, provides filtering/sorting/pagination, tracks read/unread/saved state and followed companies in browser localStorage. Auto-polls `metadata.json` every 5 minutes.

## Key Configuration

- `fetch/config.json` — API endpoints, job categories list, refresh interval, enable/disable Greenhouse/Lever sources
- Job IDs are 12-char MD5 hashes of normalized URLs (UTM params stripped)
- Seniority levels: Intern, Junior, Mid-level (default), Senior, Lead, Manager, Executive — derived from title via regex in `fetch/seniority.py`
- `fetch/seniority.py` also contains: Hebrew-to-English city mapping, Israeli location detection, and ATS department-to-TechMap category normalization
- Fetcher has built-in rate limiting (0.5s between ATS API calls) with exponential backoff on retries
