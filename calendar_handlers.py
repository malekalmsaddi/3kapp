import os
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
from logati import logger

# Load configuration
load_dotenv()
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
IMPERSONATE_USER = os.getenv("GOOGLE_CALENDAR_USER", CALENDAR_ID)
TIMEZONE = "Asia/Qatar"
DEFAULT_DURATION_MINUTES = 30
WORKDAY_START_HOUR = 9
WORKDAY_END_HOUR = 17


def get_calendar_service(fail_silently: bool = False):
    """
    Initialize Google Calendar API client using base64-encoded service account credentials.
    Returns a service client or raises RuntimeError on failure.
    """
    creds_b64 = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_B64")
    if not creds_b64:
        msg = "Missing GOOGLE_CALENDAR_CREDENTIALS_B64 environment variable"
        logger.error(msg)
        if fail_silently:
            return None
        raise RuntimeError(msg)

    try:
        decoded = base64.b64decode(creds_b64).decode('utf-8')
        info = json.loads(decoded)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        if IMPERSONATE_USER:
            credentials = credentials.with_subject(IMPERSONATE_USER)
        service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
        return service
    except Exception as e:
        logger.error(f"Failed to initialize Calendar service: {e}")
        if fail_silently:
            return None
        raise RuntimeError("Could not connect to Google Calendar API")


def _parse_iso(dt_str: str) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware datetime."""
    if dt_str.endswith('Z'):
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    else:
        dt = datetime.fromisoformat(dt_str)
    return dt


def _format_iso(dt: datetime) -> str:
    """Serialize a datetime to ISO-8601 with timezone offset."""
    return dt.astimezone(timezone.utc).isoformat()


def _query_busy(service, time_min: str, time_max: str) -> List[Dict]:
    """Return list of busy intervals from Google FreeBusy API."""
    body = {
        'timeMin': time_min,
        'timeMax': time_max,
        'timeZone': TIMEZONE,
        'items': [{'id': CALENDAR_ID}]
    }
    resp = service.freebusy().query(body=body).execute()
    return resp['calendars'][CALENDAR_ID].get('busy', [])


def get_available_time_slots(
    start_date: str,
    end_date: str,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    min_buffer_minutes: int = 0,
    max_results: Optional[int] = None,
    working_hours_only: bool = False
) -> Dict:
    """
    List available time slots between start_date and end_date.
    Returns dict with keys: status, slots, message.
    """
    try:
        service = get_calendar_service()
        logger.info("Querying free/busy intervals...")
        busy = _query_busy(service, start_date, end_date)

        start_dt = _parse_iso(start_date)
        end_dt = _parse_iso(end_date)
        step = timedelta(minutes=duration_minutes)
        buffer_delta = timedelta(minutes=min_buffer_minutes)
        slots = []
        cursor = start_dt

        while cursor + step <= end_dt:
            # enforce working hours
            if working_hours_only:
                if not (WORKDAY_START_HOUR <= cursor.hour < WORKDAY_END_HOUR):
                    cursor += step
                    continue

            slot_end = cursor + step
            # check overlap with busy intervals
            overlap = any(
                _parse_iso(b['start']) - buffer_delta < slot_end and
                _parse_iso(b['end']) + buffer_delta > cursor
                for b in busy
            )
            if not overlap:
                slots.append({'start': cursor.isoformat(), 'end': slot_end.isoformat()})
                if max_results and len(slots) >= max_results:
                    break
            cursor += step

        msg = f"{len(slots)} available slots found." if slots else "No available time slots."
        logger.info(f"{len(slots)} slots returned.")
        return {'status': 'success', 'slots': slots, 'message': msg}

    except Exception as e:
        logger.error(f"Error retrieving time slots: {e}")
        return {
            'status': 'error',
            'slots': [],
            'message': 'Failed to retrieve time slots. Please try again later.'
        }


def create_calendar_event(
    title: str,
    description: Optional[str],
    start_time: str,
    end_time: Optional[str] = None,
    location: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None
) -> Dict:
    """
    Create a calendar event with conflict checking.
    Returns dict with keys: status, message, htmlLink (on success).
    """
    try:
        service = get_calendar_service()

        # parse times
        start_dt = _parse_iso(start_time)
        if not end_time:
            end_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)
        else:
            end_dt = _parse_iso(end_time)
        start_iso = _format_iso(start_dt)
        end_iso = _format_iso(end_dt)

        # conflict check
        busy = _query_busy(service, start_iso, end_iso)
        if any(_parse_iso(b['start']) < end_dt and _parse_iso(b['end']) > start_dt for b in busy):
            return {'status': 'error', 'message': 'This time slot is already occupied.'}

        # build description
        desc = (description or "No agenda provided.").strip()
        contact_details = []
        if contact_name: contact_details.append(f"👤 {contact_name}")
        if contact_email: contact_details.append(f"📧 {contact_email}")
        if contact_phone: contact_details.append(f"📞 {contact_phone}")
        if contact_details:
            desc += "\n\nContact Info:\n" + "\n".join(contact_details)

        event_body = {
            'summary': title,
            'description': desc,
            'start': {'dateTime': start_iso, 'timeZone': TIMEZONE},
            'end': {'dateTime': end_iso, 'timeZone': TIMEZONE},
            'location': location or ""
        }

        created = service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
        link = created.get('htmlLink', '')
        logger.info(f"Event created: {link}")
        return {'status': 'success', 'message': f"Event scheduled: {link}", 'htmlLink': link}

    except Exception as e:
        logger.error(f"Failed to create calendar event: {e}")
        return {
            'status': 'error',
            'message': 'Could not schedule event at this time. Please try again.'
        }
