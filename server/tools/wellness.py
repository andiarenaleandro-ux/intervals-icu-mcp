import httpx
from datetime import date, timedelta
from typing import Optional
from server.config import settings


async def get_wellness(days: int = 14) -> list[dict]:
    """
    Trae datos de wellness de los ultimos N dias.
    Incluye HRV, FC reposo, sueno, peso, fatiga subjetiva, estado de animo.
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
            "hrv": e.get("hrv"),
            "hrv_score": e.get("hrvScore"),
            "resting_hr": e.get("restingHR"),
            "weight_kg": e.get("weight"),
            "sleep_hours": round(e.get("sleepSecs", 0) / 3600, 1) if e.get("sleepSecs") else None,
            "sleep_quality": e.get("sleepQuality"),
            "fatigue": e.get("fatigue"),
            "mood": e.get("mood"),
            "motivation": e.get("motivation"),
            "soreness": e.get("soreness"),
            "ctl": e.get("ctl"),
            "atl": e.get("atl"),
            "tsb": e.get("tsb"),
            "notes": e.get("notes"),
        }
        for e in r.json()
    ]


async def get_today_wellness() -> dict:
    """Trae el registro de wellness de hoy."""
    settings.validate()
    today = date.today().isoformat()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/wellness/{today}",
            auth=settings.auth(),
            timeout=15,
        )
    if r.status_code == 404:
        return {"date": today, "message": "Sin registro de wellness para hoy"}
    r.raise_for_status()
    e = r.json()
    return {
        "date": e.get("id"),
        "hrv": e.get("hrv"),
        "hrv_score": e.get("hrvScore"),
        "resting_hr": e.get("restingHR"),
        "weight_kg": e.get("weight"),
        "sleep_hours": round(e.get("sleepSecs", 0) / 3600, 1) if e.get("sleepSecs") else None,
        "sleep_quality": e.get("sleepQuality"),
        "fatigue": e.get("fatigue"),
        "mood": e.get("mood"),
        "motivation": e.get("motivation"),
        "soreness": e.get("soreness"),
        "ctl": e.get("ctl"),
        "atl": e.get("atl"),
        "tsb": e.get("tsb"),
        "notes": e.get("notes"),
    }


async def update_wellness(
    target_date: str,
    sleep_hours: Optional[float] = None,
    resting_hr: Optional[int] = None,
    hrv: Optional[float] = None,
    weight_kg: Optional[float] = None,
    fatigue: Optional[int] = None,
    soreness: Optional[int] = None,
    mood: Optional[int] = None,
    motivation: Optional[int] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Registra o actualiza datos de wellness para una fecha.
    target_date: formato 'YYYY-MM-DD'
    fatigue, soreness, mood, motivation: escala 1-7
    sleep_hours: horas de sueno
    """
    settings.validate()
    payload: dict = {"id": target_date}
    if sleep_hours is not None:
        payload["sleepSecs"] = int(sleep_hours * 3600)
    if resting_hr is not None:
        payload["restingHR"] = resting_hr
    if hrv is not None:
        payload["hrv"] = hrv
    if weight_kg is not None:
        payload["weight"] = weight_kg
    if fatigue is not None:
        payload["fatigue"] = fatigue
    if soreness is not None:
        payload["soreness"] = soreness
    if mood is not None:
        payload["mood"] = mood
    if motivation is not None:
        payload["motivation"] = motivation
    if notes is not None:
        payload["notes"] = notes

    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{settings.base_url}/athlete/{settings.athlete_id}/wellness/{target_date}",
            auth=settings.auth(),
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
    return r.json()
