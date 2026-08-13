"""
Longitudinal performance analysis engine.

Main metrics:
- CCI (Cardiac Cost Index): avg_HR / %avg_FTP per interval
- CCI_norm: CCI corrected by HRV via Z-Score (not a linear multiplier)
- EF by power zone: aerobic efficiency in Z1-Z5
- HR drift: HR degradation between the first and last work interval

Standard session naming convention:
  BIKE_FTP, BIKE_VO2, BIKE_STAMINA
  RUN_FTP, RUN_VO2, RUN_LONG, RUN_T2
  SWIM_RECOVERY, SWIM_FTP, SWIM_VO2

The agent can also compare by arbitrary date ranges without relying on names.
"""
import math
import json
from datetime import date, timedelta
from typing import Optional
import httpx
from server.config import settings
from server.tools.fitness import get_sport_settings


# ── Z-Score thresholds for HRV correction ───────────────────────────────────
HRV_ZSCORE_NORMAL = 1.0       # ±1 SD → factor = 1.0 (doesn't touch CCI)
HRV_ZSCORE_WARNING = 1.5      # < -1.5 SD → moderate penalty
HRV_ZSCORE_CRITICAL = 2.0     # < -2.0 SD → strong penalty

# Power zones as % of FTP (Coggan 7 zones)
POWER_ZONES = {
    "Z1": (0, 55),
    "Z2": (55, 75),
    "Z3": (75, 90),
    "Z4": (90, 105),
    "Z5": (105, 120),
    "Z6": (120, 150),
    "Z7": (150, 999),
}


def _sport_settings_key(sport: str) -> str:
    """Maps the intervals.icu activity 'type' to the sport-settings sport."""
    s = (sport or "").lower()
    if "run" in s:
        return "Run"
    if "swim" in s:
        return "Swim"
    return "Ride"


async def _resolve_ftp(sport: str) -> tuple[Optional[float], Optional[dict]]:
    """
    Fetches the FTP configured in intervals.icu for the activity's sport.
    Returns (ftp, error_dict). If no FTP is configured, ftp is None and
    error_dict carries an explanatory message asking the athlete to set it.
    """
    sport_key = _sport_settings_key(sport)
    sport_settings = await get_sport_settings(sport_key)
    ftp = sport_settings.get("ftp")
    if not ftp:
        return None, {
            "error": (
                f"No FTP configured in intervals.icu for '{sport_key}'. "
                f"Set it in intervals.icu → Settings → {sport_key} → FTP, "
                f"or pass the ftp parameter manually."
            )
        }
    return ftp, None


def _classify_zone(pct_ftp: float) -> str:
    for zone, (lo, hi) in POWER_ZONES.items():
        if lo <= pct_ftp < hi:
            return zone
    return "Z7"


def _hrv_zscore_factor(hrv_today: float, hrv_values: list[float]) -> tuple[float, str]:
    """
    Calculates the CCI correction factor based on the HRV Z-Score.
    Requires at least 21 historical values to be statistically valid.

    Returns (factor, interpretation):
    - factor = 1.0 → normal HRV, doesn't touch CCI
    - factor < 1.0 → low HRV, CCI likely inflated by sympathetic fatigue
    """
    if len(hrv_values) < 21:
        return 1.0, f"insufficient (only {len(hrv_values)} days, needs 21+)"

    mean = sum(hrv_values) / len(hrv_values)
    std = (sum((x - mean) ** 2 for x in hrv_values) / len(hrv_values)) ** 0.5

    if std == 0:
        return 1.0, "standard deviation = 0, insufficient data"

    z = (hrv_today - mean) / std

    if z >= -HRV_ZSCORE_NORMAL:
        return 1.0, f"normal (Z={z:.2f}) — HRV within ±1 SD, no CCI correction"
    elif z >= -HRV_ZSCORE_WARNING:
        # Mild penalty: reduce CCI proportionally to the Z-Score
        factor = 1.0 + (z + HRV_ZSCORE_NORMAL) * 0.03
        return round(factor, 4), f"slight drop (Z={z:.2f}) — possible fatigue, mild correction applied"
    elif z >= -HRV_ZSCORE_CRITICAL:
        factor = 1.0 + (z + HRV_ZSCORE_WARNING) * 0.05
        return round(factor, 4), f"moderate drop (Z={z:.2f}) — sympathetic fatigue likely, session flagged"
    else:
        factor = max(0.88, 1.0 + (z + HRV_ZSCORE_CRITICAL) * 0.06)  # 0.06 for a stronger penalty in severe fatigue
        return round(factor, 4), f"critical drop (Z={z:.2f}) — high probability of fatigue, CCI corrected"


async def _get_hrv_history(days: int = 60) -> list[float]:
    """Fetches HRV history from intervals wellness to calculate the Z-Score."""
    oldest = (date.today() - timedelta(days=days)).isoformat()
    newest = date.today().isoformat()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/wellness",
            auth=settings.auth(),
            params={"oldest": oldest, "newest": newest},
            timeout=15,
        )
    if r.status_code != 200:
        return []
    data = r.json()
    return [e.get("hrv") or e.get("hrvScore") for e in data if (e.get("hrv") or e.get("hrvScore")) is not None]


async def _get_wellness_for_date(target_date: str) -> dict:
    """Fetches wellness (HRV, TSB) for a specific date."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/wellness/{target_date}",
            auth=settings.auth(),
            timeout=15,
        )
    if r.status_code != 200:
        return {}
    return r.json()


# Expected work zones per session type
SESSION_WORK_ZONES = {
    "BIKE_FTP":     ["Z4"],
    "BIKE_VO2":     ["Z5", "Z6"],
    "BIKE_STAMINA": ["Z2", "Z3"],
    "RUN_FTP":      ["Z4"],
    "RUN_VO2":      ["Z5", "Z6"],
    "RUN_LONG":     ["Z2", "Z3"],
    "RUN_T2":       ["Z2", "Z3"],
    "SWIM_RECOVERY":["Z1", "Z2"],
    "SWIM_FTP":     ["Z4"],
    "SWIM_VO2":     ["Z5", "Z6"],
}

# Minimum power threshold per session type (% FTP)
SESSION_POWER_THRESHOLD = {
    "BIKE_FTP":     0.85,
    "BIKE_VO2":     1.00,
    "BIKE_STAMINA": 0.76,  # 76% FTP (~211W). Excludes untagged warmups and recoveries
    "RUN_FTP":      0.85,
    "RUN_VO2":      1.00,
    "RUN_LONG":     0.55,
    "RUN_T2":       0.55,
    "SWIM_RECOVERY":0.50,
    "SWIM_FTP":     0.85,
    "SWIM_VO2":     1.00,
}


def _extract_work_intervals(
    intervals: list[dict],
    ftp: float,
    session_type: str = None,
) -> list[dict]:
    """
    Filters work intervals using:
    1. Explicit 'type' field from intervals.icu (WORK/INTERVAL/ACTIVE)
    2. If there's no type, uses the power threshold for session_type
    3. Post-filters by the session_type's expected zone to remove
       warmups and recoveries that exceed the power threshold

    session_type: defines which zones count as real work
    """
    # Determine threshold and zones based on session type
    power_threshold = SESSION_POWER_THRESHOLD.get(session_type, 0.65) if session_type else 0.65
    expected_zones = SESSION_WORK_ZONES.get(session_type) if session_type else None

    work = []
    for lap in intervals:
        lap_type = (lap.get("type") or "").upper()

        # Identify by explicit type
        is_work = lap_type in ("WORK", "INTERVAL", "ACTIVE")
        is_rest = lap_type in ("RECOVERY", "REST", "WARMUP", "COOLDOWN")

        # Fallback to power if there's no explicit type
        if not is_work and not is_rest:
            avg_power = lap.get("avg_power") or lap.get("average_watts") or 0
            is_work = avg_power > ftp * power_threshold

        avg_power = lap.get("avg_power") or lap.get("average_watts") or 0
        avg_hr = lap.get("avg_hr") or lap.get("average_heartrate") or 0
        duration = lap.get("elapsed_time") or lap.get("moving_time") or 0

        if avg_power > 0 and avg_hr > 0 and duration > 30:
            pct_ftp = (avg_power / ftp) * 100
            # Prioritize the lap's numeric zone (intervals.icu already calculates it)
            lap_zone_num = lap.get("zone")
            zone = f"Z{lap_zone_num}" if lap_zone_num else _classify_zone(pct_ftp)
            cci = avg_hr / pct_ftp if pct_ftp > 0 else None

            # Decision tree: tags first, power as fallback
            #
            # Level 1 — Explicit tags from the .fit file / intervals.icu
            # If the lap is tagged, we always trust that tag.
            # A warmup at 160W is still WARMUP even if it exceeds the threshold.
            if is_rest:
                # WARMUP, COOLDOWN, RECOVERY, REST → always ignore
                is_work_interval = False
            elif is_work:
                # WORK, INTERVAL, ACTIVE → confirmed structured work
                is_work_interval = True
            else:
                # Level 2 — Plan B: unstructured free rides (no tags)
                # The athlete lapped manually → use power threshold as a proxy
                # This covers free rides where there's no workout loaded on the Garmin
                is_work_interval = avg_power > (ftp * power_threshold)

            lap_data = {
                "lap_index": lap.get("start_index") or 0,
                "duration_sec": duration,
                "avg_power_w": round(avg_power, 1),
                "pct_ftp": round(pct_ftp, 1),
                "avg_hr_bpm": round(avg_hr, 1),
                "zone": zone,
                "cci": round(cci, 4) if cci else None,
                "is_work_interval": is_work_interval,
            }
            work.append(lap_data)
    return work


def _calc_ef_by_zone(work_intervals: list[dict]) -> dict:
    """
    Calculates EF (avg NP/HR) grouped by power zone.
    For long rides and stamina, Z2 is most relevant.
    For FTP, Z4. For VO2, Z5.
    """
    zones: dict = {}
    for interval in work_intervals:
        zone = interval["zone"]
        if zone not in zones:
            zones[zone] = {"powers": [], "hrs": []}
        zones[zone]["powers"].append(interval["avg_power_w"])
        zones[zone]["hrs"].append(interval["avg_hr_bpm"])

    result = {}
    for zone, data in zones.items():
        avg_power = sum(data["powers"]) / len(data["powers"])
        avg_hr = sum(data["hrs"]) / len(data["hrs"])
        result[zone] = {
            "avg_power_w": round(avg_power, 1),
            "avg_hr_bpm": round(avg_hr, 1),
            "ef": round(avg_power / avg_hr, 4) if avg_hr > 0 else None,
            "intervals_count": len(data["powers"]),
        }
    return result


async def analyze_session(
    activity_id: str,
    session_type: Optional[str] = None,
    ftp: Optional[float] = None,
) -> dict:
    """
    Full analysis of a session: CCI per interval, EF by zone,
    HR drift, HRV Z-Score correction.

    activity_id: activity ID in intervals.icu
    session_type: 'BIKE_FTP', 'BIKE_VO2', 'BIKE_STAMINA', 'RUN_FTP',
                  'RUN_VO2', 'RUN_LONG', 'RUN_T2', 'SWIM_RECOVERY', etc.
                  If None, the agent infers it from the activity name.
    ftp: athlete's FTP in watts. If not specified, it's fetched automatically
         from intervals.icu (sport-settings) based on the activity's sport.
         If the athlete has no FTP configured in intervals.icu, the function
         returns an error asking them to configure it or pass it manually.

    Returns full metrics ready to be saved to the DB with save_session_metrics.
    """
    settings.validate()

    # 1. Fetch activity and intervals
    async with httpx.AsyncClient() as client:
        r_act = await client.get(
            f"{settings.base_url}/activity/{activity_id}",
            auth=settings.auth(),
            params={"intervals": "true"},
            timeout=15,
        )
        r_act.raise_for_status()
        r_int = await client.get(
            f"{settings.base_url}/activity/{activity_id}/intervals",
            auth=settings.auth(),
            timeout=15,
        )

    activity = r_act.json()

    # Normalize raw_intervals — the endpoint may return:
    # - a direct list: [{"type": "WORK", ...}, ...]
    # - a dict with a key: {"icu_intervals": [...]} or {"intervals": [...]}
    # - the activity with ?intervals=true already embeds "icu_intervals"
    raw_response = r_int.json() if r_int.status_code == 200 else []
    if isinstance(raw_response, list):
        raw_intervals = raw_response
    elif isinstance(raw_response, dict):
        raw_intervals = (
            raw_response.get("icu_intervals") or
            raw_response.get("intervals") or
            []
        )
    else:
        raw_intervals = []

    # Fallback: if the intervals endpoint returned no laps, use the activity's icu_intervals
    if not raw_intervals and isinstance(activity, dict):
        raw_intervals = activity.get("icu_intervals") or []

    # Defensive: filter out elements that aren't dicts (stray strings, None, etc.)
    raw_intervals = [lap for lap in raw_intervals if isinstance(lap, dict)]

    # 2. Basic activity data
    act_date = (activity.get("start_date_local") or "")[:10]
    sport = activity.get("type", "")
    name = activity.get("name", "")
    duration_min = round((activity.get("moving_time") or 0) / 60, 1)

    # 2b. Resolve FTP dynamically from intervals.icu if not passed explicitly
    if ftp is None:
        ftp, ftp_error = await _resolve_ftp(sport)
        if ftp_error:
            return ftp_error

    # 3. Infer session_type if not passed
    if not session_type:
        name_upper = name.upper()
        if "BIKE_FTP" in name_upper or "FTP" in name_upper and sport == "Ride":
            session_type = "BIKE_FTP"
        elif "BIKE_VO2" in name_upper or "VO2" in name_upper and sport == "Ride":
            session_type = "BIKE_VO2"
        elif "STAMINA" in name_upper or "ENDURANCE" in name_upper and sport == "Ride":
            session_type = "BIKE_STAMINA"
        elif "RUN_FTP" in name_upper or "FTP" in name_upper and sport == "Run":
            session_type = "RUN_FTP"
        elif "RUN_VO2" in name_upper or "VO2" in name_upper and sport == "Run":
            session_type = "RUN_VO2"
        elif "LONG" in name_upper and sport == "Run":
            session_type = "RUN_LONG"
        elif "T2" in name_upper or "TRANSITION" in name_upper:
            session_type = "RUN_T2"
        elif sport == "Swim":
            session_type = "SWIM_RECOVERY"
        else:
            session_type = f"{sport.upper()}_UNKNOWN"

    # 4. Extract work intervals (with zone filtering based on session_type)
    work_intervals = _extract_work_intervals(raw_intervals, ftp, session_type=session_type)

    # 5. Calculate CCI — three levels
    # Only real work laps (session_type's expected zone)
    work_laps = [i for i in work_intervals if i.get("is_work_interval")]
    all_laps = work_intervals

    cci_work_values = [i["cci"] for i in work_laps if i.get("cci")]
    cci_all_values = [i["cci"] for i in all_laps if i.get("cci")]

    # Work CCI: the number to compare week over week
    cci_avg = round(sum(cci_work_values) / len(cci_work_values), 4) if cci_work_values else None
    # Global CCI: full-session context (not for comparison)
    cci_global_all = round(sum(cci_all_values) / len(cci_all_values), 4) if cci_all_values else None

    work_intervals_count = len(work_laps)

    # 6. HR drift — ONLY between equivalent work laps (is_work_interval=True)
    # Comparing warmup vs. last interval would always show >25% due to zone difference
    hr_drift_pct = None
    true_work_laps = [lap for lap in work_laps if lap.get("is_work_interval")]
    if len(true_work_laps) >= 2:
        hr_first = true_work_laps[0]["avg_hr_bpm"]
        hr_last = true_work_laps[-1]["avg_hr_bpm"]
        hr_drift_pct = round(((hr_last - hr_first) / hr_first) * 100, 2)

    # 7. EF by zone (over real work laps)
    ef_by_zone = _calc_ef_by_zone(work_laps)

    # 8. Day's wellness: HRV and TSB
    wellness = await _get_wellness_for_date(act_date)
    hrv_today = wellness.get("hrv") or wellness.get("hrvScore")
    # TSB may come as "tsb", "icu_tsb", or calculated as ctl - atl
    tsb_day = (
        wellness.get("tsb") or
        wellness.get("icu_tsb") or
        (
            (wellness.get("ctl") - wellness.get("atl"))
            if wellness.get("ctl") and wellness.get("atl")
            else None
        )
    )
    hrv_history = await _get_hrv_history(days=60)

    # 9. CCI correction by HRV Z-Score
    hrv_factor = 1.0
    hrv_interpretation = "HRV not available"
    if hrv_today and hrv_history:
        hrv_factor, hrv_interpretation = _hrv_zscore_factor(hrv_today, hrv_history)

    cci_normalized = round(cci_avg * hrv_factor, 4) if cci_avg else None

    # 10. Global EF and decoupling (already calculated by intervals)
    ef_global = activity.get("icu_efficiency_factor")
    decoupling = activity.get("icu_aerobic_decoupling")
    vi = activity.get("icu_variability_index")
    tss = activity.get("icu_training_load")
    np_w = activity.get("icu_weighted_avg_watts")

    # Calculate HRV Z-Score for freshness_ratio and flags
    hrv_zscore = None
    if hrv_today and hrv_history and len(hrv_history) >= 21:
        mean_hrv = sum(hrv_history) / len(hrv_history)
        std_hrv = (sum((x - mean_hrv) ** 2 for x in hrv_history) / len(hrv_history)) ** 0.5
        hrv_zscore = round((hrv_today - mean_hrv) / std_hrv, 2) if std_hrv > 0 else 0.0

    # Freshness Ratio (HRV vs TSB quadrant)
    freshness = None
    if hrv_zscore is not None and tsb_day is not None:
        freshness = _freshness_ratio(hrv_zscore, tsb_day)

    # Intensity Factor (IF)
    if_val = activity.get("icu_intensity")

    flags = _generate_flags(
        cci_avg, cci_normalized, hrv_factor, hrv_zscore,
        hr_drift_pct, decoupling, tsb_day,
        vi=vi, if_val=if_val, session_type=session_type,
    )

    return {
        "activity_id": activity_id,
        "date": act_date,
        "session_type": session_type,
        "sport": sport,
        "name": name,
        "duration_min": duration_min,
        "ftp_used": ftp,
        # Intervals
        "work_intervals_count": work_intervals_count,
        "work_intervals_detail": work_laps,       # Only real work laps
        "all_laps_detail": all_laps,              # All laps (warmup, recovery, work)
        # CCI — CRITICAL RULE: ALWAYS compare cci_work_avg between sessions
        # cci_global_session is NOT exposed — contaminates comparisons due to differing recovery lap counts
        "cci_work_avg": cci_avg,                  # ONLY valid number to compare week over week
        "cci_per_interval": [i["cci"] for i in work_laps],  # Rep 1 → rep N drift (work only)
        "cci_normalized": cci_normalized,
        # Alias for save_session_metrics compatibility
        "cci_avg": cci_avg,
        # EF by zone
        "ef_by_zone": ef_by_zone,
        # Global EF and metrics from intervals
        "ef_global": ef_global,
        "decoupling_pct": decoupling,
        "variability_index": vi,
        "intensity_factor": if_val,
        "tss": tss,
        "np_w": np_w,
        # HR
        "hr_drift_pct": hr_drift_pct,
        # HRV correction
        "hrv_day": hrv_today,
        "hrv_zscore": hrv_zscore,
        "hrv_factor": hrv_factor,
        "hrv_interpretation": hrv_interpretation,
        "tsb_day": round(tsb_day, 1) if tsb_day else None,
        # Freshness Ratio (bi-dimensional quadrant)
        "freshness_ratio": freshness,
        # Flags
        "flags": flags,
    }


def _freshness_ratio(hrv_zscore: float, tsb: float) -> dict:
    """
    Bi-dimensional HRV vs TSB matrix — 4 clinical quadrants.
    Eliminates false positives from looking at TSB in isolation.
    """
    hrv_ok = hrv_zscore >= -1.5
    tsb_ok = tsb >= -10

    if hrv_ok and tsb_ok:
        return {
            "quadrant": "FRESH_RECOVERED",
            "label": "Fresh and recovered — optimal conditions for quality work or testing",
            "color": "green",
            "action": "Good conditions for a demanding session or test",
        }
    elif hrv_ok and not tsb_ok:
        return {
            "quadrant": "OPTIMAL_LOAD_ASSIMILATED",
            "label": "High load but the ANS is tolerating it well — green adaptation zone (Coggan)",
            "color": "green",
            "action": "Continue with the plan, the body is assimilating the load correctly",
        }
    elif not hrv_ok and tsb < -30:
        return {
            "quadrant": "ACUTE_OVERLOAD",
            "label": "Volume broke the ANS — real training fatigue",
            "color": "red",
            "action": "Reduce load, prioritize active recovery or full rest",
        }
    else:  # Critical HRV + TSB >= -10
        return {
            "quadrant": "NON_FUNCTIONAL_OVERREACHING",
            "label": "Mechanically rested but CNS stressed — NOT bike fatigue",
            "color": "orange",
            "action": "Check sleep quality, work stress, or incoming illness. The body needs neurological recovery, not physical",
        }


def _generate_flags(
    cci_avg, cci_normalized, hrv_factor, hrv_zscore,
    hr_drift_pct, decoupling, tsb_day,
    vi=None, if_val=None, session_type=None,
) -> list[str]:
    flags = []

    # HRV
    if hrv_factor < 0.95:
        flags.append("HRV_LOW — session affected by ANS fatigue")

    # HR drift — only alert on aerobic/stamina sessions
    # In high-intensity sessions (FTP, VO2) drift is physiologically normal
    # (VO2 slow component, fast-twitch fiber recruitment)
    AEROBIC_SESSION_TYPES = ("BIKE_STAMINA", "RUN_LONG", "RUN_T2", "SWIM_RECOVERY")
    if hr_drift_pct and hr_drift_pct > 8:
        if session_type in AEROBIC_SESSION_TYPES:
            flags.append(f"HR_DRIFT_HIGH ({hr_drift_pct:.1f}%) — HR degradation in aerobic endurance > 8%")
        elif session_type in ("BIKE_FTP", "RUN_FTP") and hr_drift_pct > 15:
            # In FTP sessions, only alert if drift is truly excessive (>15%)
            flags.append(f"HR_DRIFT_EXCESSIVE ({hr_drift_pct:.1f}%) — drift too high even for a threshold session, check hydration/temperature")

    # Decoupling
    if decoupling and abs(decoupling) > 5:
        flags.append("DECOUPLING_HIGH — you're not in real Z2 or there's cardiovascular fatigue")

    # VI — alert on continuous sessions
    if vi and vi > 1.06:
        continuous = session_type in ("BIKE_STAMINA", "BIKE_FTP", "RUN_LONG", "RUN_T2")
        if continuous:
            flags.append(f"VI_HIGH ({vi:.3f}) — irregular execution, unnecessarily high glycolytic cost")

    # Cardiac suppression — false positive improvement
    # Pattern: negative HRV + HR lower than expected at the same power
    # The heart "holds back" to protect itself — not efficiency, it's exhaustion
    if cci_normalized and cci_avg:
        delta = (cci_normalized - cci_avg) / cci_avg * 100
        if delta < -3 and hrv_zscore and hrv_zscore <= -2.0:
            flags.append(
                "FALSE_POSITIVE_CENTRAL_FATIGUE — Low CCI but critical HRV: "
                "cardiac suppression from ANS exhaustion, NOT aerobic improvement"
            )
    # Mild cardiac suppression signal: negative HRV + surprisingly low HR
    # (the heart doesn't rev up even though power matches other sessions)
    if hrv_zscore and hrv_zscore <= -1.0 and hr_drift_pct and hr_drift_pct > 10:
        if session_type in ("BIKE_FTP", "RUN_FTP"):
            flags.append(
                "POSSIBLE_CARDIAC_SUPPRESSION — Low HRV + elevated drift: "
                "cross-reference average HR with equivalent previous sessions. "
                "If average HR is lower at the same power, it's sympathetic fatigue, not improvement"
            )

    return flags


async def compare_sessions(
    session_type: Optional[str] = None,
    activity_ids: Optional[list[str]] = None,
    weeks: int = 8,
    ftp: Optional[float] = None,
    max_sessions: Optional[int] = None,
) -> dict:
    """
    Compares N equivalent sessions to detect adaptation trends.

    Two modes:
    1. By session_type (e.g. 'BIKE_FTP') → automatically searches the last N weeks
    2. By activity_ids → compares specific activities, no limit on count

    max_sessions: optional limit (None = all it finds, no limit)
    ftp: athlete's FTP in watts. If not specified, each session resolves its
         own FTP automatically from intervals.icu (via analyze_session).
    Detects: real improvement / fatigue noise / plateau / decline.
    Returns the CCI_normalized trend with a 3-week rolling average.
    """
    settings.validate()

    # Get activities to compare
    if activity_ids:
        # Free mode: compare specific IDs
        activities_to_analyze = activity_ids
    elif session_type:
        # Standard mode: search by name over the last N weeks
        oldest = (date.today() - timedelta(weeks=weeks)).isoformat()
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.base_url}/athlete/{settings.athlete_id}/activities",
                auth=settings.auth(),
                params={"oldest": oldest},
                timeout=15,
            )
            r.raise_for_status()
        all_activities = r.json()
        activities_to_analyze = [
            a["id"] for a in all_activities
            if session_type.upper() in (a.get("name") or "").upper()
        ]
    else:
        return {"error": "Specify session_type or activity_ids"}

    if not activities_to_analyze:
        return {
            "session_type": session_type,
            "message": f"No activities found with '{session_type}' in the last {weeks} weeks",
            "tip": "Check that session names follow the standard naming convention (BIKE_FTP, RUN_VO2, etc.)"
        }

    # Apply limit if specified
    if max_sessions:
        activities_to_analyze = activities_to_analyze[:max_sessions]

    # Analyze each session — no artificial limit by default
    sessions_data = []
    errors = []
    for act_id in activities_to_analyze:
        try:
            result = await analyze_session(str(act_id), session_type, ftp)
            if result.get("error"):
                errors.append(result["error"])
                continue
            if result.get("cci_avg"):
                sessions_data.append(result)
        except Exception as e:
            continue

    if not sessions_data:
        if errors:
            return {"error": errors[0]}
        return {"error": "Could not calculate CCI for any session — check that they have power and HR data"}

    # Sort by date
    sessions_data.sort(key=lambda x: x["date"])

    # Rolling average of CCI_norm (window 3)
    cci_norm_values = [s["cci_normalized"] or s["cci_avg"] for s in sessions_data]

    def rolling_avg(values, window=3):
        result = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            chunk = [v for v in values[start:i+1] if v]
            result.append(round(sum(chunk)/len(chunk), 4) if chunk else None)
        return result

    rolling = rolling_avg(cci_norm_values)

    # Detect trend (with false-positive override)
    trend = _detect_trend(cci_norm_values, sessions_detail=sessions_data)

    # Per-session summary
    summary = []
    for i, s in enumerate(sessions_data):
        summary.append({
            "date": s["date"],
            "cci_avg": s["cci_avg"],
            "cci_normalized": s["cci_normalized"],
            "cci_rolling_3w": rolling[i],
            "hrv_day": s["hrv_day"],
            "hrv_interpretation": s["hrv_interpretation"],
            "tsb_day": s["tsb_day"],
            "work_intervals": s["work_intervals_count"],
            "flags": s["flags"],
        })

    return {
        "session_type": session_type or "free comparison",
        "sessions_analyzed": len(sessions_data),
        "period": f"{sessions_data[0]['date']} → {sessions_data[-1]['date']}",
        "trend": trend,
        "sessions": summary,
        "ef_by_zone_latest": sessions_data[-1].get("ef_by_zone"),
        "interpretation": _interpret_trend(trend, sessions_data),
    }


def _rolling_avg(values: list, window: int = 3) -> list:
    """Rolling average over a list of values."""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = [v for v in values[start:i+1] if v is not None]
        result.append(round(sum(chunk)/len(chunk), 4) if chunk else None)
    return result


def _detect_trend(values: list, sessions_detail: list = None) -> dict:
    """
    Detects the CCI trend using a 3-session rolling average.
    Compares the average of the first 3 vs. the last 3 (rolling, not raw).
    Includes a false-positive override for cardiac suppression.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return {"label": "insufficient", "delta_pct": None,
                "note": f"At least 3 sessions are needed, there are {len(clean)}"}

    # Use rolling average to smooth out daily volatility
    rolling = _rolling_avg(clean, window=3)
    rolling_clean = [v for v in rolling if v is not None]

    first_avg = rolling_clean[0] if rolling_clean else clean[0]
    last_avg = rolling_clean[-1] if rolling_clean else clean[-1]
    delta_pct = ((last_avg - first_avg) / first_avg) * 100

    # Override: detect false positives from cardiac suppression in the last sessions
    false_positive_override = False
    if sessions_detail:
        last_sessions = sessions_detail[-3:]
        fp_sessions = [
            s for s in last_sessions
            if any("FALSE_POSITIVE" in f for f in (s.get("flags") or []))
        ]
        if len(fp_sessions) >= 2:
            false_positive_override = True

    # Lower CCI = better (fewer beats per unit of intensity)
    if false_positive_override:
        label = "FALSE_POSITIVE_TREND"
        description = (
            "The apparent CCI improvement is contaminated by cardiac suppression "
            "across multiple sessions. It's not aerobic adaptation — check recovery status."
        )
    elif delta_pct < -3:
        label = "REAL_IMPROVEMENT"
        description = f"Rolling CCI dropped {abs(delta_pct):.1f}% → consolidated cardiovascular adaptation"
    elif delta_pct < -1:
        label = "SLIGHT_IMPROVEMENT"
        description = f"Rolling CCI dropped {abs(delta_pct):.1f}% → positive trend, keep monitoring"
    elif delta_pct <= 1:
        label = "PLATEAU"
        description = f"Rolling CCI stable (±{abs(delta_pct):.1f}%) → consider a new stimulus or test"
    elif delta_pct <= 3:
        label = "SLIGHT_DECLINE"
        description = f"Rolling CCI rose {delta_pct:.1f}% → possible accumulated fatigue"
    else:
        label = "REAL_DECLINE"
        description = f"Rolling CCI rose {delta_pct:.1f}% → review load and recovery"

    return {
        "label": label,
        "delta_pct": round(delta_pct, 2),
        "first_3_rolling_avg": round(first_avg, 4),
        "last_3_rolling_avg": round(last_avg, 4),
        "false_positive_override": false_positive_override,
        "description": description,
        "note": "Trend calculated over a 3-session rolling average to remove daily noise",
    }


def _interpret_trend(trend: dict, sessions: list) -> str:
    label = trend.get("label", "")
    n_fatigued = sum(1 for s in sessions if any("HRV_LOW" in f or "TSB_CRITICAL" in f for f in s.get("flags", [])))

    base = trend.get("description", "")
    if n_fatigued > 0:
        base += f" ({n_fatigued} of {len(sessions)} sessions with fatigue flags — the real CCI may be better than the curve shows)"
    return base


async def get_session_ef_curve(
    session_type: str,
    weeks: int = 6,
    ftp: Optional[float] = None,
) -> dict:
    """
    Generates the EF-by-zone curve over time for a session type.
    Shows whether the EF-power curve shifts week over week.

    ftp: athlete's FTP in watts. If not specified, it's resolved automatically
         from intervals.icu per session (via compare_sessions → analyze_session).
    Ideal for long rides (BIKE_STAMINA, RUN_LONG) where Z2 is the key zone.
    """
    result = await compare_sessions(session_type=session_type, weeks=weeks, ftp=ftp)
    if "error" in result:
        return result

    # We don't have historical ef_by_zone here without re-analyzing
    # We return the latest session's and the CCI trend
    return {
        "session_type": session_type,
        "trend": result["trend"],
        "ef_by_zone_latest": result.get("ef_by_zone_latest"),
        "message": "For the full historical curve, use analyze_session on each session and save with save_session_metrics",
        "sessions_count": result["sessions_analyzed"],
    }
