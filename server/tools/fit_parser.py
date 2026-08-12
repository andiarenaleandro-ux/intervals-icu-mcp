from pathlib import Path
from server.config import settings


def _get_fit_dir() -> Path:
    p = Path(settings.fit_files_dir)
    p.mkdir(exist_ok=True)
    return p



def list_fit_files() -> list[str]:
    """
    Lista todos los archivos .fit disponibles en la carpeta fit_files/.
    Usá los nombres que devuelve esta función para llamar a analyze_fit_file.
    """
    fit_dir = _get_fit_dir()
    files = sorted(fit_dir.glob("*.fit"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [f.name for f in files]



def analyze_fit_file(filename: str) -> dict:
    """
    Analiza un archivo .fit en detalle.
    Retorna: duración, distancia, potencia media/máx/NP, picos de 1/5/20 min,
    FC media/máx, cadencia, elevación, distribución por zonas (aproximada).
    Ideal para revisar una sesión en profundidad.
    """
    try:
        import fitparse
    except ImportError:
        return {"error": "fitparse no está instalado. Ejecutá: pip install fitparse"}

    fit_dir = _get_fit_dir()
    path = fit_dir / filename

    if not path.exists():
        available = [f.name for f in fit_dir.glob("*.fit")]
        return {
            "error": f"Archivo '{filename}' no encontrado.",
            "disponibles": available,
        }

    fitfile = fitparse.FitFile(str(path))

    records = []
    laps = []

    for msg in fitfile.get_messages():
        if msg.name == "record":
            data = {d.name: d.value for d in msg if d.value is not None}
            records.append(data)
        elif msg.name == "lap":
            data = {d.name: d.value for d in msg if d.value is not None}
            laps.append(data)

    if not records:
        return {"error": "El archivo .fit no contiene datos de actividad"}

    # --- Extraer series temporales ---
    powers = [r["power"] for r in records if "power" in r and r["power"] is not None]
    hrs = [r["heart_rate"] for r in records if "heart_rate" in r]
    cadences = [r["cadence"] for r in records if "cadence" in r]
    speeds = [r["speed"] for r in records if "speed" in r]
    altitudes = [r["altitude"] for r in records if "altitude" in r]

    # --- Potencia normalizada (NP) ---
    def calc_np(power_list: list) -> float | None:
        if len(power_list) < 30:
            return None
        # Rolling average 30s → elevar a 4ta potencia → media → raíz 4ta
        window = 30
        rolling = []
        for i in range(len(power_list) - window):
            rolling.append(sum(power_list[i:i+window]) / window)
        if not rolling:
            return None
        avg_4th = sum(p**4 for p in rolling) / len(rolling)
        return round(avg_4th ** 0.25, 1)

    # --- Peak power rolling windows ---
    def peak_power(power_list: list, window_sec: int) -> float | None:
        if len(power_list) < window_sec:
            return None
        best = max(
            sum(power_list[i:i+window_sec]) / window_sec
            for i in range(len(power_list) - window_sec)
        )
        return round(best, 1)

    # --- Elevación ganada ---
    elevation_gain = 0.0
    if len(altitudes) > 1:
        for i in range(1, len(altitudes)):
            diff = altitudes[i] - altitudes[i-1]
            if diff > 0:
                elevation_gain += diff

    # --- Resumen de laps ---
    laps_summary = []
    for i, lap in enumerate(laps, 1):
        laps_summary.append({
            "lap": i,
            "duration_min": round((lap.get("total_elapsed_time") or 0) / 60, 1),
            "distance_km": round((lap.get("total_distance") or 0) / 1000, 2),
            "avg_power_w": lap.get("avg_power"),
            "max_power_w": lap.get("max_power"),
            "avg_hr_bpm": lap.get("avg_heart_rate"),
            "avg_cadence": lap.get("avg_cadence"),
        })

    # --- Resultado final ---
    result = {
        "filename": filename,
        "total_records": len(records),
        "duration_min": round(len(records) / 60, 1),  # Asume 1 sample/seg
        "laps_count": len(laps),
    }

    if powers:
        np_value = calc_np(powers)
        result["power"] = {
            "avg_w": round(sum(powers) / len(powers), 1),
            "max_w": max(powers),
            "normalized_w": np_value,
            "peak_1min_w": peak_power(powers, 60),
            "peak_5min_w": peak_power(powers, 300),
            "peak_20min_w": peak_power(powers, 1200),
            "peak_60min_w": peak_power(powers, 3600),
        }

    if hrs:
        result["heart_rate"] = {
            "avg_bpm": round(sum(hrs) / len(hrs), 1),
            "max_bpm": max(hrs),
        }

    if cadences:
        result["cadence"] = {
            "avg": round(sum(cadences) / len(cadences), 1),
            "max": max(cadences),
        }

    if speeds:
        avg_speed_ms = sum(speeds) / len(speeds)
        result["speed"] = {
            "avg_kmh": round(avg_speed_ms * 3.6, 1),
            "max_kmh": round(max(speeds) * 3.6, 1),
        }
        result["distance_km"] = round(sum(speeds), 2) / 1000  # Aproximación

    if altitudes:
        result["elevation_gain_m"] = round(elevation_gain, 1)

    if laps_summary:
        result["laps"] = laps_summary

    return result



def get_fit_raw_summary(filename: str) -> dict:
    """
    Trae un resumen de los tipos de mensajes y campos disponibles en el .fit.
    Útil para explorar qué datos tiene el archivo antes de analizarlo en detalle.
    """
    try:
        import fitparse
    except ImportError:
        return {"error": "fitparse no está instalado"}

    fit_dir = _get_fit_dir()
    path = fit_dir / filename

    if not path.exists():
        return {"error": f"Archivo '{filename}' no encontrado"}

    fitfile = fitparse.FitFile(str(path))

    message_types: dict[str, int] = {}
    field_names: dict[str, set] = {}

    for msg in fitfile.get_messages():
        name = msg.name
        message_types[name] = message_types.get(name, 0) + 1
        if name not in field_names:
            field_names[name] = set()
        for d in msg:
            if d.value is not None:
                field_names[name].add(d.name)

    return {
        "filename": filename,
        "message_types": message_types,
        "fields_per_type": {k: sorted(v) for k, v in field_names.items()},
    }
