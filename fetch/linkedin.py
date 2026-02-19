#!/usr/bin/env python3
"""
LinkedIn job scraper using Playwright (headless Chromium).

Scrapes public LinkedIn job search pages for Israeli tech positions.
No login required — uses the public /jobs/search/ endpoint.
"""

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from seniority import derive_seniority, translate_city, is_israeli_location, normalize_department

log = logging.getLogger('fetcher')

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    """Generate a short hash ID from a URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _parse_relative_date(date_text: str) -> str:
    """
    Convert LinkedIn relative dates like '2 days ago', '1 week ago'
    into YYYY-MM-DD strings. Returns today's date for unrecognized formats.
    """
    today = datetime.now(timezone.utc)
    text = date_text.strip().lower()

    match = re.search(r'(\d+)\s+(second|minute|hour|day|week|month)', text)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if unit in ('second', 'minute', 'hour'):
            pass  # same day
        elif unit == 'day':
            from datetime import timedelta
            today -= timedelta(days=num)
        elif unit == 'week':
            from datetime import timedelta
            today -= timedelta(weeks=num)
        elif unit == 'month':
            from datetime import timedelta
            today -= timedelta(days=num * 30)

    return today.strftime('%Y-%m-%d')


def _build_search_url(query: str, geo_id: str, start: int = 0) -> str:
    """Build a LinkedIn job search URL with filters."""
    from urllib.parse import quote_plus
    base = 'https://www.linkedin.com/jobs/search/'
    params = f'?keywords={quote_plus(query)}&location=Israel&geoId={geo_id}&f_TPR=r604800&start={start}'
    return base + params


# ─── Scraper ─────────────────────────────────────────────────────────────────

def _scroll_and_load(page, max_scrolls: int = 3):
    """Scroll the page to trigger lazy-loading of job cards."""
    for i in range(max_scrolls):
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(1)
        # Click "See more jobs" button if present
        try:
            see_more = page.locator('button.infinite-scroller__show-more-button')
            if see_more.is_visible(timeout=1000):
                see_more.click()
                time.sleep(1)
        except Exception:
            pass


def _extract_jobs_from_page(page) -> list[dict]:
    """Extract job card data from a LinkedIn search results page."""
    jobs = []

    # LinkedIn uses <ul class="jobs-search__results-list"> with <li> job cards
    cards = page.locator('ul.jobs-search__results-list > li').all()

    if not cards:
        # Fallback selector for alternative page structure
        cards = page.locator('div.job-search-card').all()

    for card in cards:
        try:
            # Title
            title_el = card.locator('h3.base-search-card__title')
            title = title_el.text_content(timeout=2000).strip() if title_el.count() else ''

            # Company
            company_el = card.locator('h4.base-search-card__subtitle a, h4.base-search-card__subtitle')
            company = company_el.first.text_content(timeout=2000).strip() if company_el.count() else ''

            # Location
            location_el = card.locator('span.job-search-card__location')
            location = location_el.text_content(timeout=2000).strip() if location_el.count() else ''

            # URL
            link_el = card.locator('a.base-card__full-link, a.base-search-card--link')
            job_url = link_el.get_attribute('href', timeout=2000) if link_el.count() else ''

            # Date
            date_el = card.locator('time')
            date_text = date_el.get_attribute('datetime', timeout=2000) if date_el.count() else ''
            if not date_text:
                date_text = date_el.text_content(timeout=2000).strip() if date_el.count() else ''

            if not title or not job_url:
                continue

            # Clean URL — strip tracking params
            if '?' in job_url:
                job_url = job_url.split('?')[0]
            job_url = job_url.strip()

            # Parse date
            if date_text and re.match(r'\d{4}-\d{2}-\d{2}', date_text):
                updated = date_text[:10]
            elif date_text:
                updated = _parse_relative_date(date_text)
            else:
                updated = datetime.now(timezone.utc).strftime('%Y-%m-%d')

            jobs.append({
                'title': title,
                'company': company,
                'location': location,
                'url': job_url,
                'updated': updated,
            })

        except Exception as e:
            log.debug(f'Error extracting job card: {e}')
            continue

    return jobs


def fetch_linkedin_jobs(config: dict) -> list[dict]:
    """
    Fetch jobs from LinkedIn public search pages using Playwright.
    Returns a list of normalized job dicts.
    """
    linkedin_config = config.get('linkedin', {})
    if not linkedin_config.get('enabled', False):
        return []

    search_queries = linkedin_config.get('search_queries', ['software engineer'])
    geo_id = linkedin_config.get('geo_id', '101620260')  # Israel
    max_pages = linkedin_config.get('max_pages_per_query', 3)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning('Playwright not installed — skipping LinkedIn. Install with: pip install playwright && playwright install chromium')
        return []

    raw_jobs = []
    seen_urls = set()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    log.info(f'Fetching LinkedIn jobs for {len(search_queries)} queries, up to {max_pages} pages each...')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        page = context.new_page()

        for query in search_queries:
            for page_num in range(max_pages):
                start = page_num * 25
                url = _build_search_url(query, geo_id, start)

                log.info(f'  LinkedIn: "{query}" page {page_num + 1}...')

                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    time.sleep(2)  # Wait for initial render

                    _scroll_and_load(page)

                    page_jobs = _extract_jobs_from_page(page)
                    log.info(f'    Found {len(page_jobs)} job cards')

                    if not page_jobs:
                        break  # No more results for this query

                    for job in page_jobs:
                        if job['url'] not in seen_urls:
                            seen_urls.add(job['url'])
                            raw_jobs.append(job)

                except Exception as e:
                    log.warning(f'  LinkedIn page load failed for "{query}" page {page_num + 1}: {e}')
                    break

                # Rate limiting between page loads
                time.sleep(2)

            # Extra delay between different search queries
            time.sleep(1)

        browser.close()

    # Normalize and filter jobs
    jobs = []
    for raw in raw_jobs:
        location = raw['location']

        # Filter to Israeli locations
        if not is_israeli_location(location):
            continue

        title = raw['title']
        job_url = raw['url']

        jobs.append({
            'id': _url_hash(job_url),
            'title': title,
            'company': raw['company'],
            'location': location,
            'locationEn': translate_city(location),
            'industry': '',
            'seniority': derive_seniority(title),
            'level': '',
            'department': '',
            'companySize': '',
            'url': job_url,
            'updated': raw['updated'],
            'source': 'linkedin',
        })

    log.info(f'LinkedIn total: {len(jobs)} Israeli jobs (from {len(raw_jobs)} raw results)')
    return jobs


# ─── Company-based scraper ──────────────────────────────────────────────────

def fetch_linkedin_jobs_by_company(config: dict, company_slugs: list[str]) -> list[dict]:
    """
    Fetch jobs from LinkedIn for specific companies.
    Uses company-filtered search URL (f_C=<id>) when a numeric ID is available,
    otherwise falls back to /company/<slug>/jobs/ page.
    Returns a list of normalized job dicts (same format as fetch_linkedin_jobs).
    """
    linkedin_config = config.get('linkedin', {})
    if not linkedin_config.get('enabled', False):
        return []

    if not company_slugs:
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning('Playwright not installed — skipping LinkedIn company scraping.')
        return []

    company_ids = linkedin_config.get('company_ids', {})
    geo_id = linkedin_config.get('geo_id', '101620260')

    raw_jobs = []
    seen_urls = set()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    log.info(f'Fetching LinkedIn jobs for {len(company_slugs)} company pages...')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        page = context.new_page()

        for slug in company_slugs:
            company_id = company_ids.get(slug)
            if company_id:
                # Use search URL filtered by company ID — same structure as keyword search
                url = f'https://www.linkedin.com/jobs/search/?f_C={company_id}&geoId={geo_id}'
                log.info(f'  LinkedIn company search (id={company_id}): {slug}...')
            else:
                url = f'https://www.linkedin.com/company/{slug}/jobs/'
                log.info(f'  LinkedIn company page: {slug}...')

            try:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                time.sleep(2)

                _scroll_and_load(page, max_scrolls=5)

                page_jobs = _extract_jobs_from_page(page)
                log.info(f'    Found {len(page_jobs)} job cards for {slug}')

                for job in page_jobs:
                    if job['url'] not in seen_urls:
                        seen_urls.add(job['url'])
                        raw_jobs.append(job)

            except Exception as e:
                log.warning(f'  LinkedIn company page failed for {slug}: {e}')

            # Rate limiting between company pages (3-5 sec)
            time.sleep(3 + (hash(slug) % 3))

        browser.close()

    # Normalize and filter jobs
    jobs = []
    for raw in raw_jobs:
        location = raw['location']

        if not is_israeli_location(location):
            continue

        title = raw['title']
        job_url = raw['url']

        jobs.append({
            'id': _url_hash(job_url),
            'title': title,
            'company': raw['company'],
            'location': location,
            'locationEn': translate_city(location),
            'industry': '',
            'seniority': derive_seniority(title),
            'level': '',
            'department': '',
            'companySize': '',
            'url': job_url,
            'updated': raw['updated'],
            'source': 'linkedin',
        })

    log.info(f'LinkedIn company pages total: {len(jobs)} Israeli jobs (from {len(raw_jobs)} raw results)')
    return jobs


# ─── Standalone test ─────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )

    config_path = Path(__file__).resolve().parent / 'config.json'
    with open(config_path, 'r') as f:
        config = json.load(f)

    jobs = fetch_linkedin_jobs(config)
    print(f'\nFound {len(jobs)} jobs:')
    for job in jobs[:10]:
        print(f'  {job["company"]:30s} | {job["title"][:50]:50s} | {job["location"]}')
    if len(jobs) > 10:
        print(f'  ... and {len(jobs) - 10} more')
