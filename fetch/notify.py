"""
WhatsApp notification via Twilio.

Sends a WhatsApp message when new jobs are found during a fetch cycle.
Requires Twilio credentials in fetch/.env.
"""

import logging
import os
from pathlib import Path

log = logging.getLogger('fetcher')

ENV_PATH = Path(__file__).resolve().parent / '.env'


def _load_env():
    """Load key=value pairs from fetch/.env into os.environ."""
    if not ENV_PATH.exists():
        return False
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())
    return True


def send_whatsapp(new_count: int, new_jobs: list[dict]):
    """
    Send a WhatsApp notification about new jobs via Twilio.

    Args:
        new_count: Total number of new jobs found.
        new_jobs: List of new job dicts (with 'title', 'company', 'locationEn').
    """
    if new_count <= 0:
        return

    if not _load_env():
        log.info('No fetch/.env file found — skipping WhatsApp notification')
        return

    account_sid = os.environ.get('TWILIO_ACCOUNT_SID', '')
    auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '')
    from_number = os.environ.get('TWILIO_WHATSAPP_FROM', '')
    to_number = os.environ.get('WHATSAPP_TO', '')

    if not all([account_sid, auth_token, from_number, to_number]):
        log.warning('Twilio credentials incomplete — skipping WhatsApp notification')
        return

    # Build message
    lines = [f'\U0001f514 Israeli Job Scanner: {new_count} new job{"s" if new_count != 1 else ""} found!']
    lines.append('')

    top_jobs = new_jobs[:10]
    if top_jobs:
        lines.append('Top new jobs:')
        for job in top_jobs:
            title = job.get('title', 'Unknown')
            company = job.get('company', 'Unknown')
            location = job.get('locationEn', '') or job.get('location', '')
            entry = f'- {title} @ {company}'
            if location:
                entry += f' ({location})'
            lines.append(entry)

    if new_count > 10:
        lines.append(f'... and {new_count - 10} more')

    body = '\n'.join(lines)

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=body,
            from_=f'whatsapp:{from_number}',
            to=f'whatsapp:{to_number}',
        )
        log.info(f'WhatsApp notification sent (SID: {message.sid})')
    except ImportError:
        log.warning('twilio package not installed — run: pip install twilio')
    except Exception as e:
        log.error(f'Failed to send WhatsApp notification: {e}')
