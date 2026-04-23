import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from repo root
load_dotenv()

API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
HOME_ADDRESS = os.getenv("HOME_ADDRESS")
WORK_ADDRESS = os.getenv("WORK_ADDRESS")
CSV_PATH = Path(os.getenv("CSV_PATH", "commute_times.csv"))

# Tracking window: Tue(1)–Thu(3), mornings 6–10, evenings 15–19 (local time)
TRACKED_WEEKDAYS = {1, 2, 3}  # Monday=0 … Sunday=6
MORNING_WINDOW = (6, 10)   # to_work:  6:00 AM – 9:59 AM
EVENING_WINDOW = (15, 19)  # to_home:  3:00 PM – 6:59 PM

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def detect_direction(now: datetime) -> str | None:
    """Return 'to_work', 'to_home', or None when outside a tracked window."""
    hour = now.hour
    if MORNING_WINDOW[0] <= hour < MORNING_WINDOW[1]:
        return "to_work"
    if EVENING_WINDOW[0] <= hour < EVENING_WINDOW[1]:
        return "to_home"
    return None


def parse_duration_seconds(duration_str: str) -> int:
    """Parse a Routes API duration string like '1238s' into integer seconds."""
    if not duration_str.endswith("s"):
        raise ValueError(f"Unexpected duration format: {duration_str}")
    return int(float(duration_str[:-1]))

def fetch_commute_time(direction: str) -> dict:
    if not API_KEY:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set in .env")
    if not HOME_ADDRESS or not WORK_ADDRESS:
        raise RuntimeError("HOME_ADDRESS or WORK_ADDRESS missing in .env")

    origin, destination = (
        (HOME_ADDRESS, WORK_ADDRESS) if direction == "to_work"
        else (WORK_ADDRESS, HOME_ADDRESS)
    )

    departure_time_utc = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )

    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "trafficModel": "BEST_GUESS",
        "departureTime": departure_time_utc,
        "languageCode": "en-US",
        "units": "METRIC",
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.staticDuration,routes.distanceMeters",
    }

    resp = requests.post(ROUTES_URL, json=body, headers=headers, timeout=10)
    if resp.status_code != 200:
        print("Routes API error:", resp.status_code, resp.text)
        resp.raise_for_status()
    data = resp.json()

    try:
        route = data["routes"][0]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Routes API response: {data}") from e

    if "duration" not in route:
        raise RuntimeError(f"Routes API response missing 'duration': {route}")

    duration_traffic_sec = parse_duration_seconds(route["duration"])
    static_duration_sec = parse_duration_seconds(
        route.get("staticDuration", route["duration"])
    )
    distance_m = route["distanceMeters"]

    now_local = datetime.now()

    return {
        "timestamp": now_local.isoformat(timespec="seconds"),
        "weekday": now_local.strftime("%A"),
        "direction": direction,
        "origin_input": origin,
        "destination_input": destination,
        "distance_m": distance_m,
        "duration_sec": static_duration_sec,
        "duration_text": f"{round(static_duration_sec / 60)} min (no traffic)",
        "duration_in_traffic_sec": duration_traffic_sec,
        "duration_in_traffic_text": f"{round(duration_traffic_sec / 60)} min (with traffic)",
    }

def append_to_csv(row: dict):
    new_file = not CSV_PATH.exists()
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new_file:
            writer.writeheader()
        writer.writerow(row)

def main():
    parser = argparse.ArgumentParser(description="Log commute times via Google Routes API.")
    parser.add_argument(
        "--direction",
        choices=["to_work", "to_home"],
        default=None,
        help="Trip direction. Auto-detected from current time if omitted.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even outside the scheduled time window / tracked weekdays.",
    )
    args = parser.parse_args()

    now = datetime.now()

    direction = args.direction
    if direction is None:
        direction = detect_direction(now)
        if direction is None:
            if args.force:
                print(
                    "Warning: outside a tracked time window, but --force was set. "
                    "Defaulting to 'to_work'.",
                    file=sys.stderr,
                )
                direction = "to_work"
            else:
                print(
                    f"Skipping: current time ({now.strftime('%H:%M')}) is outside "
                    f"the morning ({MORNING_WINDOW[0]}–{MORNING_WINDOW[1]}) and "
                    f"evening ({EVENING_WINDOW[0]}–{EVENING_WINDOW[1]}) windows.",
                    file=sys.stderr,
                )
                sys.exit(0)

    if not args.force and now.weekday() not in TRACKED_WEEKDAYS:
        print(
            f"Skipping: {now.strftime('%A')} is not a tracked weekday (Tue–Thu).",
            file=sys.stderr,
        )
        sys.exit(0)

    row = fetch_commute_time(direction)
    append_to_csv(row)
    label = "→ work" if direction == "to_work" else "→ home"
    print(
        f"[{row['timestamp']}] {row['weekday']} {label}: "
        f"{row['duration_in_traffic_text']} "
        f"(baseline {row['duration_text']}, distance {row['distance_m']} m)"
    )

if __name__ == "__main__":
    main()