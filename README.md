# Commute Tracker (Windows)

Logs Google Maps driving time (with live traffic) between home and work into a CSV,
To work: every 10 minutes on Tue–Thu mornings between 6AM to 10 AM PST.
Return to Home: every 10 minutes on Tue–Thu afternoon between 3PM to 7 PM PST.

## Setup

1. Create a Google Cloud project, enable **Routes API** or **Distance Matrix API (Legacy)**.
2. Create an API key and put it in `.env` as `GOOGLE_MAPS_API_KEY`.
3. Copy `.env.example` to `.env` and fill in values.
4. Create venv and install deps: