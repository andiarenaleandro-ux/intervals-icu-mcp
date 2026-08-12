import json
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent.parent
PROFILE_PATH = _PROJECT_ROOT / "athlete_profile.json"
EXAMPLE_PROFILE_PATH = _PROJECT_ROOT / "athlete_profile.example.json"


def _load() -> dict:
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if EXAMPLE_PROFILE_PATH.exists():
        data = json.loads(EXAMPLE_PROFILE_PATH.read_text(encoding="utf-8"))
        data["_warning"] = (
            "No existe athlete_profile.json — estás viendo athlete_profile.example.json (plantilla). "
            "Copiá el ejemplo a athlete_profile.json y completá tus datos reales."
        )
        return data
    return {
        "error": (
            "No se encontró athlete_profile.json ni athlete_profile.example.json. "
            "Copiá athlete_profile.example.json a athlete_profile.json en la raíz del "
            "proyecto y completá tus datos para usar esta herramienta."
        )
    }


def _save(data: dict) -> None:
    PROFILE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def get_athlete_extended_profile() -> dict:
    """
    Trae el perfil extendido del atleta con datos que intervals.icu no tiene:
    - Datos de fitting y posicion en bici
    - Largo de palanca actual y objetivo
    - Angulos de torso, cadera, rodilla
    - Historial de cambios de fit con impacto en metricas
    - Lesiones y limitaciones de movilidad
    - Contexto de bloques de entrenamiento
    - Historial de carreras
    Usar siempre que el analisis involucre biomecanica, eficiencia o fitting.
    """
    return _load()


def update_bike_fit(
    crank_length_current_mm: Optional[float] = None,
    crank_length_target_mm: Optional[float] = None,
    crank_change_status: Optional[str] = None,
    saddle_height_mm: Optional[float] = None,
    saddle_setback_mm: Optional[float] = None,
    torso_angle_deg: Optional[float] = None,
    hip_angle_top_dead_center_deg: Optional[float] = None,
    knee_angle_bottom_deg: Optional[float] = None,
    elbow_angle_deg: Optional[float] = None,
    stack_mm: Optional[float] = None,
    reach_mm: Optional[float] = None,
    drop_mm: Optional[float] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Actualiza los datos de fitting de la bici en el perfil local.
    Usar cuando el atleta reporte un cambio de posicion, nuevo fitting,
    o actualizacion de angulos tras analisis de video.
    crank_change_status: 'pendiente', 'en_proceso', 'completado'
    """
    data = _load()
    if "error" in data:
        return data

    fit = data["bike_fit"]
    crank = fit["crank_length_mm"]
    pos = fit["position_current"]

    if crank_length_current_mm is not None:
        crank["current"] = crank_length_current_mm
    if crank_length_target_mm is not None:
        crank["target"] = crank_length_target_mm
    if crank_change_status is not None:
        crank["change_status"] = crank_change_status
    if saddle_height_mm is not None:
        pos["saddle_height_mm"] = saddle_height_mm
    if saddle_setback_mm is not None:
        pos["saddle_setback_mm"] = saddle_setback_mm
    if torso_angle_deg is not None:
        pos["torso_angle_deg"] = torso_angle_deg
    if hip_angle_top_dead_center_deg is not None:
        pos["hip_angle_top_dead_center_deg"] = hip_angle_top_dead_center_deg
    if knee_angle_bottom_deg is not None:
        pos["knee_angle_bottom_deg"] = knee_angle_bottom_deg
    if elbow_angle_deg is not None:
        pos["elbow_angle_deg"] = elbow_angle_deg
    if stack_mm is not None:
        pos["stack_mm"] = stack_mm
    if reach_mm is not None:
        pos["reach_mm"] = reach_mm
    if drop_mm is not None:
        pos["drop_mm"] = drop_mm
    if notes is not None:
        pos["notes"] = notes

    _save(data)
    return {"updated": True, "bike_fit": data["bike_fit"]}


def add_fit_history_entry(
    change_date: str,
    change_description: str,
    metrics_before: Optional[dict] = None,
    metrics_after: Optional[dict] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Registra un cambio de fitting con metricas antes/despues.
    change_date: 'YYYY-MM-DD'
    metrics_before/after: dict con valores relevantes, ej:
      {"avg_power_w": 265, "decoupling_pct": 6.2, "ef": 1.45}
    Permite al agente comparar impacto real de cambios de posicion.
    """
    data = _load()
    if "error" in data:
        return data

    entry = {
        "date": change_date,
        "change": change_description,
        "metrics_before": metrics_before or {},
        "metrics_after": metrics_after or {},
        "notes": notes,
    }
    history = data["bike_fit"].get("fit_history", [])
    # Filtrar el entry vacío inicial si existe
    history = [h for h in history if h.get("change") != "Configuración inicial" or h.get("date")]
    history.append(entry)
    data["bike_fit"]["fit_history"] = history

    _save(data)
    return {"added": True, "entry": entry}


def add_injury(
    injury_date: str,
    injury_description: str,
    body_part: str,
    recovery_weeks: Optional[int] = None,
    status: str = "activa",
    notes: Optional[str] = None,
) -> dict:
    """
    Registra una lesion o molestia en el historial.
    status: 'activa', 'recuperado', 'cronico'
    """
    data = _load()
    if "error" in data:
        return data

    entry = {
        "date": injury_date,
        "injury": injury_description,
        "body_part": body_part,
        "recovery_weeks": recovery_weeks,
        "status": status,
        "notes": notes,
    }
    injuries = [i for i in data.get("injury_history", []) if i.get("injury")]
    injuries.append(entry)
    data["injury_history"] = injuries

    _save(data)
    return {"added": True, "entry": entry}


def update_training_notes(notes: str) -> dict:
    """
    Actualiza las notas generales del perfil del atleta.
    Usar para registrar observaciones del agente sobre tendencias,
    patrones detectados, o recomendaciones a largo plazo.
    """
    data = _load()
    if "error" in data:
        return data
    data["notes"] = notes
    _save(data)
    return {"updated": True}
