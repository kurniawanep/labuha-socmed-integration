"""
report_generator.py
-------------------
CLI tool to generate dissemination recap from Supabase.

Usage
-----
  # Recap for ALL records ever (default)
  python report_generator.py

  # Recap for a custom date range
  python report_generator.py --from 2026-07-01 --to 2026-07-13

  # Show every individual log row
  python report_generator.py --detail
  python report_generator.py --from 2026-07-01 --to 2026-07-13 --detail

  # Show staff registry
  python report_generator.py --list-staff

Output
------
  - Formatted table printed to terminal
  - CSV file saved: recap_all.csv  or  recap_YYYY-MM-DD_YYYY-MM-DD.csv
"""

import sys
import csv
import os
import argparse
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

try:
    from db_monitor import (
        get_recap, get_all_recap,
        get_raw_logs, get_all_raw_logs,
        load_staff,
    )
    from supabase_uploader import SupabaseUploader
except ImportError as e:
    print(f"Import error: {e}. Make sure all modules are in the same directory.")
    sys.exit(1)

# ── Display helpers ──────────────────────────────────────────────────────────

def fmt_period(start: str, end: str) -> str:
    """Format period label using full datetime strings."""
    return f"{start}  ->  {end}"

def print_summary_table(rows: list[dict], start_dt: str, end_dt: str):
    label = fmt_period(start_dt, end_dt)
    width = 72
    print()
    print("=" * width)
    print(f"  [RECAP]  DISSEMINATION RECAP")
    print(f"  Period : {label}")
    print("=" * width)

    if not rows:
        print("  (No dissemination logs found for this period.)")
        print("=" * width)
        return

    header = f"  {'#':<4} {'Name':<25} {'WA Number':<18} {'Sent':>6}  Status"
    print(header)
    print("-" * width)

    for i, r in enumerate(rows, 1):
        badge = "[OK] Registered" if r["is_registered"] else "[!] Unregistered"
        print(f"  {i:<4} {r['name']:<25} {r['wa_number']:<18} {r['count']:>6}  {badge}")

    total = sum(r["count"] for r in rows)
    print("-" * width)
    print(f"  {'TOTAL':<52} {total:>6}")
    print("=" * width)
    print()

def print_detail_table(logs: list[dict], start_dt: str, end_dt: str):
    label = fmt_period(start_dt, end_dt)
    width = 92
    print()
    print("=" * width)
    print(f"  [DETAIL LOG]")
    print(f"  Period : {label}")
    print("=" * width)

    if not logs:
        print("  (No logs found for this period.)")
        print("=" * width)
        return

    print(f"  {'Timestamp':<22} {'Name':<22} {'WA Number':<16} {'Type':<8} {'Message'}")
    print("-" * width)

    for r in logs:
        ts  = r.get("timestamp", "")[:19].replace("T", " ")
        msg = (r.get("message") or "")[:28]
        if len(r.get("message") or "") > 28:
            msg += "..."
        print(f"  {ts:<22} {r.get('name','?'):<22} {r.get('wa_number','?'):<16} {r.get('media_type','?'):<8} {msg}")

    print("=" * width)
    print(f"  Total rows: {len(logs)}")
    print()

def export_summary_csv(rows: list[dict], logs: list[dict], filename: str) -> str:
    """
    Export CSV with:
    - Individual rows: Timestamp | Name | WA Number | Media Type
    - Count summary per person at the bottom
    """
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)

        # Section 1: individual submissions
        w.writerow(["Timestamp", "Name", "WA Number", "Media Type"])
        for r in logs:
            ts = (r.get("timestamp") or "")[:19].replace("T", " ")
            w.writerow([
                ts,
                r.get("name", ""),
                r.get("wa_number", ""),
                r.get("media_type", ""),
            ])

        # Section 2: count summary
        w.writerow([])
        w.writerow(["-- RECAP PER STAFF --", "", "", ""])
        w.writerow(["Name", "WA Number", "Total Sent", "Registered"])
        for r in rows:
            w.writerow([
                r["name"],
                r["wa_number"],
                r["count"],
                "Yes" if r["is_registered"] else "No",
            ])
        if rows:
            w.writerow([])
            w.writerow(["TOTAL", "", sum(r["count"] for r in rows), ""])

    return os.path.abspath(filename)

def export_detail_csv(logs: list[dict], filename: str) -> str:
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Timestamp", "Name", "WA Number", "Media Type", "Message", "Status"])
        for r in logs:
            ts = (r.get("timestamp") or "")[:19].replace("T", " ")
            w.writerow([
                ts,
                r.get("name", ""),
                r.get("wa_number", ""),
                r.get("media_type", ""),
                r.get("message", ""),
                r.get("status", ""),
            ])
    return os.path.abspath(filename)

def cmd_list_staff():
    staff = load_staff()
    print()
    print("=" * 50)
    print("  REGISTERED STAFF  (staff.json)")
    print("=" * 50)
    if not staff:
        print("  (No staff entries found.)")
    for i, s in enumerate(staff, 1):
        print(f"  {i}. {s.get('name', '?'):<25}  {s.get('wa_number', '?')}")
    print("=" * 50)
    print()

def cmd_cleanup_storage(older_than_days: int):
    print(f"Deleting Supabase files older than {older_than_days} days ...")
    uploader = SupabaseUploader()
    total_deleted, total_failed = [], []
    for folder in ("stories", "originals", "videos"):
        result = uploader.delete_old_files(folder, older_than_days)
        total_deleted.extend(result["deleted"])
        total_failed.extend(result["failed"])

    print(f"  Deleted : {len(total_deleted)} files")
    for p in total_deleted:
        print(f"    - {p}")
    if total_failed:
        print(f"  Failed  : {len(total_failed)} files")
        for p in total_failed:
            print(f"    ! {p}")
    print("Done.")

def cmd_list_storage():
    uploader = SupabaseUploader()
    files = uploader.list_storage_usage()
    width = 70
    print()
    print("=" * width)
    print("  SUPABASE STORAGE CONTENTS")
    print("=" * width)
    if not files:
        print("  (No files found.)")
        print("=" * width)
        return
    print(f"  {'Folder':<12} {'Age(days)':>9}  {'Size(KB)':>9}  Name")
    print("-" * width)
    total_kb = 0
    for f in sorted(files, key=lambda x: x["age_days"], reverse=True):
        print(f"  {f['folder']:<12} {f['age_days']:>9}  {f['size_kb']:>9}  {f['name']}")
        total_kb += f['size_kb']
    print("-" * width)
    print(f"  Total: {len(files)} files,  {total_kb:.1f} KB  ({total_kb/1024:.2f} MB)")
    print("=" * width)
    print()

# ── Argument parsing ─────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        prog="report_generator.py",
        description="Generate dissemination recap and manage Supabase storage.",
    )
    parser.add_argument(
        "--from", dest="start_date", metavar="YYYY-MM-DD",
        help="Start date (inclusive). Omit to include ALL records.",
    )
    parser.add_argument(
        "--to", dest="end_date", metavar="YYYY-MM-DD",
        help="End date (inclusive). Omit to include ALL records.",
    )
    parser.add_argument(
        "--detail", action="store_true",
        help="Show every individual log entry instead of the summary.",
    )
    parser.add_argument(
        "--list-staff", action="store_true",
        help="Print all registered staff from staff.json and exit.",
    )
    parser.add_argument(
        "--list-storage", action="store_true",
        help="List all files in Supabase storage with sizes and ages.",
    )
    parser.add_argument(
        "--cleanup-storage", dest="cleanup_days", metavar="DAYS", type=int, nargs="?", const=7,
        help="Delete Supabase files older than DAYS days (default: 7).",
    )
    return parser.parse_args()

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if args.list_staff:
        cmd_list_staff()
        return

    if args.list_storage:
        cmd_list_storage()
        return

    if args.cleanup_days is not None:
        cmd_cleanup_storage(args.cleanup_days)
        return

    use_date_filter = bool(args.start_date or args.end_date)

    if use_date_filter:
        today = date.today().isoformat()
        start = args.start_date or today
        end   = args.end_date   or today

        # Validate
        for label, val in [("--from", start), ("--to", end)]:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                print(f"Invalid {label} date '{val}'. Use YYYY-MM-DD format.")
                sys.exit(1)

        if start > end:
            print(f"--from ({start}) must not be after --to ({end}).")
            sys.exit(1)

        # Full datetime strings for display
        start_dt = f"{start} 00:00:00"
        end_dt   = f"{end} 23:59:59"

        print(f"Fetching data from Supabase  [{start_dt}  ->  {end_dt}] ...")

        if args.detail:
            logs = get_raw_logs(start, end)
            print_detail_table(logs, start_dt, end_dt)
            if logs:
                fname = f"log_detail_{start}_{end}.csv"
                csv_path = export_detail_csv(logs, fname)
                print(f"Detail CSV exported: {csv_path}")
            else:
                print("No data to export.")
        else:
            rows = get_recap(start, end)
            logs = get_raw_logs(start, end)   # needed for per-row timestamps in CSV
            print_summary_table(rows, start_dt, end_dt)
            if rows:
                fname = f"recap_{start}_{end}.csv"
                csv_path = export_summary_csv(rows, logs, fname)
                print(f"Summary CSV exported: {csv_path}")
            else:
                print("No data to export.")

    else:
        # No date filter — fetch ALL records
        print("Fetching ALL records from Supabase ...")

        if args.detail:
            logs = get_all_raw_logs()
            start_dt = (logs[0]["timestamp"][:19].replace("T", " ")) if logs else "-"
            end_dt   = (logs[-1]["timestamp"][:19].replace("T", " ")) if logs else "-"
            print_detail_table(logs, start_dt, end_dt)
            if logs:
                csv_path = export_detail_csv(logs, "log_detail_all.csv")
                print(f"Detail CSV exported: {csv_path}")
            else:
                print("No data to export.")
        else:
            rows, earliest, latest = get_all_recap()
            logs = get_all_raw_logs()          # needed for per-row timestamps in CSV
            start_dt = earliest or "-"
            end_dt   = latest   or "-"
            print_summary_table(rows, start_dt, end_dt)
            if rows:
                csv_path = export_summary_csv(rows, logs, "recap_all.csv")
                print(f"Summary CSV exported: {csv_path}")
            else:
                print("No data to export.")

if __name__ == "__main__":
    main()
