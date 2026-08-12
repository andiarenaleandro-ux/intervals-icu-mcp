"""
Herramientas de análisis aerodinámico para ciclismo TT.
Basado en el modelo de potencia de ciclismo (Martin et al., 1998)
y el método de elevación virtual (Chung, 2012).
"""
import math
from typing import Optional
from server.config import settings


# ── Constantes físicas ──────────────────────────────────────────────────────
RHO_SEA_LEVEL = 1.2256   # kg/m³ — densidad del aire a nivel del mar, 15°C
G = 9.8067               # m/s²
CRR_TT_ROAD = 0.0035     # coeficiente de resistencia a la rodadura (TT, asfalto liso)
CRR_TT_ROUGH = 0.0042    # asfalto rugoso

# CdA de referencia por posición (Defraeye et al., 2010; Blocken et al., 2013)
# Valores típicos de túnel de viento y CFD
CDA_REFERENCE = {
    "road_hoods":       0.388,  # manos en capuchas
    "road_drops":       0.342,  # manos en bajantes
    "road_aero":        0.307,  # agachado en bajantes
    "tt_standard":      0.265,  # TT estándar, torso ~20-25°
    "tt_aggressive":    0.230,  # TT agresivo, torso ~15-20°
    "tt_very_aggressive": 0.210, # TT muy agresivo, torso < 15°
    "tt_world_class":   0.185,  # Elite TT optimizado
}


def _air_density(altitude_m: float = 0, temp_c: float = 15) -> float:
    """Calcula densidad del aire según altitud y temperatura."""
    pressure = 101325 * (1 - 0.0000226 * altitude_m) ** 5.256
    return pressure / (287.05 * (temp_c + 273.15))


def estimate_cda_from_position(
    torso_angle_deg: float,
    hip_angle_deg: float,
    elbow_angle_deg: float,
    total_mass_kg: float,
    reference_powers_w: list[float] = None,
    frontal_area_notes: str = None,
) -> dict:
    """
    Estima el CdA a partir de los ángulos de posición del atleta en la bici.
    Usa modelos empíricos de la literatura (Defraeye et al., Blocken et al.).

    torso_angle_deg: ángulo del torso respecto a horizontal (menor = más aero)
    hip_angle_deg: ángulo cadera en PMS entre torso y fémur
    elbow_angle_deg: ángulo entre torso y húmero en posición aero
    total_mass_kg: masa total del atleta + equipo (cuerpo + bici) en kg, usada
                   para las estimaciones de velocidad. Parámetro obligatorio.
    reference_powers_w: potencias (W) para las que se estima velocidad.
                        Si no se pasa, usa valores genéricos [200, 250, 300].

    Retorna estimación de CdA y comparativa con referencias de literatura.
    """
    if reference_powers_w is None:
        reference_powers_w = [200, 250, 300]
    # Modelo empírico basado en ángulo de torso (principal driver del CdA en TT)
    # Regresión aproximada de datos de Defraeye et al. (2010) y Blocken et al. (2013)
    if torso_angle_deg <= 10:
        base_cda = 0.195
        position_label = "Extremadamente agresivo (< 10°)"
    elif torso_angle_deg <= 15:
        base_cda = 0.210
        position_label = "Muy agresivo (10-15°)"
    elif torso_angle_deg <= 20:
        base_cda = 0.228
        position_label = "Agresivo TT (15-20°)"
    elif torso_angle_deg <= 25:
        base_cda = 0.248
        position_label = "TT estándar (20-25°)"
    else:
        base_cda = 0.270 + (torso_angle_deg - 25) * 0.005
        position_label = f"TT abierto ({torso_angle_deg}°)"

    # Corrección por ángulo de codos (apertura lateral aumenta CdA)
    # Referencia: cada 10° de apertura de codos ≈ +0.005 m² (estimación)
    if elbow_angle_deg < 85:
        elbow_correction = -0.005
        elbow_note = "Codos muy cerrados — reducción adicional de CdA"
    elif elbow_angle_deg <= 100:
        elbow_correction = 0.0
        elbow_note = "Codos en rango óptimo para TT (85-100°)"
    else:
        elbow_correction = (elbow_angle_deg - 100) * 0.0004
        elbow_note = f"Codos abiertos — leve penalización aerodinámica"

    cda_estimated = round(base_cda + elbow_correction, 4)

    # Análisis del ángulo de cadera
    if hip_angle_deg < 45:
        hip_note = "Cadera muy cerrada — posible compromiso de potencia sostenida"
        hip_risk = "alto"
    elif hip_angle_deg <= 55:
        hip_note = "Cadera en rango óptimo para TT (45-55°) según Bini et al."
        hip_risk = "bajo"
    else:
        hip_note = "Cadera abierta — buena para potencia, menor ganancia aerodinámica"
        hip_risk = "bajo"

    # Velocidad estimada con este CdA a distintas potencias (plano, nivel del mar)
    def speed_from_power(power_w, cda, mass_kg=total_mass_kg, crr=CRR_TT_ROAD, rho=RHO_SEA_LEVEL):
        # Iteración numérica para resolver v de P = CdA*0.5*rho*v³ + Crr*m*g*v
        v = 10.0
        for _ in range(50):
            f_aero = 0.5 * rho * cda * v**3
            f_roll = crr * mass_kg * G * v
            p_calc = f_aero + f_roll
            v = v * (power_w / p_calc) ** 0.33
        return round(v * 3.6, 1)  # km/h

    return {
        "cda_estimated_m2": cda_estimated,
        "position_label": position_label,
        "inputs": {
            "torso_angle_deg": torso_angle_deg,
            "hip_angle_deg": hip_angle_deg,
            "elbow_angle_deg": elbow_angle_deg,
        },
        "corrections": {
            "elbow_correction": elbow_correction,
            "elbow_note": elbow_note,
        },
        "hip_analysis": {
            "angle_deg": hip_angle_deg,
            "note": hip_note,
            "risk_level": hip_risk,
        },
        "speed_estimates_kmh": {
            f"at_{int(p)}w": speed_from_power(p, cda_estimated)
            for p in reference_powers_w
        },
        "literature_references": {
            "Defraeye_et_al_2010": "CFD study of cyclist positions — base de los valores de referencia",
            "Blocken_et_al_2013": "Wind tunnel validation of CFD cyclist aerodynamics",
            "Bini_et_al_2014": "Hip angle and power output in cycling — rango óptimo 45-55°",
        },
        "reference_comparison": {
            k: {"cda": v, "delta": round(cda_estimated - v, 4)}
            for k, v in CDA_REFERENCE.items()
        },
    }


def calculate_cda_from_segment(
    power_watts: list[float],
    velocity_ms: list[float],
    total_mass_kg: float,
    altitude_m: float = 0,
    temperature_c: float = 15,
    crr: float = CRR_TT_ROAD,
    grade_pct: float = 0.0,
) -> dict:
    """
    Calcula CdA real de campo usando el método de Martin et al. (1998).
    Requiere segmento plano o de gradiente conocido y constante.

    power_watts: lista de potencias segundo a segundo (del stream de intervals)
    velocity_ms: lista de velocidades en m/s (del stream de intervals)
    total_mass_kg: masa total del atleta + equipo (cuerpo + bici) en kg.
                   Parámetro obligatorio — pasá tu masa real, no hay valor por defecto.
    altitude_m: altitud del segmento para cálculo de densidad de aire
    crr: coeficiente de rodadura (0.0035 TT en asfalto liso)
    grade_pct: gradiente del segmento en % (0 = plano)

    Retorna CdA estimado y métricas de calidad del segmento.
    """
    if len(power_watts) != len(velocity_ms):
        return {"error": "Las listas de potencia y velocidad deben tener el mismo largo"}
    if len(power_watts) < 30:
        return {"error": "Se necesitan al menos 30 segundos de datos para el cálculo"}

    rho = _air_density(altitude_m, temperature_c)
    grade = grade_pct / 100.0

    # Filtrar outliers (potencia 0 o velocidad < 5 m/s = 18 km/h)
    pairs = [
        (p, v) for p, v in zip(power_watts, velocity_ms)
        if p > 0 and v > 5.0
    ]
    if len(pairs) < 20:
        return {"error": "Datos insuficientes después de filtrar valores inválidos"}

    cda_values = []
    for p, v in pairs:
        # P = CdA × 0.5 × ρ × v³ + Crr × m × g × v + m × g × v × sin(θ)
        p_roll = crr * total_mass_kg * G * v
        p_grav = total_mass_kg * G * v * math.sin(math.atan(grade))
        p_aero = p - p_roll - p_grav
        if p_aero > 0:
            cda = p_aero / (0.5 * rho * v**3)
            if 0.10 < cda < 0.60:  # rango físicamente posible
                cda_values.append(cda)

    if not cda_values:
        return {"error": "No se pudo calcular CdA — verificar que el segmento sea plano y a velocidad sostenida"}

    cda_mean = sum(cda_values) / len(cda_values)
    cda_sorted = sorted(cda_values)
    n = len(cda_sorted)
    cda_median = cda_sorted[n // 2]
    cda_p25 = cda_sorted[n // 4]
    cda_p75 = cda_sorted[3 * n // 4]
    std = (sum((x - cda_mean)**2 for x in cda_values) / len(cda_values)) ** 0.5

    avg_power = sum(p for p, v in pairs) / len(pairs)
    avg_speed_kmh = sum(v for p, v in pairs) / len(pairs) * 3.6

    return {
        "cda_mean_m2": round(cda_mean, 4),
        "cda_median_m2": round(cda_median, 4),
        "cda_p25_m2": round(cda_p25, 4),
        "cda_p75_m2": round(cda_p75, 4),
        "std": round(std, 4),
        "data_quality": {
            "samples_used": len(cda_values),
            "samples_total": len(power_watts),
            "avg_power_w": round(avg_power, 1),
            "avg_speed_kmh": round(avg_speed_kmh, 1),
            "air_density_kgm3": round(rho, 4),
            "note": "Mayor calidad con segmentos > 5min, viento calmo, gradiente < 0.5%"
        },
        "method": "Martin et al. (1998) — campo libre",
        "inputs": {
            "altitude_m": altitude_m,
            "temperature_c": temperature_c,
            "total_mass_kg": total_mass_kg,
            "crr": crr,
            "grade_pct": grade_pct,
        },
    }


def compare_positions_cda(
    position_a_name: str,
    position_a_torso_deg: float,
    position_a_hip_deg: float,
    position_a_elbow_deg: float,
    position_b_name: str,
    position_b_torso_deg: float,
    position_b_hip_deg: float,
    position_b_elbow_deg: float,
    target_power_w: float,
    race_distance_km: float,
    total_mass_kg: float,
) -> dict:
    """
    Compara dos configuraciones de posición en términos de CdA estimado,
    velocidad proyectada y tiempo estimado en carrera.

    Útil para comparar posición pre/post cambio de palanca o ajuste de fit.
    target_power_w: potencia objetivo de carrera. Parámetro obligatorio.
    race_distance_km: distancia de la prueba objetivo en km. Parámetro obligatorio.
    total_mass_kg: masa total del atleta + equipo (cuerpo + bici) en kg.
                   Parámetro obligatorio — pasá tu masa real, no hay valor por defecto.
    """
    def estimate_cda(torso, elbow):
        if torso <= 10: base = 0.195
        elif torso <= 15: base = 0.210
        elif torso <= 20: base = 0.228
        elif torso <= 25: base = 0.248
        else: base = 0.270 + (torso - 25) * 0.005
        elbow_corr = 0.0 if 85 <= elbow <= 100 else (
            -0.005 if elbow < 85 else (elbow - 100) * 0.0004
        )
        return round(base + elbow_corr, 4)

    def speed_kmh(power, cda, mass=total_mass_kg, crr=CRR_TT_ROAD, rho=RHO_SEA_LEVEL):
        v = 10.0
        for _ in range(50):
            p_calc = 0.5 * rho * cda * v**3 + crr * mass * G * v
            v = v * (power / p_calc) ** 0.33
        return round(v * 3.6, 2)

    cda_a = estimate_cda(position_a_torso_deg, position_a_elbow_deg)
    cda_b = estimate_cda(position_b_torso_deg, position_b_elbow_deg)

    speed_a = speed_kmh(target_power_w, cda_a, total_mass_kg)
    speed_b = speed_kmh(target_power_w, cda_b, total_mass_kg)

    time_a_min = round((race_distance_km / speed_a) * 60, 1)
    time_b_min = round((race_distance_km / speed_b) * 60, 1)
    time_delta_sec = round((time_a_min - time_b_min) * 60, 0)

    return {
        "comparison": {
            position_a_name: {
                "torso_deg": position_a_torso_deg,
                "hip_deg": position_a_hip_deg,
                "elbow_deg": position_a_elbow_deg,
                "cda_estimated_m2": cda_a,
                "speed_at_target_power_kmh": speed_a,
                "time_at_distance_min": time_a_min,
            },
            position_b_name: {
                "torso_deg": position_b_torso_deg,
                "hip_deg": position_b_hip_deg,
                "elbow_deg": position_b_elbow_deg,
                "cda_estimated_m2": cda_b,
                "speed_at_target_power_kmh": speed_b,
                "time_at_distance_min": time_b_min,
            },
        },
        "delta": {
            "cda_diff_m2": round(cda_b - cda_a, 4),
            "speed_diff_kmh": round(speed_b - speed_a, 2),
            "time_saved_sec": time_delta_sec,
            "better_position": position_b_name if cda_b < cda_a else position_a_name,
        },
        "context": {
            "target_power_w": target_power_w,
            "race_distance_km": race_distance_km,
            "total_mass_kg": total_mass_kg,
            "note": "CdA estimado por modelo empírico (Defraeye/Blocken). Para validación precisa usar velódromo o segmento controlado con método Chung.",
        },
    }


def calculate_speed_from_power(
    power_w: float,
    total_mass_kg: float,
    cda: float = None,
    grade_pct: float = 0.0,
    altitude_m: float = 0.0,
    temperature_c: float = 15.0,
    crr: float = CRR_TT_ROAD,
) -> dict:
    """
    Calcula velocidad esperada dado un nivel de potencia y CdA.
    total_mass_kg: masa total del atleta + equipo (cuerpo + bici) en kg.
                   Parámetro obligatorio — pasá tu masa real, no hay valor por defecto.
    Si no se pasa CdA, usa un valor de referencia genérico de posición TT estándar
    (ver CDA_REFERENCE["tt_standard"]). Para un CdA propio, usar estimate_cda_from_position
    o calculate_cda_from_segment con tus datos reales.
    Útil para proyectar tiempos de carrera o segmentos.
    """
    if cda is None:
        cda = CDA_REFERENCE["tt_standard"]
        cda_source = f"Valor de referencia genérico (TT estándar) — {cda} m². Para un CdA propio, usar estimate_cda_from_position o calculate_cda_from_segment."
    else:
        cda_source = "CdA provisto manualmente"

    rho = _air_density(altitude_m, temperature_c)
    grade = grade_pct / 100.0

    v = 10.0
    for _ in range(100):
        p_aero = 0.5 * rho * cda * v**3
        p_roll = crr * total_mass_kg * G * v
        p_grav = total_mass_kg * G * v * math.sin(math.atan(grade))
        p_calc = p_aero + p_roll + p_grav
        if p_calc == 0:
            break
        v = v * (power_w / p_calc) ** 0.33

    speed_kmh = v * 3.6

    return {
        "power_w": power_w,
        "cda_m2": cda,
        "cda_source": cda_source,
        "speed_kmh": round(speed_kmh, 2),
        "grade_pct": grade_pct,
        "conditions": {
            "altitude_m": altitude_m,
            "temperature_c": temperature_c,
            "air_density": round(rho, 4),
            "crr": crr,
            "total_mass_kg": total_mass_kg,
        },
    }
