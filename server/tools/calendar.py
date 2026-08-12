import httpx
from datetime import date, timedelta
from typing import Optional
from server.config import settings


async def get_planned_workouts(days: int = 7) -> list[dict]:
    """
    Trae los workouts planificados en el calendario (category=WORKOUT)
    para los proximos N dias.
    """
    settings.validate()
    oldest = date.today().isoformat()
    newest = (date.today() + timedelta(days=days)).isoformat()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/events",
            auth=settings.auth(),
            params={"oldest": oldest, "newest": newest, "category": "WORKOUT"},
            timeout=15,
        )
        r.raise_for_status()
    events = r.json()
    if not events:
        return [{"message": f"No hay workouts planificados en los proximos {days} dias"}]
    return [
        {
            "id": e.get("id"),
            "date": e.get("start_date_local", "")[:10],
            "name": e.get("name"),
            "sport": e.get("sport_type") or e.get("type"),
            "duration_min": round((e.get("moving_time") or 0) / 60, 1) or None,
            "load_estimate": e.get("icu_training_load"),
            "description": e.get("description"),
            "days_until": (
                date.fromisoformat(e.get("start_date_local", date.today().isoformat())[:10])
                - date.today()
            ).days,
        }
        for e in events
    ]


async def get_todays_plan() -> dict:
    """
    Trae todos los eventos de hoy: workouts, notas y targets.
    """
    settings.validate()
    today = date.today().isoformat()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/events",
            auth=settings.auth(),
            params={"oldest": today, "newest": today},
            timeout=15,
        )
        r.raise_for_status()
    events = r.json()
    if not events:
        return {"date": today, "message": "No hay nada planificado para hoy"}
    return {
        "date": today,
        "sessions": [
            {
                "id": e.get("id"),
                "name": e.get("name"),
                "category": e.get("category"),
                "sport": e.get("sport_type") or e.get("type"),
                "duration_min": round((e.get("moving_time") or 0) / 60, 1) or None,
                "load_estimate": e.get("icu_training_load"),
                "description": e.get("description"),
            }
            for e in events
        ],
        "total_sessions": len(events),
    }


async def get_calendar_events(oldest: str, newest: str, category: str = None) -> list[dict]:
    """
    Trae eventos del calendario en un rango de fechas.
    oldest/newest: 'YYYY-MM-DD'
    category: 'WORKOUT', 'NOTE', 'TARGET', 'RACE' (None = todos)
    """
    settings.validate()
    params = {"oldest": oldest, "newest": newest}
    if category:
        params["category"] = category
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/events",
            auth=settings.auth(),
            params=params,
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


async def create_workout(
    name: str,
    start_date_local: str,
    description: Optional[str] = None,
    sport_type: Optional[str] = None,
    moving_time_secs: Optional[int] = None,
    category: str = "WORKOUT",
) -> dict:
    """
    Crea un evento/workout en el calendario de intervals.icu.
    start_date_local: 'YYYY-MM-DDTHH:MM:SS'
    category: 'WORKOUT', 'NOTE', 'TARGET', 'RACE'
    sport_type: 'Ride', 'Run', 'Swim', etc.
    """
    settings.validate()
    payload: dict = {
        "name": name,
        "category": category,
        "start_date_local": start_date_local,
    }
    if description:
        payload["description"] = description
    if sport_type:
        payload["sport_type"] = sport_type
    if moving_time_secs:
        payload["moving_time"] = moving_time_secs

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.base_url}/athlete/{settings.athlete_id}/events",
            auth=settings.auth(),
            json=payload,
            params={"upsertOnUid": "true"},
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


async def create_weekly_plan(workouts: list[dict]) -> list[dict]:
    """
    Crea multiples workouts en el calendario de una sola vez.
    Cada workout debe tener: name, start_date_local, category (opcional), description (opcional).
    Ejemplo: [{"name": "Fondo Z2", "start_date_local": "2026-05-12T08:00:00", "description": "2h Z2"}]
    """
    settings.validate()
    payload = [
        {
            "name": w.get("name"),
            "category": w.get("category", "WORKOUT"),
            "start_date_local": w.get("start_date_local"),
            "description": w.get("description", ""),
            "sport_type": w.get("sport_type"),
        }
        for w in workouts
    ]
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.base_url}/athlete/{settings.athlete_id}/events/bulk",
            auth=settings.auth(),
            json=payload,
            params={"upsertOnUid": "true", "updatePlanApplied": "true"},
            timeout=20,
        )
        r.raise_for_status()
    return r.json()


async def update_event(
    event_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Modifica un evento existente del calendario por su ID.
    """
    settings.validate()
    payload = {}
    if name:
        payload["name"] = name
    if description is not None:
        payload["description"] = description

    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{settings.base_url}/athlete/{settings.athlete_id}/events/{event_id}",
            auth=settings.auth(),
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
    return r.json()


async def delete_event(event_id: str) -> dict:
    """
    Elimina un evento del calendario por su ID.
    Usar con cuidado — la accion es irreversible.
    """
    settings.validate()
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{settings.base_url}/athlete/{settings.athlete_id}/events/{event_id}",
            auth=settings.auth(),
            timeout=15,
        )
        r.raise_for_status()
    return {"deleted": True, "event_id": event_id}
