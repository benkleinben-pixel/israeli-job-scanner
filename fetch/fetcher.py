#!/usr/bin/env python3
"""
Israeli Startup Job Scanner — Data Fetcher

Aggregates job listings from:
1. TechMap GitHub repo (primary — CSV job files + company JSON)
2. Greenhouse API (secondary — free, no auth)
3. Lever API (secondary — free, no auth)

Outputs unified JSON files to the data/ directory.
"""

import argparse
import csv
import hashlib
import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from seniority import derive_seniority, translate_city, is_israeli_location, normalize_department

# ─── Configuration ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
FETCH_DIR = Path(__file__).resolve().parent
CONFIG_PATH = FETCH_DIR / 'config.json'
COMPANY_CACHE_PATH = DATA_DIR / 'company_cache.json'
COMPANY_CACHE_MAX_AGE_HOURS = 24

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('fetcher')

# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)


def normalize_url(url: str) -> str:
    """Strip UTM params and trailing slashes for deduplication."""
    if not url:
        return ''
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    # Remove UTM and tracking params
    clean_params = {k: v for k, v in params.items()
                    if not k.startswith('utm_') and k not in ('source', 'medium', 'campaign')}
    clean_query = urlencode(clean_params, doseq=True)
    cleaned = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'),
                          parsed.params, clean_query, ''))
    return cleaned


def url_hash(url: str) -> str:
    """Generate a short hash ID from a normalized URL."""
    normalized = normalize_url(url)
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def safe_get(url: str, timeout: int = 30, retries: int = 2) -> requests.Response | None:
    """GET with retries and error handling."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < retries:
                log.warning(f'Retry {attempt + 1} for {url}: {e}')
                time.sleep(2 ** attempt)
            else:
                log.error(f'Failed to fetch {url}: {e}')
                return None


# ─── TechMap Source ──────────────────────────────────────────────────────────

def fetch_techmap_lookups(config: dict) -> tuple[dict, dict]:
    """Fetch categories.json and sizes.json from TechMap."""
    categories = {}
    sizes = {}

    resp = safe_get(config['techmap']['categories_url'])
    if resp:
        categories = resp.json()
        log.info(f'Loaded {len(categories)} categories')

    resp = safe_get(config['techmap']['sizes_url'])
    if resp:
        sizes = resp.json()
        log.info(f'Loaded {len(sizes)} sizes')

    return categories, sizes


def _load_company_cache() -> tuple[dict, bool]:
    """
    Load cached company data. Returns (cache_dict, is_fresh).
    is_fresh is True if the cache is less than COMPANY_CACHE_MAX_AGE_HOURS old.
    """
    if not COMPANY_CACHE_PATH.exists():
        return {}, False
    try:
        with open(COMPANY_CACHE_PATH, 'r') as f:
            cache = json.load(f)
        cached_at = cache.get('_cached_at', '')
        companies = cache.get('companies', {})
        if cached_at:
            age_hours = (time.time() - datetime.fromisoformat(cached_at).timestamp()) / 3600
            is_fresh = age_hours < COMPANY_CACHE_MAX_AGE_HOURS
        else:
            is_fresh = False
        log.info(f'Loaded {len(companies)} companies from cache (fresh={is_fresh})')
        return companies, is_fresh
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning(f'Error reading company cache: {e}')
        return {}, False


def _save_company_cache(companies: dict):
    """Save company data to local cache file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = {
        '_cached_at': datetime.now(timezone.utc).isoformat(),
        'companies': companies,
    }
    with open(COMPANY_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    log.info(f'Saved {len(companies)} companies to cache')


def _fetch_company_file(base_url: str, file_path: str, categories: dict) -> tuple[str, dict] | None:
    """Fetch and parse a single company JSON file. Returns (name, data) or None."""
    url = f'{base_url}/{file_path}'
    resp = safe_get(url, timeout=10, retries=1)
    if not resp:
        return None
    try:
        data = resp.json()
        name = data.get('name', '')
        if not name:
            return None
        cat_id = str(data.get('categoryId', ''))
        category = categories.get(cat_id, 'Other')
        return name, {
            'category': category,
            'size': data.get('size', ''),
            'website': data.get('websiteUrl', ''),
            'careers': data.get('careersUrl', ''),
            'linkedin': data.get('linkedinId', ''),
            'cities': [addr.get('city', '') for addr in data.get('addresses', [])],
            'greenhouseId': data.get('greenhouseId'),
            'leverId': data.get('leverId'),
            'comeetId': data.get('comeetId'),
            'breezyId': data.get('breezyId'),
        }
    except (json.JSONDecodeError, KeyError) as e:
        log.warning(f'Error parsing {file_path}: {e}')
        return None


def fetch_techmap_companies(config: dict, company_names: set, categories: dict) -> dict:
    """
    Fetch company JSON files from TechMap for companies found in job CSVs.
    Uses a local cache to avoid re-downloading on every run.
    Only fetches companies not already in cache.
    Full cache refresh once per day.
    """
    cached_companies, is_fresh = _load_company_cache()

    # Determine which companies we still need to fetch
    missing = company_names - set(cached_companies.keys())

    if is_fresh and not missing:
        log.info(f'Company cache is fresh, all {len(cached_companies)} companies cached — skipping downloads')
        return cached_companies

    # Get the repo tree to find company file paths
    log.info('Fetching TechMap repo tree...')
    resp = safe_get(config['techmap']['tree_url'])
    if not resp:
        log.warning('Could not fetch repo tree, using cache only')
        return cached_companies

    tree = resp.json()
    company_files = [item['path'] for item in tree.get('tree', [])
                     if item['path'].startswith('companies/') and item['path'].endswith('.json')]
    log.info(f'Found {len(company_files)} company files in repo')

    base_url = config['techmap']['base_url']

    if is_fresh:
        # Cache is fresh — only fetch missing companies
        log.info(f'Cache is fresh. Fetching {len(missing)} new companies only...')
        fetched = 0
        for file_path in company_files:
            if not missing:
                break
            if fetched >= 100:  # Limit new company downloads per run
                break

            result = _fetch_company_file(base_url, file_path, categories)
            if result:
                name, data = result
                if name in missing:
                    cached_companies[name] = data
                    missing.discard(name)
                    fetched += 1

            if fetched % 50 == 0 and fetched > 0:
                time.sleep(1)

        if fetched > 0:
            log.info(f'Fetched {fetched} new companies')
            _save_company_cache(cached_companies)
    else:
        # Cache is stale or empty — do a full refresh
        log.info('Cache is stale or empty — doing full company download...')
        companies = {}
        fetched = 0

        for file_path in company_files:
            if fetched >= 500:
                break

            result = _fetch_company_file(base_url, file_path, categories)
            if result:
                name, data = result
                if name in company_names:
                    companies[name] = data
                    fetched += 1

            if fetched % 50 == 0 and fetched > 0:
                time.sleep(1)

        log.info(f'Full refresh: fetched {len(companies)} company profiles')
        _save_company_cache(companies)
        return companies

    log.info(f'Total companies available: {len(cached_companies)}')
    return cached_companies


def fetch_techmap_jobs(config: dict, categories: dict) -> tuple[list[dict], set[str]]:
    """
    Fetch all job CSVs from TechMap.
    Returns (jobs_list, company_names_set)
    """
    jobs = []
    company_names = set()
    base_url = config['techmap']['base_url']

    for category in config['techmap']['job_categories']:
        url = f'{base_url}/jobs/{category}.csv'
        resp = safe_get(url)
        if not resp:
            continue

        # Parse CSV (strip BOM if present)
        content = resp.text.lstrip('\ufeff')
        reader = csv.DictReader(io.StringIO(content))

        count = 0
        for row in reader:
            job_url = row.get('url', '').strip()
            if not job_url:
                continue

            title = row.get('title', '').strip()
            company = row.get('company', '').strip()
            city = row.get('city', '').strip()
            updated = row.get('updated', '').strip()
            level = row.get('level', '').strip()
            size = row.get('size', '').strip()
            row_category = row.get('category', '').strip()

            company_names.add(company)

            job = {
                'id': url_hash(job_url),
                'title': title,
                'company': company,
                'location': city,
                'locationEn': translate_city(city),
                'industry': row_category,
                'seniority': derive_seniority(title),
                'level': level,
                'department': category,
                'companySize': size,
                'url': job_url,
                'updated': updated,
                'source': 'techmap',
            }
            jobs.append(job)
            count += 1

        log.info(f'  {category}: {count} jobs')

    log.info(f'TechMap total: {len(jobs)} jobs from {len(company_names)} companies')
    return jobs, company_names


# ─── Greenhouse Source ──────────────────────────────────────────────────────

def fetch_greenhouse_jobs(config: dict, companies: dict) -> list[dict]:
    """Fetch jobs from Greenhouse API for companies with greenhouseId."""
    if not config.get('greenhouse', {}).get('enabled', False):
        return []

    jobs = []
    api_base = config['greenhouse']['api_base']

    greenhouse_companies = {name: data for name, data in companies.items()
                           if data.get('greenhouseId')}

    log.info(f'Fetching Greenhouse jobs for {len(greenhouse_companies)} companies...')

    for company_name, company_data in greenhouse_companies.items():
        board_token = company_data['greenhouseId']
        url = f'{api_base}/{board_token}/jobs'

        resp = safe_get(url, timeout=15, retries=1)
        if not resp:
            continue

        try:
            data = resp.json()
            job_list = data.get('jobs', [])

            added = 0
            for job in job_list:
                job_url = job.get('absolute_url', '')
                if not job_url:
                    continue

                location = job.get('location', {}).get('name', '')

                # Filter to Israeli locations only
                if not is_israeli_location(location):
                    continue

                updated = job.get('updated_at', '')[:10] if job.get('updated_at') else ''

                # Extract department from departments list
                departments = job.get('departments', [])
                dept_name = departments[0].get('name', '') if departments else ''

                jobs.append({
                    'id': url_hash(job_url),
                    'title': job.get('title', ''),
                    'company': company_name,
                    'location': location,
                    'locationEn': translate_city(location),
                    'industry': company_data.get('category', ''),
                    'seniority': derive_seniority(job.get('title', '')),
                    'level': '',
                    'department': normalize_department(dept_name),
                    'companySize': company_data.get('size', ''),
                    'url': job_url,
                    'updated': updated,
                    'source': 'greenhouse',
                })
                added += 1

            if added:
                skipped = len(job_list) - added
                msg = f'  Greenhouse {company_name}: {added} jobs'
                if skipped:
                    msg += f' ({skipped} non-Israeli filtered)'
                log.info(msg)

        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f'Error parsing Greenhouse data for {company_name}: {e}')

        time.sleep(0.5)  # Rate limiting

    log.info(f'Greenhouse total: {len(jobs)} jobs')
    return jobs


# ─── Lever Source ───────────────────────────────────────────────────────────

def fetch_lever_jobs(config: dict, companies: dict) -> list[dict]:
    """Fetch jobs from Lever API for companies with leverId."""
    if not config.get('lever', {}).get('enabled', False):
        return []

    jobs = []
    api_base = config['lever']['api_base']

    lever_companies = {name: data for name, data in companies.items()
                       if data.get('leverId')}

    log.info(f'Fetching Lever jobs for {len(lever_companies)} companies...')

    for company_name, company_data in lever_companies.items():
        site_name = company_data['leverId']
        url = f'{api_base}/{site_name}?mode=json'

        resp = safe_get(url, timeout=15, retries=1)
        if not resp:
            continue

        try:
            job_list = resp.json()
            if not isinstance(job_list, list):
                continue

            added = 0
            for job in job_list:
                job_url = job.get('hostedUrl', '')
                if not job_url:
                    continue

                categories = job.get('categories', {})
                location = categories.get('location', '')

                # Filter to Israeli locations only
                if not is_israeli_location(location):
                    continue

                created = job.get('createdAt', 0)
                updated = ''
                if created:
                    updated = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

                jobs.append({
                    'id': url_hash(job_url),
                    'title': job.get('text', ''),
                    'company': company_name,
                    'location': location,
                    'locationEn': translate_city(location),
                    'industry': company_data.get('category', ''),
                    'seniority': derive_seniority(job.get('text', '')),
                    'level': '',
                    'department': normalize_department(categories.get('team', '')),
                    'companySize': company_data.get('size', ''),
                    'url': job_url,
                    'updated': updated,
                    'source': 'lever',
                })
                added += 1

            if added:
                skipped = len(job_list) - added
                msg = f'  Lever {company_name}: {added} jobs'
                if skipped:
                    msg += f' ({skipped} non-Israeli filtered)'
                log.info(msg)

        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f'Error parsing Lever data for {company_name}: {e}')

        time.sleep(0.5)  # Rate limiting

    log.info(f'Lever total: {len(jobs)} jobs')
    return jobs


# ─── Merge & Deduplicate ────────────────────────────────────────────────────

def merge_jobs(techmap_jobs: list, greenhouse_jobs: list, lever_jobs: list,
               existing_jobs: dict) -> list[dict]:
    """
    Merge jobs from all sources, deduplicate by normalized URL.
    ATS API versions take priority over TechMap CSV versions.
    Preserves firstSeen from existing data.
    """
    merged = {}
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # Add TechMap jobs first (lowest priority)
    for job in techmap_jobs:
        merged[job['id']] = job

    # ATS jobs overwrite TechMap duplicates
    for job in greenhouse_jobs + lever_jobs:
        merged[job['id']] = job

    # Set firstSeen dates
    for job_id, job in merged.items():
        if job_id in existing_jobs:
            job['firstSeen'] = existing_jobs[job_id].get('firstSeen', today)
        else:
            job['firstSeen'] = today

    result = list(merged.values())
    # Sort by updated date descending
    result.sort(key=lambda j: j.get('updated', ''), reverse=True)

    return result


# ─── Main ────────────────────────────────────────────────────────────────────

def load_existing_jobs() -> dict:
    """Load existing jobs.json to preserve firstSeen dates."""
    jobs_path = DATA_DIR / 'jobs.json'
    if jobs_path.exists():
        try:
            with open(jobs_path, 'r') as f:
                jobs = json.load(f)
                return {j['id']: j for j in jobs}
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def run_fetch():
    """Execute a full fetch cycle."""
    config = load_config()
    start_time = time.time()

    log.info('=' * 60)
    log.info('Starting job fetch cycle...')
    log.info('=' * 60)

    # Load existing data for firstSeen preservation
    existing_jobs = load_existing_jobs()
    log.info(f'Loaded {len(existing_jobs)} existing jobs for firstSeen tracking')

    # 1. Fetch TechMap lookups
    categories, sizes = fetch_techmap_lookups(config)

    # 2. Fetch TechMap jobs
    techmap_jobs, company_names = fetch_techmap_jobs(config, categories)

    # 3. Fetch company details (for ATS IDs and enrichment)
    companies = fetch_techmap_companies(config, company_names, categories)

    # 4. Fetch Greenhouse jobs
    greenhouse_jobs = fetch_greenhouse_jobs(config, companies)

    # 5. Fetch Lever jobs
    lever_jobs = fetch_lever_jobs(config, companies)

    # 6. Merge and deduplicate
    all_jobs = merge_jobs(techmap_jobs, greenhouse_jobs, lever_jobs, existing_jobs)

    # 7. Count new jobs
    new_count = sum(1 for j in all_jobs if j['id'] not in existing_jobs)

    # 7b. Send WhatsApp notification for new jobs
    if new_count > 0:
        try:
            from notify import send_whatsapp
            new_jobs_list = [j for j in all_jobs if j['id'] not in existing_jobs]
            send_whatsapp(new_count, new_jobs_list)
        except Exception as e:
            log.warning(f'WhatsApp notification failed: {e}')

    # 8. Build companies output
    companies_output = {}
    for name, data in companies.items():
        companies_output[name] = {
            'category': data.get('category', ''),
            'size': data.get('size', ''),
            'website': data.get('website', ''),
            'careers': data.get('careers', ''),
            'linkedin': data.get('linkedin', ''),
            'cities': data.get('cities', []),
        }

    # Also add companies from jobs that weren't in company files
    for job in all_jobs:
        if job['company'] not in companies_output:
            companies_output[job['company']] = {
                'category': job.get('industry', ''),
                'size': job.get('companySize', ''),
                'website': '',
                'careers': '',
                'linkedin': '',
                'cities': [job.get('location', '')],
            }

    # 9. Build metadata
    source_counts = {}
    for job in all_jobs:
        src = job.get('source', 'unknown')
        source_counts[src] = source_counts.get(src, 0) + 1

    metadata = {
        'lastRefresh': datetime.now(timezone.utc).isoformat(),
        'totalJobs': len(all_jobs),
        'totalCompanies': len(companies_output),
        'sources': source_counts,
        'newSinceLastRefresh': new_count,
        'fetchDurationSeconds': round(time.time() - start_time, 1),
    }

    # 10. Write output files
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(DATA_DIR / 'jobs.json', 'w', encoding='utf-8') as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=2)

    with open(DATA_DIR / 'companies.json', 'w', encoding='utf-8') as f:
        json.dump(companies_output, f, ensure_ascii=False, indent=2)

    with open(DATA_DIR / 'metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    log.info('=' * 60)
    log.info(f'Fetch complete in {metadata["fetchDurationSeconds"]}s')
    log.info(f'Total: {len(all_jobs)} jobs | {len(companies_output)} companies | {new_count} new')
    log.info(f'Sources: {source_counts}')
    log.info('=' * 60)


def main():
    """Run fetcher once or schedule periodic runs."""
    parser = argparse.ArgumentParser(description='Israeli Job Scanner — Data Fetcher')
    parser.add_argument('--once', action='store_true',
                        help='Run a single fetch cycle and exit')
    args = parser.parse_args()

    # First run immediately
    run_fetch()

    if args.once:
        return

    # Schedule periodic runs
    try:
        import schedule

        config = load_config()
        interval = config.get('refresh_interval_hours', 3)

        schedule.every(interval).hours.do(run_fetch)
        log.info(f'Scheduled to refresh every {interval} hours. Press Ctrl+C to stop.')

        while True:
            schedule.run_pending()
            time.sleep(60)

    except ImportError:
        log.info('schedule library not installed. Run manually or set up a cron job.')
        log.info('Install with: pip install schedule')
    except KeyboardInterrupt:
        log.info('Fetcher stopped.')


if __name__ == '__main__':
    main()
