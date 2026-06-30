#!/usr/bin/env python3
"""
Slack Follow-Up Bot
===================

Chases people who haven't responded to a form/survey/sheet, on your behalf.

You give it two files:
  1. The full list of people who SHOULD respond (employees).
  2. The current responses sheet (whoever has responded so far).

It figures out who's still missing, DMs each of them a follow-up in Slack,
remembers who it has already nudged (and how many times), waits a set interval
before nudging again, and stops once everyone has responded -- then DMs YOU a
summary.

Safe by default: it runs in DRY-RUN mode (prints what it WOULD send) unless you
pass --send. So you can test the matching before a single message goes out.

Run it on a schedule (cron / GitHub Actions / etc.) and it becomes fully
hands-off: each run re-reads the latest responses, nudges only the people still
due, and goes quiet when the list is clear.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# Slack is only imported when actually sending, so dry-run needs no token.
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    WebClient = None
    SlackApiError = Exception


# --------------------------------------------------------------------------- #
#  Follow-up message templates -- one per round. Edit these to your voice.
#  {name} is filled in with the person's first name.
#  NOTE: If a "Message" column exists in the employee sheet, it will be used
#  instead of these templates.
# --------------------------------------------------------------------------- #
MESSAGE_ROUNDS = [
    # Round 1 -- gentle
    "Hi {name}! Quick nudge -- we're still waiting on your response for the "
    "form. Whenever you get a sec, would you mind filling it in? Thanks a lot!",
    # Round 2 -- a touch firmer
    "Hey {name}, following up again on the form -- we'd really like to get "
    "yours in. It only takes a minute. Thank you!",
    # Round 3 -- final
    "Hi {name}, last reminder from me on the pending form. We're closing the "
    "loop on this soon, so it'd be great to have your response in. Appreciate it!",
]


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def norm_email(value) -> str:
    return str(value).strip().lower() if pd.notna(value) else ""


def norm_name(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)   # drop punctuation
    s = re.sub(r"\s+", " ", s)          # collapse whitespace
    return s


def name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two names (0.0 to 1.0).
    
    Handles cases like:
    - "Dhanpat Singh Meena" vs "Dhanpat Meena" (missing middle name)
    - "John Smith" vs "John R Smith" (added middle initial)
    - "Mary Jane Watson" vs "Mary Watson" (dropped middle name)
    """
    n1_parts = norm_name(name1).split()
    n2_parts = norm_name(name2).split()
    
    if not n1_parts or not n2_parts:
        return 0.0
    
    # Exact match
    if " ".join(n1_parts) == " ".join(n2_parts):
        return 1.0
    
    # Check if first name and last name match (ignore middle names)
    if len(n1_parts) >= 2 and len(n2_parts) >= 2:
        if n1_parts[0] == n2_parts[0] and n1_parts[-1] == n2_parts[-1]:
            return 0.9  # High confidence if first and last match
    
    # Check if first name matches and last name is contained
    if n1_parts[0] == n2_parts[0]:
        # Check if any last name parts match
        n1_last = set(n1_parts[1:])
        n2_last = set(n2_parts[1:])
        if n1_last & n2_last:  # Intersection
            return 0.8
    
    # Check if all parts of shorter name are in longer name
    shorter = n1_parts if len(n1_parts) < len(n2_parts) else n2_parts
    longer = n2_parts if len(n1_parts) < len(n2_parts) else n1_parts
    
    if all(part in longer for part in shorter):
        return 0.85
    
    return 0.0


def first_name(full_name: str) -> str:
    full_name = str(full_name).strip()
    return full_name.split()[0] if full_name else "there"


def read_table(path: str) -> pd.DataFrame:
    """Read a CSV or Excel file -- from a local path OR a web URL.

    A URL is treated as CSV (e.g. a Google Sheet 'Publish to web -> CSV' link),
    so responses can be read live with no Google login required.
    """
    if str(path).startswith(("http://", "https://")):
        try:
            return pd.read_csv(path, on_bad_lines='skip')
        except Exception as e:
            sys.exit(f"ERROR: couldn't read the responses URL.\n  {e}\n"
                     "Check the Google Sheet is published to the web as CSV and "
                     "the link is pasted correctly.")
    p = Path(path)
    if not p.exists():
        sys.exit(f"ERROR: file not found: {path}")
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p)
    return pd.read_csv(p)


def find_col(df: pd.DataFrame, override: str, keywords: list[str]) -> Optional[str]:
    """Pick a column: explicit override wins, else first name containing a keyword."""
    if override:
        if override not in df.columns:
            sys.exit(f"ERROR: column '{override}' not in {list(df.columns)}")
        return override
    for col in df.columns:
        low = str(col).strip().lower()
        if any(k in low for k in keywords):
            log(f"  Auto-detected column '{col}' for keywords {keywords}")
            return col
    return None


# --------------------------------------------------------------------------- #
#  Load people + responders
# --------------------------------------------------------------------------- #
def load_people(args) -> list[dict]:
    df = read_table(args.employees)
    log(f"  Available columns: {list(df.columns)}")
    name_col = find_col(df, args.emp_name_col, ["name"])
    email_col = find_col(df, args.emp_email_col, ["email", "e-mail", "mail"])
    slack_col = find_col(df, args.emp_slack_col, ["slack", "user id", "userid"])
    message_col = find_col(df, args.emp_message_col, ["message", "msg", "text", "note"])  # Optional message column

    if not (email_col or slack_col):
        sys.exit("ERROR: employee file needs an email column or a slack-id "
                 "column so people can be matched in Slack.")

    people = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip() if name_col else ""
        email = norm_email(row[email_col]) if email_col else ""
        slack_id = str(row[slack_col]).strip() if slack_col else ""
        custom_msg = str(row[message_col]).strip() if message_col and pd.notna(row[message_col]) else ""
        if not (name or email or slack_id):
            continue
        people.append({
            "name": name,
            "email": email,
            "slack_id": slack_id,
            "message": custom_msg
        })
    log(f"Loaded {len(people)} people from '{args.employees}' "
        f"(name='{name_col}', email='{email_col}', slack='{slack_col}', message='{message_col}')")
    return people


def load_responders(args) -> tuple[set, set]:
    df = read_table(args.responses)
    email_col = find_col(df, args.resp_email_col, ["email", "e-mail", "mail"])
    name_col = find_col(df, args.resp_name_col, ["name"])

    if not (email_col or name_col):
        sys.exit("ERROR: responses file needs an email column or a name column "
                 "so respondents can be identified.")

    emails, names = set(), set()
    for _, row in df.iterrows():
        if email_col:
            e = norm_email(row[email_col])
            if e:
                emails.add(e)
        if name_col:
            n = norm_name(row[name_col])
            if n:
                names.add(n)
    
    log(f"Loaded {len(emails)} responder emails / {len(names)} responder names "
        f"from '{args.responses}' (email='{email_col}', name='{name_col}')")
    
    # DEBUG: Show some samples
    if emails:
        log(f"  Sample responder emails: {list(emails)[:5]}")
    if names:
        log(f"  Sample responder names: {list(names)[:5]}")
    
    return emails, names


def has_responded(person: dict, resp_emails: set, resp_names: set) -> bool:
    # Check email match (most reliable)
    if person["email"] and person["email"] in resp_emails:
        log(f"  ✓ {person['name']} matched by email: {person['email']}")
        return True
    
    # Check exact name match
    person_norm = norm_name(person["name"])
    if person["name"] and person_norm in resp_names:
        log(f"  ✓ {person['name']} matched by exact name: {person_norm}")
        return True
    
    # Check fuzzy name match (handles missing middle names, etc.)
    if person["name"]:
        for resp_name in resp_names:
            similarity = name_similarity(person["name"], resp_name)
            if similarity >= 0.8:  # 80% confidence threshold
                log(f"  ✓ {person['name']} matched by fuzzy name (similarity: {similarity:.0%}): '{person_norm}' ≈ '{resp_name}'")
                return True
    
    # No match
    log(f"  ✗ {person['name']} NOT matched (email: {person['email']}, norm_name: {person_norm})")
    return False


# --------------------------------------------------------------------------- #
#  State (so we don't spam and we know when to stop)
# --------------------------------------------------------------------------- #
def load_state(path: str) -> dict:
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            log(f"WARN: state file '{path}' was unreadable; starting fresh.")
    return {"people": {}, "completed": False}


def save_state(path: str, state: dict):
    Path(path).write_text(json.dumps(state, indent=2))


def person_key(person: dict) -> str:
    return person["email"] or person["slack_id"] or norm_name(person["name"])


def is_due(record: dict, min_hours: float, max_rounds: int, now: datetime) -> bool:
    """Has enough time passed, and are we still under the round cap?"""
    if record.get("rounds", 0) >= max_rounds:
        return False
    last = record.get("last_contacted")
    if not last:
        return True
    last_dt = datetime.fromisoformat(last)
    return now - last_dt >= timedelta(hours=min_hours)


# --------------------------------------------------------------------------- #
#  Slack
# --------------------------------------------------------------------------- #
class Slack:
    def __init__(self, token: Optional[str], send: bool):
        self.send = send
        self.client = None
        self._email_cache = {}
        if send:
            if WebClient is None:
                sys.exit("ERROR: slack_sdk not installed. Run: pip install slack_sdk")
            if not token:
                sys.exit("ERROR: --send requires a Slack bot token "
                         "(SLACK_BOT_TOKEN env var or --token).")
            self.client = WebClient(token=token)

    def resolve(self, person: dict) -> Optional[str]:
        """Get a Slack user ID for a person."""
        if person.get("slack_id"):
            return person["slack_id"]
        if not self.send:                       # dry-run: pretend we found them
            return f"DRYRUN:{person.get('email') or person.get('name')}"
        email = person.get("email")
        if not email:
            return None
        if email in self._email_cache:
            return self._email_cache[email]
        try:
            resp = self.client.users_lookupByEmail(email=email)
            uid = resp["user"]["id"]
            self._email_cache[email] = uid
            return uid
        except SlackApiError as e:
            log(f"  ! could not find Slack user for {email}: "
                f"{e.response['error']}")
            self._email_cache[email] = None
            return None

    def dm(self, user_id: str, text: str) -> bool:
        if not self.send:
            log(f"  [dry-run] would DM {user_id}: {text}")
            return True
        try:
            # Send as user (not bot) by using user token and not setting as_user
            self.client.chat_postMessage(channel=user_id, text=text)
            return True
        except SlackApiError as e:
            log(f"  ! failed to DM {user_id}: {e.response['error']}")
            return False


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Slack follow-up bot")
    ap.add_argument("--employees", required=True, help="CSV/XLSX: full list of people")
    ap.add_argument("--responses", required=True, help="CSV/XLSX: responses so far")
    ap.add_argument("--state", default="followup_state.json", help="state file path")
    ap.add_argument("--send", action="store_true",
                    help="actually send DMs (default is dry-run / preview only)")
    ap.add_argument("--force", action="store_true",
                    help="send messages even to people who have already responded (for testing)")
    ap.add_argument("--token", default=os.environ.get("SLACK_BOT_TOKEN"),
                    help="Slack bot token (or set SLACK_BOT_TOKEN)")
    ap.add_argument("--owner", default=os.environ.get("SLACK_OWNER_ID"),
                    help="your Slack user ID, for the 'all done' summary DM")
    ap.add_argument("--max-rounds", type=int, default=3, help="max nudges per person")
    ap.add_argument("--min-hours", type=float, default=24,
                    help="min hours between nudges to the same person")
    # column overrides (optional -- auto-detected otherwise)
    ap.add_argument("--emp-name-col", default="")
    ap.add_argument("--emp-email-col", default="")
    ap.add_argument("--emp-slack-col", default="")
    ap.add_argument("--emp-message-col", default="", help="custom message column")
    ap.add_argument("--custom-message", default="", 
                    help="override message for all employees (use {name} for first name)")
    ap.add_argument("--resp-email-col", default="")
    ap.add_argument("--resp-name-col", default="")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    mode = "SEND" if args.send else "DRY-RUN (no messages sent)"
    log(f"=== Follow-up run | mode: {mode} ===")

    people = load_people(args)
    resp_emails, resp_names = load_responders(args)
    state = load_state(args.state)
    slack = Slack(args.token, args.send)

    if args.force:
        log("FORCE MODE: Will send to everyone, ignoring response status")
        pending = people
    else:
        pending = [p for p in people if not has_responded(p, resp_emails, resp_names)]
    
    responded = len(people) - len(pending)
    log(f"Status: {responded}/{len(people)} responded, {len(pending)} still pending.")

    # Everyone's in -> notify owner once, mark complete, exit.
    if not pending:
        log("Everyone has responded.")
        if not state.get("completed"):
            msg = (f":white_check_mark: All {len(people)} people have now "
                   f"responded to the form. Follow-ups complete.")
            if args.owner:
                uid = slack.resolve({"slack_id": args.owner})
                slack.dm(uid, msg)
            else:
                log("  (no --owner set, so not sending a summary DM) " + msg)
            state["completed"] = True
            if args.send:
                save_state(args.state, state)
        return

    state["completed"] = False   # reset if new pending people appeared
    nudged = skipped = unreachable = 0

    for p in pending:
        key = person_key(p)
        rec = state["people"].setdefault(key, {"rounds": 0, "last_contacted": None,
                                               "name": p["name"]})
        if not is_due(rec, args.min_hours, args.max_rounds, now):
            reason = ("hit max rounds" if rec["rounds"] >= args.max_rounds
                      else "nudged too recently")
            log(f"- skip {p['name'] or key} ({reason})")
            skipped += 1
            continue

        uid = slack.resolve(p)
        if not uid:
            log(f"- can't reach {p['name'] or key} (no Slack match)")
            unreachable += 1
            continue

        # Use custom message if available, otherwise use round-based template
        if args.custom_message:
            text = args.custom_message.format(name=first_name(p["name"]))
        elif p.get("message"):
            text = p["message"].format(name=first_name(p["name"]))
        else:
            round_idx = min(rec["rounds"], len(MESSAGE_ROUNDS) - 1)
            text = MESSAGE_ROUNDS[round_idx].format(name=first_name(p["name"]))
        
        if slack.dm(uid, text):
            rec["rounds"] += 1
            rec["last_contacted"] = now.isoformat()
            log(f"+ nudged {p['name'] or key} (round {rec['rounds']})")
            nudged += 1

    if args.send:
        save_state(args.state, state)
    log(f"=== Done: {nudged} nudged, {skipped} skipped, "
        f"{unreachable} unreachable, {len(pending)} still pending ===")


if __name__ == "__main__":
    main()
