"""
Aerodynamic analysis tools for TT cycling.
Based on the cycling power model (Martin et al., 1998)
and the virtual elevation method (Chung, 2012).
"""
import math
from typing import Optional
from server.config import settings


# ── Physical constants ───────────────────────────────────────────────────────
RHO_SEA_LEVEL = 1.2256   # kg/m³ — air density at sea level, 15°C
G = 9.8067               # m/s²
CRR_TT_ROAD = 0.0035     # rolling resistance coefficient (TT, smooth asphalt)
CRR_TT_ROUGH = 0.0042    # rough asphalt

# Reference CdA by position (Defraeye et al., 2010; Blocken et al., 2013)
# Typical wind tunnel and CFD values
CDA_REFERENCE = {
    "road_hoods":       0.388,  # hands on hoods
    "road_drops":       0.342,  # hands on drops
    "road_aero":        0.307,  # crouched on drops
    "tt_standard":      0.265,  # standard TT, torso ~20-25°
    "tt_aggressive":    0.230,  # aggressive TT, torso ~15-20°
    "tt_very_aggressive": 0.210, # very aggressive TT, torso < 15°
    "tt_world_class":   0.185,  # optimized elite TT
}


def _air_density(altitude_m: float = 0, temp_c: float = 15) -> float:
    """Calculates air density based on altitude and temperature."""
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
    Estimates CdA from the athlete's position angles on the bike.
    Uses empirical models from the literature (Defraeye et al., Blocken et al.).

    torso_angle_deg: torso angle relative to horizontal (lower = more aero)
    hip_angle_deg: hip angle at TDC between torso and femur
    elbow_angle_deg: angle between torso and humerus in aero position
    total_mass_kg: total mass of athlete + equipment (body + bike) in kg, used
                   for the speed estimates. Required parameter.
    reference_powers_w: power levels (W) at which speed is estimated.
                        If not passed, uses generic values [200, 250, 300].

    Returns the estimated CdA and a comparison against literature references.
    """
    if reference_powers_w is None:
        reference_powers_w = [200, 250, 300]
    # Empirical model based on torso angle (main driver of CdA in TT)
    # Approximate regression from Defraeye et al. (2010) and Blocken et al. (2013) data
    if torso_angle_deg <= 10:
        base_cda = 0.195
        position_label = "Extremely aggressive (< 10°)"
    elif torso_angle_deg <= 15:
        base_cda = 0.210
        position_label = "Very aggressive (10-15°)"
    elif torso_angle_deg <= 20:
        base_cda = 0.228
        position_label = "Aggressive TT (15-20°)"
    elif torso_angle_deg <= 25:
        base_cda = 0.248
        position_label = "Standard TT (20-25°)"
    else:
        base_cda = 0.270 + (torso_angle_deg - 25) * 0.005
        position_label = f"Open TT ({torso_angle_deg}°)"

    # Correction for elbow angle (lateral flare increases CdA)
    # Reference: each 10° of elbow flare ≈ +0.005 m² (estimate)
    if elbow_angle_deg < 85:
        elbow_correction = -0.005
        elbow_note = "Elbows very tucked — additional CdA reduction"
    elif elbow_angle_deg <= 100:
        elbow_correction = 0.0
        elbow_note = "Elbows in optimal TT range (85-100°)"
    else:
        elbow_correction = (elbow_angle_deg - 100) * 0.0004
        elbow_note = f"Elbows flared — slight aerodynamic penalty"

    cda_estimated = round(base_cda + elbow_correction, 4)

    # Hip angle analysis
    if hip_angle_deg < 45:
        hip_note = "Hip very closed — possible compromise to sustained power"
        hip_risk = "high"
    elif hip_angle_deg <= 55:
        hip_note = "Hip in optimal TT range (45-55°) per Bini et al."
        hip_risk = "low"
    else:
        hip_note = "Open hip — good for power, less aerodynamic gain"
        hip_risk = "low"

    # Estimated speed with this CdA at different power levels (flat, sea level)
    def speed_from_power(power_w, cda, mass_kg=total_mass_kg, crr=CRR_TT_ROAD, rho=RHO_SEA_LEVEL):
        # Numerical iteration to solve v for P = CdA*0.5*rho*v³ + Crr*m*g*v
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
            "Defraeye_et_al_2010": "CFD study of cyclist positions — basis for the reference values",
            "Blocken_et_al_2013": "Wind tunnel validation of CFD cyclist aerodynamics",
            "Bini_et_al_2014": "Hip angle and power output in cycling — optimal range 45-55°",
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
    Calculates real field CdA using the Martin et al. (1998) method.
    Requires a flat segment or one with known, constant gradient.

    power_watts: second-by-second power list (from the intervals stream)
    velocity_ms: speed list in m/s (from the intervals stream)
    total_mass_kg: total mass of athlete + equipment (body + bike) in kg.
                   Required parameter — pass your real mass, there's no default.
    altitude_m: segment altitude for air density calculation
    crr: rolling resistance coefficient (0.0035 for TT on smooth asphalt)
    grade_pct: segment gradient in % (0 = flat)

    Returns the estimated CdA and segment quality metrics.
    """
    if len(power_watts) != len(velocity_ms):
        return {"error": "The power and velocity lists must have the same length"}
    if len(power_watts) < 30:
        return {"error": "At least 30 seconds of data are needed for the calculation"}

    rho = _air_density(altitude_m, temperature_c)
    grade = grade_pct / 100.0

    # Filter outliers (power 0 or speed < 5 m/s = 18 km/h)
    pairs = [
        (p, v) for p, v in zip(power_watts, velocity_ms)
        if p > 0 and v > 5.0
    ]
    if len(pairs) < 20:
        return {"error": "Insufficient data after filtering invalid values"}

    cda_values = []
    for p, v in pairs:
        # P = CdA × 0.5 × ρ × v³ + Crr × m × g × v + m × g × v × sin(θ)
        p_roll = crr * total_mass_kg * G * v
        p_grav = total_mass_kg * G * v * math.sin(math.atan(grade))
        p_aero = p - p_roll - p_grav
        if p_aero > 0:
            cda = p_aero / (0.5 * rho * v**3)
            if 0.10 < cda < 0.60:  # physically plausible range
                cda_values.append(cda)

    if not cda_values:
        return {"error": "Could not calculate CdA — check that the segment is flat and at sustained speed"}

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
            "note": "Higher quality with segments > 5min, calm wind, gradient < 0.5%"
        },
        "method": "Martin et al. (1998) — free-field",
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
    Compares two position setups in terms of estimated CdA,
    projected speed, and estimated race time.

    Useful for comparing position pre/post crank length change or fit adjustment.
    target_power_w: target race power. Required parameter.
    race_distance_km: target race distance in km. Required parameter.
    total_mass_kg: total mass of athlete + equipment (body + bike) in kg.
                   Required parameter — pass your real mass, there's no default.
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
            "note": "CdA estimated with an empirical model (Defraeye/Blocken). For precise validation, use a velodrome or a controlled segment with the Chung method.",
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
    Calculates expected speed given a power level and CdA.
    total_mass_kg: total mass of athlete + equipment (body + bike) in kg.
                   Required parameter — pass your real mass, there's no default.
    If CdA isn't passed, uses a generic standard-TT-position reference value
    (see CDA_REFERENCE["tt_standard"]). For your own CdA, use estimate_cda_from_position
    or calculate_cda_from_segment with your real data.
    Useful for projecting race or segment times.
    """
    if cda is None:
        cda = CDA_REFERENCE["tt_standard"]
        cda_source = f"Generic reference value (standard TT) — {cda} m². For your own CdA, use estimate_cda_from_position or calculate_cda_from_segment."
    else:
        cda_source = "CdA provided manually"

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
