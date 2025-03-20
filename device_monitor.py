"""Device monitor script - used to ensure that class devices remain online."""

import os
from datetime import datetime, timedelta
from supabase import create_client, Client
from typing import List

# Constants
DEVICE_IDS = [
    "jasoncurtis-co2-temperature-airquality",
    "jasoncurtis-co2-temperature-airquality-battery",
    "jasoncurtis-co2_ndir_scd30-pressure-temperature-humidity",
]
HOURS_THRESHOLD = 1


def check_device_data(
    supabase: Client, device_ids: List[str], hours_threshold: int = HOURS_THRESHOLD
) -> List[str]:
    """
    Check which devices on the given list have not reported data in the last hour.
    Returns a list of device IDs that have not reported data.
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=hours_threshold)

    # Query for the latest data point for each device
    query = (
        supabase.table("device_data")
        .select("device_id, created_at")
        .in_("device_id", device_ids)
    )
    response = query.execute()

    if not response.data:
        return device_ids  # If no data found, all devices are considered offline

    # Create a set of devices that have reported data recently
    active_devices = {
        record["device_id"]
        for record in response.data
        if datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
        > cutoff_time
    }

    # Return list of devices that haven't reported data recently
    return [device_id for device_id in device_ids if device_id not in active_devices]


def main():
    """Check if devices have reported data recently."""
    # Initialize Supabase client
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_KEY"]
    supabase: Client = create_client(supabase_url, supabase_key)

    # Check device data
    offline_devices = check_device_data(supabase, DEVICE_IDS)

    if offline_devices:
        print(f"❌ Devices not reporting data in the last {HOURS_THRESHOLD} hour(s):")
        for device_id in offline_devices:
            print(f"  - {device_id}")
        exit(1)
    else:
        print("✅ All devices reporting data normally")
        exit(0)


if __name__ == "__main__":
    main()
