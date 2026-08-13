import httpx
from datetime import date, timedelta
from server.config import settings


async def get_athlete_profile() -> dict:
    """Full athlete profile with FTP, LTHR, zones, and MMP model."""
    settings.validate()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}",
            auth=settings.auth(),
            timeout=15,
        )
        r.raise_for_status()
    a = r.json()

    ftp, lthr, max_hr, mmp, vo2max = None, None, None, None, None
    ftp_run, lthr_run = None, None
    for s in a.get("sportSettings", []):
        types = s.get("types", [])
        if "Ride" in types:
            ftp = s.get("ftp")
            lthr = s.get("lthr")
            max_hr = s.get("max_hr")
            mmp = s.get("mmp_model")
            vo2max = s.get("custom_field_values", {}).get("VO2MaxGarmin")
        elif "Run" in types:
            ftp_run = s.get("ftp")
            lthr_run = s.get("lthr")

    weight = a.get("icu_weight") or a.get("weight")
    return {
        "name": a.get("name"),
        "athlete_id": a.get("id"),
        "weight_kg": weight,
        "height_cm": a.get("height"),
        "resting_hr_bpm": a.get("icu_resting_hr"),
        "cycling_ftp_w": ftp,
        "cycling_lthr_bpm": lthr,
        "cycling_max_hr_bpm": max_hr,
        "cycling_wpkg": round(ftp / weight, 2) if ftp and weight else None,
        "vo2max_garmin": vo2max,
        "mmp_model": {
            "cp_w": mmp.get("criticalPower"),
            "wprime_j": mmp.get("wPrime"),
            "pmax_w": mmp.get("pMax"),
            "ftp_estimate_w": mmp.get("ftp"),
        } if mmp else None,
        "run_ftp_w": ftp_run,
        "run_lthr_bpm": lthr_run,
        "plan": a.get("plan"),
    }


async def get_upcoming_events(days: int = 90) -> list[dict]:
    """Type A/B/C races and events on the calendar for the next N days."""
    settings.validate()
    oldest = date.today().isoformat()
    newest = (date.today() + timedelta(days=days)).isoformat()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/events",
            auth=settings.auth(),
            params={"oldest": oldest, "newest": newest, "category": "RACE"},
            timeout=15,
        )
        r.raise_for_status()
    return [
        {
            "name": e.get("name"),
            "date": e.get("start_date_local", "")[:10],
            "category": e.get("category"),
            "distance_km": e.get("distance"),
            "description": e.get("description"),
            "days_until": (
                date.fromisoformat(e.get("start_date_local", date.today().isoformat())[:10])
                - date.today()
            ).days,
        }
        for e in r.json()
    ]


async def get_power_zones() -> dict:
    """Power zones calculated from cycling FTP."""
    settings.validate()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/sport-settings/Ride",
            auth=settings.auth(),
            timeout=15,
        )
        r.raise_for_status()
    s = r.json()
    ftp = s.get("ftp")
    if not ftp:
        return {"error": "FTP not configured in intervals.icu"}
    return {
        "ftp_w": ftp,
        "zones": {
            "Z1_recovery":      f"< {round(ftp * 0.55)}W",
            "Z2_endurance":     f"{round(ftp * 0.55)}-{round(ftp * 0.75)}W",
            "Z3_tempo":         f"{round(ftp * 0.75)}-{round(ftp * 0.87)}W",
            "Z4_threshold":     f"{round(ftp * 0.87)}-{round(ftp * 1.05)}W",
            "Z5_vo2max":        f"{round(ftp * 1.05)}-{round(ftp * 1.20)}W",
            "Z6_anaerobic":     f"{round(ftp * 1.20)}-{round(ftp * 1.50)}W",
            "Z7_neuromuscular": f"> {round(ftp * 1.50)}W",
        },
    }
