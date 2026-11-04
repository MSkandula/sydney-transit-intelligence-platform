"""Shared config for ingestion scripts. Loads secrets from .env — never hardcode a key."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TFNSW_API_KEY = os.environ.get("TFNSW_API_KEY")

GTFS_SCHEDULE_BASE_URL = "https://api.transport.nsw.gov.au/v1/gtfs/schedule"
GTFS_REALTIME_V2_BASE_URL = "https://api.transport.nsw.gov.au/v2/gtfs/realtime"

# Phase 1 MVP scope — Sydney Trains only. Trains/Metro/Inner West Light Rail moved to
# the v2 realtime endpoint; other modes (bus/ferry/regional) are still on v1 and are
# out of scope until Phase 2 (see ROADMAP.md).
AGENCY = "sydneytrains"

REPO_ROOT = Path(__file__).resolve().parent.parent
# Overridable so a container (whose disk is wiped after every run) can use a temp dir.
LOCAL_LANDING_DIR = Path(os.environ.get("LANDING_DIR") or REPO_ROOT / "data" / "bronze")


def require_api_key() -> str:
    if not TFNSW_API_KEY:
        raise RuntimeError(
            "TFNSW_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return TFNSW_API_KEY


def auth_headers() -> dict:
    return {"Authorization": f"apikey {require_api_key()}"}
