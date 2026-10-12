
# -*- coding: utf-8 -*-

import json
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request


KEY_FILE = "/etc/odoo/google/service-account.json"
CALENDAR_ID = "hhvida@gmail.com"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly"
]


def main():
    credentials = service_account.Credentials.from_service_account_file(
        KEY_FILE,
        scopes=SCOPES,
    )
    credentials.refresh(Request())

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    end = now + timedelta(days=60)

    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{quote(CALENDAR_ID, safe='')}/events"
    )

    events = []
    page_token = None

    while True:
        params = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": "true",
            "maxResults": 250,
        }

        if page_token:
            params["pageToken"] = page_token

        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {credentials.token}"
            },
            params=params,
            timeout=20,
        )
        response.raise_for_status()

        data = response.json()

        for event in data.get("items", []):
            description = event.get("description") or ""

            
            # Identificar reservas generadas por Meta Business Agent.
            required_markers = (
                "Business name:",
                "Customer name:",
                "Customer phone:",
                "Chat with customer:",
                "Booking notes:",
            )

            if not all(
                marker in description
                for marker in required_markers
            ):
                continue


            if event.get("status") == "cancelled":
                continue

            if not event.get("start", {}).get("dateTime"):
                continue

            if not event.get("end", {}).get("dateTime"):
                continue

            events.append(event)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    json.dump(events, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
