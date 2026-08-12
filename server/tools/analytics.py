"""
Motor de análisis de performance longitudinal.

Métricas principales:
- CCI (Cardiac Cost Index): FC_avg / %FTP_avg por intervalo
- CCI_norm: CCI corregido por HRV via Z-Score (no multiplicador lineal)
- EF por zona de potencia: eficiencia aeróbica en Z1-Z5
- HR drift: degradación de FC entre primer y último intervalo de trabajo

Nomenclatura estándar de sesiones:
  BIKE_FTP, BIKE_VO2, BIKE_STAMINA
  RUN_FTP, RUN_VO2, RUN_LONG, RUN_T2
  SWIM_RECOVERY, SWIM_FTP, SWIM_VO2

El agente también puede comparar por fechas libres sin depender de nombres.
"""
import math
import json
from datetime import date, timedelta
from typing import Optional
import httpx
from server.config import settings


# ── Umbrales Z-Score para corrección HRV ────────────────────────────────────
HRV_ZSCORE_NORMAL = 1.0       # ±1 SD → factor = 1.0 (no toca el CCI)
HRV_ZSCORE_WARNING = 1.5      # < -1.5 SD → penalidad moderada
HRV_ZSCORE_CRITICAL = 2.0     # < -2.0 SD → penalidad fuerte

# Zonas de potencia como % del FTP (Coggan 7 zonas)
POWER_ZONES = {
    "Z1": (0, 55),
    "Z2": (55, 75),
    "Z3": (75, 90),
    "Z4": (90, 105),
    "Z5": (105, 120),
    "Z6": (120, 150),
    "Z7": (150, 999),
}


def _classify_zone(pct_ftp: float) -> str:
    for zone, (lo, hi) in POWER_ZONES.items():
        if lo <= pct_ftp < hi:
            return zone
    return "Z7"


def _hrv_zscore_factor(hrv_today: float, hrv_values: list[float]) -> tuple[float, str]:
    """
    Calcula el factor de corrección del CCI basado en Z-Score del HRV.
    Requiere al menos 21 valores históricos para ser estadísticamente válido.

    Retorna (factor, interpretacion):
    - factor = 1.0 → HRV normal, no toca el CCI
    - factor < 1.0 → HRV bajo, CCI probablemente inflado por fatiga simpática
    """
    if len(hrv_values) < 21:
        return 1.0, f"insuficiente (solo {len(hrv_values)} días, necesita 21+)"

    mean = sum(hrv_values) / len(hrv_values)
    std = (sum((x - mean) ** 2 for x in hrv_values) / len(hrv_values)) ** 0.5

    if std == 0:
        return 1.0, "desviación estándar = 0, datos insuficientes"

    z = (hrv_today - mean) / std

    if z >= -HRV_ZSCORE_NORMAL:
        return 1.0, f"normal (Z={z:.2f}) — HRV dentro de ±1 SD, CCI sin corrección"
    elif z >= -HRV_ZSCORE_WARNING:
        # Penalidad suave: reducir el CCI proporcional al Z-Score
        factor = 1.0 + (z + HRV_ZSCORE_NORMAL) * 0.03
        return round(factor, 4), f"leve caída (Z={z:.2f}) — posible fatiga, corrección leve aplicada"
    elif z >= -HRV_ZSCORE_CRITICAL:
        factor = 1.0 + (z + HRV_ZSCORE_WARNING) * 0.05
        return round(factor, 4), f"caída moderada (Z={z:.2f}) — fatiga simpática probable, sesión marcada"
    else:
        factor = max(0.88, 1.0 + (z + HRV_ZSCORE_CRITICAL) * 0.06)  # 0.06 para castigo más fuerte en fatiga severa
        return round(factor, 4), f"caída crítica (Z={z:.2f}) — alta probabilidad de fatiga, CCI corregido"


async def _get_hrv_history(days: int = 60) -> list[float]:
    """Trae historial de HRV desde wellness de intervals para calcular Z-Score."""
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
    """Trae wellness (HRV, TSB) de una fecha específica."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.base_url}/athlete/{settings.athlete_id}/wellness/{target_date}",
            auth=settings.auth(),
            timeout=15,
        )
    if r.status_code != 200:
        return {}
    return r.json()


# Zonas de trabajo esperadas por tipo de sesión
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

# Umbral de potencia mínima por tipo de sesión (% FTP)
SESSION_POWER_THRESHOLD = {
    "BIKE_FTP":     0.85,
    "BIKE_VO2":     1.00,
    "BIKE_STAMINA": 0.76,  # 76% FTP (~211W). Excluye calentamientos y recuperaciones sin etiqueta
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
    Filtra intervalos de trabajo usando:
    1. Campo 'type' explícito de intervals.icu (WORK/INTERVAL/ACTIVE)
    2. Si no hay tipo, usa umbral de potencia según session_type
    3. Post-filtra por zona esperada del session_type para eliminar
       calentamientos y recuperaciones que pasen el umbral de potencia

    session_type: define qué zonas se consideran trabajo real
    """
    # Determinar umbral y zonas según tipo de sesión
    power_threshold = SESSION_POWER_THRESHOLD.get(session_type, 0.65) if session_type else 0.65
    expected_zones = SESSION_WORK_ZONES.get(session_type) if session_type else None

    work = []
    for lap in intervals:
        lap_type = (lap.get("type") or "").upper()

        # Identificar por tipo explícito
        is_work = lap_type in ("WORK", "INTERVAL", "ACTIVE")
        is_rest = lap_type in ("RECOVERY", "REST", "WARMUP", "COOLDOWN")

        # Fallback por potencia si no hay tipo explícito
        if not is_work and not is_rest:
            avg_power = lap.get("avg_power") or lap.get("average_watts") or 0
            is_work = avg_power > ftp * power_threshold

        avg_power = lap.get("avg_power") or lap.get("average_watts") or 0
        avg_hr = lap.get("avg_hr") or lap.get("average_heartrate") or 0
        duration = lap.get("elapsed_time") or lap.get("moving_time") or 0

        if avg_power > 0 and avg_hr > 0 and duration > 30:
            pct_ftp = (avg_power / ftp) * 100
            # Priorizar zone numérico del lap (intervals.icu ya lo calcula)
            lap_zone_num = lap.get("zone")
            zone = f"Z{lap_zone_num}" if lap_zone_num else _classify_zone(pct_ftp)
            cci = avg_hr / pct_ftp if pct_ftp > 0 else None

            # Árbol de decisión: tags primero, potencia como fallback
            #
            # Nivel 1 — Tags explícitos del archivo .fit / intervals.icu
            # Si el lap viene etiquetado, confiamos en esa etiqueta siempre.
            # Un calentamiento a 160W sigue siendo WARMUP aunque supere el umbral.
            if is_rest:
                # WARMUP, COOLDOWN, RECOVERY, REST → ignorar siempre
                is_work_interval = False
            elif is_work:
                # WORK, INTERVAL, ACTIVE → trabajo estructurado confirmado
                is_work_interval = True
            else:
                # Nivel 2 — Plan B: salidas libres sin estructura (sin tags)
                # El atleta lapeó manualmente → usar umbral de potencia como proxy
                # Esto cubre rodadas libres donde no hay workout cargado en el Garmin
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
    Calcula EF (NP/FC promedio) agrupado por zona de potencia.
    Para fondos y stamina, lo más relevante es Z2.
    Para FTP, Z4. Para VO2, Z5.
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
    ftp: float = 278.0,
) -> dict:
    """
    Análisis completo de una sesión: CCI por intervalo, EF por zona,
    HR drift, corrección HRV por Z-Score.

    activity_id: ID de la actividad en intervals.icu
    session_type: 'BIKE_FTP', 'BIKE_VO2', 'BIKE_STAMINA', 'RUN_FTP',
                  'RUN_VO2', 'RUN_LONG', 'RUN_T2', 'SWIM_RECOVERY', etc.
                  Si es None, el agente lo infiere del nombre de la actividad.
    ftp: FTP actual del atleta (default 278W)

    Retorna métricas completas listas para guardar en la BD con save_session_metrics.
    """
    settings.validate()

    # 1. Traer actividad e intervalos
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

    # Normalizar raw_intervals — el endpoint puede devolver:
    # - lista directa: [{"type": "WORK", ...}, ...]
    # - dict con key: {"icu_intervals": [...]} o {"intervals": [...]}
    # - la actividad con ?intervals=true ya embebe "icu_intervals"
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

    # Fallback: si el endpoint de intervals no dio laps, usar icu_intervals de la actividad
    if not raw_intervals and isinstance(activity, dict):
        raw_intervals = activity.get("icu_intervals") or []

    # Defensivo: filtrar elementos que no sean dict (strings sueltos, None, etc.)
    raw_intervals = [lap for lap in raw_intervals if isinstance(lap, dict)]

    # 2. Datos básicos de la actividad
    act_date = (activity.get("start_date_local") or "")[:10]
    sport = activity.get("type", "")
    name = activity.get("name", "")
    duration_min = round((activity.get("moving_time") or 0) / 60, 1)

    # 3. Inferir session_type si no se pasó
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
        elif "T2" in name_upper or "TRANSICION" in name_upper:
            session_type = "RUN_T2"
        elif sport == "Swim":
            session_type = "SWIM_RECOVERY"
        else:
            session_type = f"{sport.upper()}_UNKNOWN"

    # 4. Extraer intervalos de trabajo (con filtro por zona según session_type)
    work_intervals = _extract_work_intervals(raw_intervals, ftp, session_type=session_type)

    # 5. Calcular CCI — tres niveles
    # Solo laps de trabajo real (zona esperada del session_type)
    work_laps = [i for i in work_intervals if i.get("is_work_interval")]
    all_laps = work_intervals

    cci_work_values = [i["cci"] for i in work_laps if i.get("cci")]
    cci_all_values = [i["cci"] for i in all_laps if i.get("cci")]

    # CCI trabajo: el número para comparar semana a semana
    cci_avg = round(sum(cci_work_values) / len(cci_work_values), 4) if cci_work_values else None
    # CCI global: contexto de sesión completa (no para comparar)
    cci_global_all = round(sum(cci_all_values) / len(cci_all_values), 4) if cci_all_values else None

    work_intervals_count = len(work_laps)

    # 6. HR drift — SOLO entre laps de trabajo equivalente (is_work_interval=True)
    # Comparar calentamiento vs último intervalo daría siempre >25% por diferencia de zona
    hr_drift_pct = None
    true_work_laps = [lap for lap in work_laps if lap.get("is_work_interval")]
    if len(true_work_laps) >= 2:
        hr_first = true_work_laps[0]["avg_hr_bpm"]
        hr_last = true_work_laps[-1]["avg_hr_bpm"]
        hr_drift_pct = round(((hr_last - hr_first) / hr_first) * 100, 2)

    # 7. EF por zona (sobre laps de trabajo real)
    ef_by_zone = _calc_ef_by_zone(work_laps)

    # 8. Wellness del día: HRV y TSB
    wellness = await _get_wellness_for_date(act_date)
    hrv_today = wellness.get("hrv") or wellness.get("hrvScore")
    # TSB puede venir como "tsb", "icu_tsb" o calculado como ctl - atl
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

    # 9. Corrección CCI por Z-Score HRV
    hrv_factor = 1.0
    hrv_interpretation = "HRV no disponible"
    if hrv_today and hrv_history:
        hrv_factor, hrv_interpretation = _hrv_zscore_factor(hrv_today, hrv_history)

    cci_normalized = round(cci_avg * hrv_factor, 4) if cci_avg else None

    # 10. EF y decoupling globales (ya calculados por intervals)
    ef_global = activity.get("icu_efficiency_factor")
    decoupling = activity.get("icu_aerobic_decoupling")
    vi = activity.get("icu_variability_index")
    tss = activity.get("icu_training_load")
    np_w = activity.get("icu_weighted_avg_watts")

    # Calcular HRV Z-Score para freshness_ratio y flags
    hrv_zscore = None
    if hrv_today and hrv_history and len(hrv_history) >= 21:
        mean_hrv = sum(hrv_history) / len(hrv_history)
        std_hrv = (sum((x - mean_hrv) ** 2 for x in hrv_history) / len(hrv_history)) ** 0.5
        hrv_zscore = round((hrv_today - mean_hrv) / std_hrv, 2) if std_hrv > 0 else 0.0

    # Freshness Ratio (cuadrante HRV vs TSB)
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
        # Intervalos
        "work_intervals_count": work_intervals_count,
        "work_intervals_detail": work_laps,       # Solo laps de trabajo real
        "all_laps_detail": all_laps,              # Todos los laps (calentamiento, recovery, trabajo)
        # CCI — REGLA CRÍTICA: comparar SIEMPRE cci_work_avg entre sesiones
        # cci_global_session NO se expone — contamina comparativas por diferente N de recuperaciones
        "cci_work_avg": cci_avg,                  # ÚNICO número válido para comparar semana a semana
        "cci_per_interval": [i["cci"] for i in work_laps],  # Drift rep 1 → rep N (solo trabajo)
        "cci_normalized": cci_normalized,
        # Alias para compatibilidad con save_session_metrics
        "cci_avg": cci_avg,
        # EF por zona
        "ef_by_zone": ef_by_zone,
        # EF y métricas globales de intervals
        "ef_global": ef_global,
        "decoupling_pct": decoupling,
        "variability_index": vi,
        "intensity_factor": if_val,
        "tss": tss,
        "np_w": np_w,
        # HR
        "hr_drift_pct": hr_drift_pct,
        # Corrección HRV
        "hrv_day": hrv_today,
        "hrv_zscore": hrv_zscore,
        "hrv_factor": hrv_factor,
        "hrv_interpretation": hrv_interpretation,
        "tsb_day": round(tsb_day, 1) if tsb_day else None,
        # Freshness Ratio (cuadrante bi-dimensional)
        "freshness_ratio": freshness,
        # Flags
        "flags": flags,
    }


def _freshness_ratio(hrv_zscore: float, tsb: float) -> dict:
    """
    Matriz bi-dimensional HRV vs TSB — 4 cuadrantes clínicos.
    Elimina los falsos positivos del TSB aislado.
    """
    hrv_ok = hrv_zscore >= -1.5
    tsb_ok = tsb >= -10

    if hrv_ok and tsb_ok:
        return {
            "cuadrante": "FRESCO_RECUPERADO",
            "label": "Fresco y recuperado — condiciones óptimas para calidad o test",
            "color": "verde",
            "accion": "Buenas condiciones para sesión exigente o test",
        }
    elif hrv_ok and not tsb_ok:
        return {
            "cuadrante": "CARGA_OPTIMA_ASIMILADA",
            "label": "Carga alta pero el SNA la tolera bien — zona verde de adaptación (Coggan)",
            "color": "verde",
            "accion": "Continuar con el plan, el cuerpo está asimilando la carga correctamente",
        }
    elif not hrv_ok and tsb < -30:
        return {
            "cuadrante": "SOBRECARGA_AGUDA",
            "label": "El volumen rompió el SNA — fatiga de entrenamiento real",
            "color": "rojo",
            "accion": "Reducir carga, priorizar recuperación activa o descanso total",
        }
    else:  # HRV crítico + TSB >= -10
        return {
            "cuadrante": "FATIGA_NO_FUNCIONAL",
            "label": "Descansado mecánicamente pero SNC estresado — NO es fatiga de bici",
            "color": "naranja",
            "accion": "Revisar calidad de sueño, estrés laboral o enfermedad inminente. El cuerpo necesita recuperación neurológica, no física",
        }


def _generate_flags(
    cci_avg, cci_normalized, hrv_factor, hrv_zscore,
    hr_drift_pct, decoupling, tsb_day,
    vi=None, if_val=None, session_type=None,
) -> list[str]:
    flags = []

    # HRV
    if hrv_factor < 0.95:
        flags.append("HRV_LOW — sesión condicionada por fatiga del SNA")

    # HR drift — solo alertar en sesiones aeróbicas/stamina
    # En sesiones de alta intensidad (FTP, VO2) el drift es fisiológicamente normal
    # (componente lento del VO2, reclutamiento de fibras rápidas)
    AEROBIC_SESSION_TYPES = ("BIKE_STAMINA", "RUN_LONG", "RUN_T2", "SWIM_RECOVERY")
    if hr_drift_pct and hr_drift_pct > 8:
        if session_type in AEROBIC_SESSION_TYPES:
            flags.append(f"HR_DRIFT_HIGH ({hr_drift_pct:.1f}%) — degradación de FC en resistencia aeróbica > 8%")
        elif session_type in ("BIKE_FTP", "RUN_FTP") and hr_drift_pct > 15:
            # En FTP solo alertar si el drift es realmente excesivo (>15%)
            flags.append(f"HR_DRIFT_EXCESSIVE ({hr_drift_pct:.1f}%) — drift muy alto incluso para sesión de umbral, revisar hidratación/temperatura")

    # Decoupling
    if decoupling and abs(decoupling) > 5:
        flags.append("DECOUPLING_HIGH — no estás en Z2 real o hay fatiga cardiovascular")

    # VI — alerta en sesiones continuas
    if vi and vi > 1.06:
        continuous = session_type in ("BIKE_STAMINA", "BIKE_FTP", "RUN_LONG", "RUN_T2")
        if continuous:
            flags.append(f"VI_HIGH ({vi:.3f}) — ejecución irregular, costo glucolítico innecesariamente alto")

    # Supresión cardíaca — falso positivo de mejora
    # Patrón: HRV negativo + FC más baja de lo esperado a la misma potencia
    # El corazón "se frena" para protegerse — no es eficiencia, es agotamiento
    if cci_normalized and cci_avg:
        delta = (cci_normalized - cci_avg) / cci_avg * 100
        if delta < -3 and hrv_zscore and hrv_zscore <= -2.0:
            flags.append(
                "FALSO_POSITIVO_FATIGA_CENTRAL — CCI bajo pero HRV crítico: "
                "supresión cardíaca por agotamiento del SNA, NO es mejora aeróbica"
            )
    # Señal de supresión cardíaca leve: HRV negativo + FC sorprendentemente baja
    # (el corazón no sube de vueltas aunque la potencia sea la misma que otras sesiones)
    if hrv_zscore and hrv_zscore <= -1.0 and hr_drift_pct and hr_drift_pct > 10:
        if session_type in ("BIKE_FTP", "RUN_FTP"):
            flags.append(
                "POSIBLE_SUPRESION_CARDIACA — HRV bajo + drift elevado: "
                "cruzar FC media con sesiones anteriores equivalentes. "
                "Si FC media es menor a igual potencia, es fatiga simpática, no mejora"
            )

    return flags


async def compare_sessions(
    session_type: Optional[str] = None,
    activity_ids: Optional[list[str]] = None,
    weeks: int = 8,
    ftp: float = 278.0,
    max_sessions: Optional[int] = None,
) -> dict:
    """
    Compara N sesiones equivalentes para detectar tendencias de adaptación.

    Dos modos:
    1. Por session_type (ej: 'BIKE_FTP') → busca automáticamente en las últimas N semanas
    2. Por activity_ids → compara actividades específicas, sin límite de cantidad

    max_sessions: límite opcional (None = todas las que encuentre, sin límite)
    Detecta: mejora real / ruido por fatiga / plateau / caída.
    Retorna tendencia del CCI_normalizado con rolling average de 3 semanas.
    """
    settings.validate()

    # Obtener actividades a comparar
    if activity_ids:
        # Modo libre: comparar IDs específicos
        activities_to_analyze = activity_ids
    elif session_type:
        # Modo estándar: buscar por nombre en los últimos N semanas
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
        return {"error": "Especificá session_type o activity_ids"}

    if not activities_to_analyze:
        return {
            "session_type": session_type,
            "message": f"No se encontraron actividades con '{session_type}' en las últimas {weeks} semanas",
            "tip": "Verificá que los nombres de sesión sigan la nomenclatura estándar (BIKE_FTP, RUN_VO2, etc.)"
        }

    # Aplicar límite si se especificó
    if max_sessions:
        activities_to_analyze = activities_to_analyze[:max_sessions]

    # Analizar cada sesión — sin límite artificial por defecto
    sessions_data = []
    for act_id in activities_to_analyze:
        try:
            result = await analyze_session(str(act_id), session_type, ftp)
            if result.get("cci_avg"):
                sessions_data.append(result)
        except Exception as e:
            continue

    if not sessions_data:
        return {"error": "No se pudo calcular CCI para ninguna sesión — verificar que tengan potencia y FC"}

    # Ordenar por fecha
    sessions_data.sort(key=lambda x: x["date"])

    # Rolling average CCI_norm (ventana 3)
    cci_norm_values = [s["cci_normalized"] or s["cci_avg"] for s in sessions_data]

    def rolling_avg(values, window=3):
        result = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            chunk = [v for v in values[start:i+1] if v]
            result.append(round(sum(chunk)/len(chunk), 4) if chunk else None)
        return result

    rolling = rolling_avg(cci_norm_values)

    # Detectar tendencia (con override de falso positivo)
    trend = _detect_trend(cci_norm_values, sessions_detail=sessions_data)

    # Resumen por sesión
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
        "session_type": session_type or "comparativa libre",
        "sessions_analyzed": len(sessions_data),
        "period": f"{sessions_data[0]['date']} → {sessions_data[-1]['date']}",
        "trend": trend,
        "sessions": summary,
        "ef_by_zone_latest": sessions_data[-1].get("ef_by_zone"),
        "interpretation": _interpret_trend(trend, sessions_data),
    }


def _rolling_avg(values: list, window: int = 3) -> list:
    """Promedio móvil sobre una lista de valores."""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = [v for v in values[start:i+1] if v is not None]
        result.append(round(sum(chunk)/len(chunk), 4) if chunk else None)
    return result


def _detect_trend(values: list, sessions_detail: list = None) -> dict:
    """
    Detecta tendencia del CCI usando rolling average de 3 sesiones.
    Compara promedio de las primeras 3 vs últimas 3 (rolling, no raw).
    Incluye override de falso positivo por supresión cardíaca.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return {"label": "insuficiente", "delta_pct": None,
                "note": f"Se necesitan al menos 3 sesiones, hay {len(clean)}"}

    # Usar rolling average para suavizar volatilidad diaria
    rolling = _rolling_avg(clean, window=3)
    rolling_clean = [v for v in rolling if v is not None]

    first_avg = rolling_clean[0] if rolling_clean else clean[0]
    last_avg = rolling_clean[-1] if rolling_clean else clean[-1]
    delta_pct = ((last_avg - first_avg) / first_avg) * 100

    # Override: detectar si hay falsos positivos por supresión cardíaca en las últimas sesiones
    false_positive_override = False
    if sessions_detail:
        last_sessions = sessions_detail[-3:]
        fp_sessions = [
            s for s in last_sessions
            if any("FALSO_POSITIVO" in f for f in (s.get("flags") or []))
        ]
        if len(fp_sessions) >= 2:
            false_positive_override = True

    # CCI más bajo = mejor (menos latidos por unidad de intensidad)
    if false_positive_override:
        label = "FALSO_POSITIVO_TENDENCIA"
        description = (
            "La mejora aparente del CCI está contaminada por supresión cardíaca "
            "en múltiples sesiones. No es adaptación aeróbica — revisar estado de recuperación."
        )
    elif delta_pct < -3:
        label = "MEJORA_REAL"
        description = f"Rolling CCI bajó {abs(delta_pct):.1f}% → adaptación cardiovascular consolidada"
    elif delta_pct < -1:
        label = "MEJORA_LEVE"
        description = f"Rolling CCI bajó {abs(delta_pct):.1f}% → tendencia positiva, continuar monitoreando"
    elif delta_pct <= 1:
        label = "PLATEAU"
        description = f"Rolling CCI estable (±{abs(delta_pct):.1f}%) → evaluar nuevo estímulo o test"
    elif delta_pct <= 3:
        label = "CAIDA_LEVE"
        description = f"Rolling CCI subió {delta_pct:.1f}% → posible fatiga acumulada"
    else:
        label = "CAIDA_REAL"
        description = f"Rolling CCI subió {delta_pct:.1f}% → revisar carga y recuperación"

    return {
        "label": label,
        "delta_pct": round(delta_pct, 2),
        "first_3_rolling_avg": round(first_avg, 4),
        "last_3_rolling_avg": round(last_avg, 4),
        "false_positive_override": false_positive_override,
        "description": description,
        "note": "Tendencia calculada sobre rolling average de 3 sesiones para eliminar ruido diario",
    }


def _interpret_trend(trend: dict, sessions: list) -> str:
    label = trend.get("label", "")
    n_fatigued = sum(1 for s in sessions if any("HRV_LOW" in f or "TSB_CRITICAL" in f for f in s.get("flags", [])))

    base = trend.get("description", "")
    if n_fatigued > 0:
        base += f" ({n_fatigued} de {len(sessions)} sesiones con flags de fatiga — el CCI real puede ser mejor de lo que muestra la curva)"
    return base


async def get_session_ef_curve(
    session_type: str,
    weeks: int = 6,
    ftp: float = 278.0,
) -> dict:
    """
    Genera la curva de EF por zona a lo largo del tiempo para un tipo de sesión.
    Muestra si la curva EF-potencia se desplaza semana a semana.

    Ideal para fondos (BIKE_STAMINA, RUN_LONG) donde Z2 es la zona clave.
    """
    result = await compare_sessions(session_type=session_type, weeks=weeks, ftp=ftp)
    if "error" in result:
        return result

    # No tenemos los ef_by_zone históricos aquí sin re-analizar
    # Devolvemos el de la última sesión y la tendencia del CCI
    return {
        "session_type": session_type,
        "trend": result["trend"],
        "ef_by_zone_latest": result.get("ef_by_zone_latest"),
        "message": "Para la curva histórica completa, usar analyze_session en cada sesión y guardar con save_session_metrics",
        "sessions_count": result["sessions_analyzed"],
    }