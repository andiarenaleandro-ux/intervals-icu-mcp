import httpx
from datetime import date, timedelta
from server.config import settings


async def get_fitness_stats(days: int = 42) -> list[dict]:
    """
    CTL/ATL/TSB history for the last N days from wellness.
    Default 42 days to see a 6-week trend.
    """
    settings.validate()
    oldest = (date.today() - timedelta(days=days)).isoformat()
    newest = date.today().isoformat()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/wellness",
            auth=settings.auth(),
            params={"oldest": oldest, "newest": newest},
            timeout=15,
        )
        r.raise_for_status()
    return [
        {
            "date": e.get("id"),
            "ctl": round(e.get("ctl") or 0, 1),
            "atl": round(e.get("atl") or 0, 1),
            "tsb": round(e.get("tsb") or 0, 1),
            "tss": e.get("tss_actual"),
        }
        for e in r.json()
        if e.get("ctl") or e.get("atl")
    ]


async def get_current_fitness() -> dict:
    """Current CTL/ATL/TSB snapshot with interpretation."""
    settings.validate()
    for target in [date.today().isoformat(), (date.today() - timedelta(days=1)).isoformat()]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.base_url}/athlete/{settings.athlete_id}/wellness/{target}",
                auth=settings.auth(),
                timeout=15,
            )
        if r.status_code == 200:
            e = r.json()
            ctl, atl, tsb = e.get("ctl"), e.get("atl"), e.get("tsb")
            if ctl or atl:
                return {
                    "date": e.get("id"),
                    "ctl": round(ctl, 1) if ctl else None,
                    "atl": round(atl, 1) if atl else None,
                    "tsb": round(tsb, 1) if tsb else None,
                    "interpretation": _interpret_tsb(tsb or 0),
                }
    return {"error": "No CTL/ATL data found in intervals.icu"}


async def get_sport_settings(sport: str = "Ride") -> dict:
    """
    Full zone and FTP configuration for a sport.
    sport: 'Ride', 'Run', 'Swim'
    """
    settings.validate()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/sport-settings/{sport}",
            auth=settings.auth(),
            timeout=15,
        )
        r.raise_for_status()
    s = r.json()
    return {
        "sport": sport,
        "ftp": s.get("ftp"),
        "lthr": s.get("lthr"),
        "max_hr": s.get("max_hr"),
        "w_prime": s.get("w_prime"),
        "power_zones_pct": s.get("power_zones"),
        "hr_zones_bpm": s.get("hr_zones"),
        "mmp_model": s.get("mmp_model"),
    }


async def update_sport_settings(
    sport: str,
    ftp: int = None,
    lthr: int = None,
) -> dict:
    """
    Updates FTP or LTHR for a sport in intervals.icu.
    sport: 'Ride', 'Run', 'Swim'
    """
    settings.validate()
    payload = {}
    if ftp is not None:
        payload["ftp"] = ftp
    if lthr is not None:
        payload["lthr"] = lthr

    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{settings.base_url}/athlete/{settings.athlete_id}/sport-settings/{sport}",
            auth=settings.auth(),
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


def _interpret_tsb(tsb: float) -> str:
    if tsb > 25:
        return "Very fresh — risk of losing fitness, consider adding load"
    elif tsb > 5:
        return "Fresh — good conditions to race or do a quality session"
    elif tsb >= -10:
        return "Productive zone — load and adaptation in balance"
    elif tsb >= -25:
        return "Fatigued — keep following the plan but monitor recovery"
    else:
        return "Very fatigued — consider reducing load or active recovery"
