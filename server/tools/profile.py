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
            "athlete_profile.json doesn't exist — you're viewing athlete_profile.example.json (template). "
            "Copy the example to athlete_profile.json and fill in your real data."
        )
        return data
    return {
        "error": (
            "Neither athlete_profile.json nor athlete_profile.example.json were found. "
            "Copy athlete_profile.example.json to athlete_profile.json in the project "
            "root and fill in your data to use this tool."
        )
    }


def _save(data: dict) -> None:
    PROFILE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def get_athlete_extended_profile() -> dict:
    """
    Fetches the athlete's extended profile with data that intervals.icu doesn't have:
    - Bike fitting and position data
    - Current and target crank length
    - Torso, hip, knee angles
    - History of fit changes with metric impact
    - Injuries and mobility limitations
    - Training block context
    - Race history
    Always use when the analysis involves biomechanics, efficiency, or fitting.
    """
    return _load()


def update_bike_fit(
    crank_length_current_mm: Optional[float] = None,
    crank_length_previous_mm: Optional[float] = None,
    crank_change_status: Optional[str] = None,
    saddle_height_mm: Optional[float] = None,
    saddle_setback_mm: Optional[float] = None,
    torso_angle_deg: Optional[float] = None,
    hip_angle_top_dead_center_deg: Optional[float] = None,
    knee_angle_bottom_deg: Optional[float] = None,
    elbow_angle_aero_deg: Optional[float] = None,
    reach_total_mm: Optional[float] = None,
    drop_saddle_to_pads_mm: Optional[float] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Updates the bike fitting data in the local profile.
    Use when the athlete reports a position change, a new fitting,
    or an angle update after video analysis.
    crank_change_status: 'pending', 'in_progress', 'completed'
    notes: saved to crank_length_mm.adaptation_notes
    """
    data = _load()
    if "error" in data:
        return data

    fit = data["bike_fit"]
    crank = fit["crank_length_mm"]
    pos = fit["position_current"]

    if crank_length_current_mm is not None:
        crank["current"] = crank_length_current_mm
    if crank_length_previous_mm is not None:
        crank["previous"] = crank_length_previous_mm
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
    if elbow_angle_aero_deg is not None:
        pos["elbow_angle_aero_deg"] = elbow_angle_aero_deg
    if reach_total_mm is not None:
        pos["reach_total_mm"] = reach_total_mm
    if drop_saddle_to_pads_mm is not None:
        pos["drop_saddle_to_pads_mm"] = drop_saddle_to_pads_mm
    if notes is not None:
        crank["adaptation_notes"] = notes

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
    Records a fitting change with before/after metrics.
    change_date: 'YYYY-MM-DD'
    metrics_before/after: dict with relevant values, e.g.:
      {"avg_power_w": 265, "decoupling_pct": 6.2, "ef": 1.45}
    Lets the agent compare the real impact of position changes.
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
    # Filter out the initial empty entry if present
    history = [h for h in history if h.get("change") != "Initial configuration" or h.get("date")]
    history.append(entry)
    data["bike_fit"]["fit_history"] = history

    _save(data)
    return {"added": True, "entry": entry}


def add_injury(
    injury_date: str,
    injury_description: str,
    body_part: str,
    recovery_weeks: Optional[int] = None,
    status: str = "active",
    notes: Optional[str] = None,
) -> dict:
    """
    Records an injury or issue in the history.
    status: 'active', 'healed', 'chronic'
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
    Updates the athlete's general profile notes.
    Use to record agent observations about trends,
    detected patterns, or long-term recommendations.
    """
    data = _load()
    if "error" in data:
        return data
    data["notes"] = notes
    _save(data)
    return {"updated": True}
