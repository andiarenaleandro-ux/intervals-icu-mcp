import httpx
from datetime import date, timedelta
from typing import Optional
from server.config import settings


def _clean_activity(a: dict) -> dict:
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "date": a.get("start_date_local", "")[:10],
        "sport": a.get("type"),
        "duration_min": round(a.get("moving_time", 0) / 60, 1),
        "distance_km": round((a.get("distance") or 0) / 1000, 2),
        "elevation_m": a.get("total_elevation_gain"),
        # Load
        "tss": a.get("icu_training_load"),
        "intensity_factor": a.get("icu_intensity"),
        # Power
        "avg_power_w": a.get("average_watts"),
        "normalized_power_w": a.get("icu_weighted_avg_watts"),
        "variability_index": a.get("icu_variability_index"),
        # HR
        "avg_hr_bpm": a.get("average_heartrate"),
        "max_hr_bpm": a.get("max_heartrate"),
        # Aerobic KPIs — already calculated by intervals
        "efficiency_factor": a.get("icu_efficiency_factor"),
        "aerobic_decoupling": a.get("icu_aerobic_decoupling"),
        # Zone distribution
        "zone_times": a.get("icu_zone_times"),
        "hr_zone_times": a.get("icu_hr_zone_times"),
        # Form at the time of the activity
        "ctl_at_activity": a.get("icu_ctl"),
        "atl_at_activity": a.get("icu_atl"),
        # Running dynamics (if applicable)
        "avg_cadence": a.get("average_cadence"),
        "avg_stride_length": a.get("average_stride_length"),
        "avg_vertical_oscillation": a.get("average_vertical_oscillation"),
        "avg_ground_contact_time": a.get("average_ground_contact_time"),
        "avg_vertical_ratio": a.get("average_vertical_ratio"),
        # Misc
        "calories": a.get("calories"),
        "perceived_exertion": a.get("perceived_exertion"),
        "feel": a.get("feel"),
        "description": a.get("description"),
    }


FIELDS = ",".join([
    "id", "name", "start_date_local", "type", "distance", "moving_time",
    "total_elevation_gain", "icu_training_load", "icu_intensity",
    "average_watts", "icu_weighted_avg_watts", "icu_variability_index",
    "average_heartrate", "max_heartrate",
    "icu_efficiency_factor", "icu_aerobic_decoupling",
    "icu_zone_times", "icu_hr_zone_times",
    "icu_ctl", "icu_atl",
    "average_cadence", "average_stride_length",
    "average_vertical_oscillation", "average_ground_contact_time",
    "average_vertical_ratio",
    "calories", "perceived_exertion", "feel", "description",
])


async def get_recent_activities(days: int = 7) -> list[dict]:
    """Fetches activities from the last N days with all intervals KPIs."""
    settings.validate()
    oldest = (date.today() - timedelta(days=days)).isoformat()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/activities",
            auth=settings.auth(),
            params={"oldest": oldest, "fields": FIELDS},
            timeout=15,
        )
        r.raise_for_status()
    return [_clean_activity(a) for a in r.json()]


async def get_activity_detail(activity_id: str) -> dict:
    """Full detail of an activity by ID, including intervals and streams."""
    settings.validate()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/activity/{activity_id}",
            auth=settings.auth(),
            params={"intervals": "true"},
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


async def get_activity_streams(
    activity_id: str,
    types: str = "watts,heart_rate,cadence,velocity_smooth,altitude"
) -> dict:
    """
    Second-by-second streams of an activity.
    types: watts, heart_rate, cadence, velocity_smooth, altitude,
           distance, latlng, temp, left_pedal_smoothness, left_torque_effectiveness
    """
    settings.validate()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/activity/{activity_id}/streams.json",
            auth=settings.auth(),
            params={"types": types},
            timeout=30,
        )
        r.raise_for_status()
    return r.json()


async def get_activity_intervals(activity_id: str) -> list[dict]:
    """Laps/intervals of an activity. Useful for structured sets."""
    settings.validate()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/activity/{activity_id}/intervals",
            auth=settings.auth(),
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


async def get_activities_by_sport(sport_type: str, days: int = 30) -> list[dict]:
    """
    Filters activities by sport over the last N days.
    sport_type: 'Ride', 'Run', 'Swim', 'VirtualRide', 'TrailRun'
    """
    settings.validate()
    oldest = (date.today() - timedelta(days=days)).isoformat()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/activities",
            auth=settings.auth(),
            params={"oldest": oldest, "fields": FIELDS},
            timeout=15,
        )
        r.raise_for_status()
    filtered = [a for a in r.json() if a.get("type") == sport_type]
    return [_clean_activity(a) for a in filtered]


async def create_manual_activity(
    name: str,
    sport_type: str,
    start_date_local: str,
    moving_time_secs: int,
    distance_m: Optional[float] = None,
    description: Optional[str] = None,
    avg_power_w: Optional[float] = None,
    avg_hr_bpm: Optional[float] = None,
    calories: Optional[int] = None,
    trainer: bool = False,
) -> dict:
    """
    Creates a manual activity in intervals.icu.
    start_date_local: 'YYYY-MM-DDTHH:MM:SS'
    """
    settings.validate()
    payload: dict = {
        "name": name,
        "type": sport_type,
        "start_date_local": start_date_local,
        "moving_time": moving_time_secs,
    }
    if distance_m is not None: payload["distance"] = distance_m
    if description: payload["description"] = description
    if avg_power_w is not None: payload["icu_weighted_avg_watts"] = avg_power_w
    if avg_hr_bpm is not None: payload["average_heartrate"] = avg_hr_bpm
    if calories is not None: payload["calories"] = calories
    if trainer: payload["trainer"] = True

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.base_url}/athlete/{settings.athlete_id}/activities/manual",
            auth=settings.auth(),
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


async def update_activity(
    activity_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    perceived_exertion: Optional[int] = None,
    feel: Optional[int] = None,
) -> dict:
    """
    Updates fields of an existing activity.
    perceived_exertion and feel: 1-10 scale.
    """
    settings.validate()
    payload = {}
    if name: payload["name"] = name
    if description is not None: payload["description"] = description
    if perceived_exertion is not None: payload["perceived_exertion"] = perceived_exertion
    if feel is not None: payload["feel"] = feel

    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{settings.base_url}/activity/{activity_id}",
            auth=settings.auth(),
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
    return r.json()
