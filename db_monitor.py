"""
db_monitor.py
-------------
Supabase-backed monitoring layer for the One Gate Dissemination system.

Responsibilities:
  - Load staff registry from staff.json
  - Insert a log row into `dissemination_log` table in Supabase after every dissemination
  - Query recap data for a custom date range for report_generator.py
"""

import os
import json
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Supabase REST helpers ────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
TABLE_NAME   = "dissemination_log"

def _headers(extra: dict = None) -> dict:
    h = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }
    if extra:
        h.update(extra)
    return h

def _table_url(table: str = TABLE_NAME) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"

# ── LID resolver ────────────────────────────────────────────────────────────

SESSION_DB = os.path.join(os.path.dirname(__file__), "session.sqlite3")

def resolve_phone(jid_str: str) -> str:
    """
    Converts a WhatsApp @lid JID to the real phone number using the
    whatsmeow_lid_map table stored in session.sqlite3.

    Examples:
        '46175226957895@lid'  →  '6285280599185'
        '6281266419227@s.whatsapp.net'  →  '6281266419227'  (already real)
        '6281266419227'  →  '6281266419227'  (no suffix)
    """
    raw = jid_str.split("@")[0].strip()

    if not jid_str.endswith("@lid"):
        return raw  # Already a real number

    try:
        conn = sqlite3.connect(SESSION_DB)
        cur  = conn.cursor()
        cur.execute("SELECT pn FROM whatsmeow_lid_map WHERE lid = ?", (raw,))
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]   # real phone number
    except Exception as e:
        logging.warning(f"LID lookup failed for {jid_str}: {e}")

    return raw  # fallback: return LID number as-is

# ── Staff registry ───────────────────────────────────────────────────────────

STAFF_FILE = os.path.join(os.path.dirname(__file__), "staff.json")

def load_staff() -> list[dict]:
    """Load staff list from staff.json. Returns [] if file is missing or empty."""
    if not os.path.exists(STAFF_FILE):
        logging.warning("staff.json not found. All senders will be logged as 'Unregistered'.")
        return []
    try:
        with open(STAFF_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logging.error(f"Failed to load staff.json: {e}")
        return []

def lookup_staff_name(sender_wa: str) -> str:
    """
    Returns the staff display name for a given WA JID or number.
    Resolves @lid JIDs to real phone numbers first via session.sqlite3.
    Returns 'Unregistered' if not found in staff.json.
    """
    clean = resolve_phone(sender_wa)   # handles @lid, @s.whatsapp.net, or plain number
    for staff in load_staff():
        registered = str(staff.get("wa_number", "")).strip()
        if registered == clean:
            return staff.get("name", "Unregistered")
    return "Unregistered"

# ── Logging ──────────────────────────────────────────────────────────────────

def log_dissemination(
    sender_wa:    str,
    sender_name:  str,
    media_type:   str | None,
    text_content: str | None,
    platforms:    list[str],
    status:       str = "success",
) -> bool:
    """
    Insert one row into the Supabase `dissemination_log` table.

    Columns stored
    --------------
    timestamp     : ISO datetime of the event
    name          : Resolved staff name (from staff.json) or 'Unregistered'
    wa_number     : Clean WA number without @suffix
    message       : Caption / text sent (truncated at 500 chars)
    media_type    : 'image', 'video', or 'text'
    platforms     : JSON string list of platforms published to
    status        : 'success', 'partial', or 'failed'
    is_registered : True if the number is in staff.json

    Returns True on success, False on error.
    """
    import requests

    if not SUPABASE_URL or not SUPABASE_KEY:
        logging.error("Supabase credentials missing — cannot log dissemination.")
        return False

    now          = datetime.now()
    ts_iso       = now.isoformat()
    staff_name   = lookup_staff_name(sender_wa)
    clean_number = sender_wa.split("@")[0].strip()
    is_registered = staff_name != "Unregistered"

    # If not registered, fall back to WhatsApp push-name
    display_name = staff_name if is_registered else (sender_name or "Unregistered")

    row = {
        "timestamp":     ts_iso,
        "name":          display_name,
        "wa_number":     clean_number,
        "message":       (text_content or "")[:500],
        "media_type":    media_type or "text",
        "platforms":     json.dumps(platforms),
        "status":        status,
        "is_registered": is_registered,
    }

    try:
        resp = requests.post(
            _table_url(),
            headers=_headers(),
            json=row,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logging.info(f"📊 Monitoring log saved → {display_name} ({clean_number})")
            return True
        else:
            logging.error(f"Supabase insert failed [{resp.status_code}]: {resp.text}")
            return False
    except Exception as e:
        logging.error(f"Failed to insert monitoring log: {e}")
        return False

# ── Recap query ──────────────────────────────────────────────────────────────

def _aggregate_rows(rows: list[dict]) -> list[dict]:
    """Aggregate raw DB rows into per-staff count dicts, sorted by count desc."""
    tally: dict[str, dict] = {}
    for r in rows:
        key = r["wa_number"]
        if key not in tally:
            tally[key] = {
                "name":          r["name"],
                "wa_number":     key,
                "is_registered": r.get("is_registered", False),
                "count":         0,
            }
        tally[key]["count"] += 1
    return sorted(tally.values(), key=lambda x: x["count"], reverse=True)


def get_recap(start_date: str, end_date: str) -> list[dict]:
    """
    Query dissemination_log for a custom datetime range.

    Parameters
    ----------
    start_date : 'YYYY-MM-DD'  (inclusive, from 00:00:00)
    end_date   : 'YYYY-MM-DD'  (inclusive, to 23:59:59)
    """
    import requests

    start_iso = f"{start_date}T00:00:00"
    end_iso   = f"{end_date}T23:59:59"

    url = (
        f"{_table_url()}"
        f"?timestamp=gte.{start_iso}"
        f"&timestamp=lte.{end_iso}"
        f"&select=name,wa_number,is_registered,timestamp"
        f"&order=timestamp.asc"
    )

    try:
        resp = requests.get(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, timeout=15)
        if resp.status_code != 200:
            logging.error(f"Supabase query failed [{resp.status_code}]: {resp.text}")
            return []
        return _aggregate_rows(resp.json())
    except Exception as e:
        logging.error(f"Failed to fetch recap: {e}")
        return []


def get_all_recap() -> tuple[list[dict], str, str]:
    """
    Fetch ALL dissemination logs ever recorded, with no date filter.

    Returns
    -------
    (rows, earliest_datetime_str, latest_datetime_str)
    where rows is the aggregated per-staff count list.
    """
    import requests

    url = (
        f"{_table_url()}"
        f"?select=name,wa_number,is_registered,timestamp"
        f"&order=timestamp.asc"
    )

    try:
        resp = requests.get(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, timeout=15)
        if resp.status_code != 200:
            logging.error(f"Supabase all-recap query failed [{resp.status_code}]: {resp.text}")
            return [], "", ""
        raw = resp.json()
        if not raw:
            return [], "", ""
        earliest = raw[0]["timestamp"][:19].replace("T", " ")
        latest   = raw[-1]["timestamp"][:19].replace("T", " ")
        return _aggregate_rows(raw), earliest, latest
    except Exception as e:
        logging.error(f"Failed to fetch all-recap: {e}")
        return [], "", ""


def get_raw_logs(start_date: str, end_date: str) -> list[dict]:
    """
    Return every individual log row in the date range (for detailed views).
    Columns: timestamp, name, wa_number, message, media_type, status
    """
    import requests

    start_iso = f"{start_date}T00:00:00"
    end_iso   = f"{end_date}T23:59:59"

    url = (
        f"{_table_url()}"
        f"?timestamp=gte.{start_iso}"
        f"&timestamp=lte.{end_iso}"
        f"&select=timestamp,name,wa_number,message,media_type,status"
        f"&order=timestamp.asc"
    )

    try:
        resp = requests.get(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, timeout=15)
        if resp.status_code != 200:
            logging.error(f"Supabase raw log query failed [{resp.status_code}]: {resp.text}")
            return []
        return resp.json()
    except Exception as e:
        logging.error(f"Failed to fetch raw logs: {e}")
        return []


def get_all_raw_logs() -> list[dict]:
    """
    Return every individual log row ever recorded (no date filter).
    """
    import requests

    url = (
        f"{_table_url()}"
        f"?select=timestamp,name,wa_number,message,media_type,status"
        f"&order=timestamp.asc"
    )

    try:
        resp = requests.get(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, timeout=15)
        if resp.status_code != 200:
            logging.error(f"Supabase all-log query failed [{resp.status_code}]: {resp.text}")
            return []
        return resp.json()
    except Exception as e:
        logging.error(f"Failed to fetch all raw logs: {e}")
        return []
