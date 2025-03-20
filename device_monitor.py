"""Device monitor script - used to ensure that class devices remain online."""

import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from dateutil import parser
from supabase import create_client, Client
from typing import List, Set

# Load environment variables from .env file
load_dotenv()

# Constants
DEVICE_IDS = [
    "jasoncurtis-outdoor",
    "jasoncurtis-co2-temperature-airquality-battery",
    "jasoncurtis-co2_ndir_scd30-pressure-temperature-humidity",
]
HOURS_THRESHOLD = 1


def get_all_active_devices(
    supabase: Client, hours_threshold: int = HOURS_THRESHOLD
) -> Set[str]:
    """
    Get all devices that have reported data in the last hour.
    Returns a set of device IDs.
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_threshold)

    # Query for all recent data points
    query = (
        supabase.table("iot")
        .select("device_id, created_at")
        .order("created_at", desc=True)
        .limit(1000)  # Get a good chunk of recent data
    )
    response = query.execute()

    if not response.data:
        return set()

    # Create a set of devices that have reported data recently
    return {
        record["device_id"]
        for record in response.data
        if parser.parse(record["created_at"]) > cutoff_time
    }


def main():
    """Check if devices have reported data recently."""
    # Initialize Supabase client
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_KEY"]
    supabase: Client = create_client(supabase_url, supabase_key)

    # Get all active devices
    active_devices = get_all_active_devices(supabase)

    print("\nAll devices reporting data in the last hour:")
    for device_id in sorted(active_devices):
        print(f"  - {device_id}")

    # Check our specific devices
    offline_devices = [
        device_id for device_id in DEVICE_IDS if device_id not in active_devices
    ]

    if offline_devices:
        print(
            f"\n❌ Monitored devices not reporting data in the last {HOURS_THRESHOLD} hour(s):"
        )
        for device_id in offline_devices:
            print(f"  - {device_id}")
        exit(1)
    else:
        print("\n✅ All monitored devices reporting data normally")
        exit(0)


if __name__ == "__main__":
    main()
