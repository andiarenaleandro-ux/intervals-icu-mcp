"""
Persistent memory engine for trend analysis.
Saves weekly KPI snapshots to local SQLite.
The agent writes here after each analysis and reads to detect trends.
"""
import sqlite3
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "db" / "snapshots.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS weekly_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL UNIQUE,
            sport TEXT NOT NULL DEFAULT 'Ride',
            -- Load
            tss_total REAL,
            hours_total REAL,
            sessions_count INTEGER,
            -- Aerobic KPIs (average of that sport's sessions that week)
            ef_avg REAL,
            ef_z2_avg REAL,
            decoupling_avg REAL,
            vi_avg REAL,
            -- Form
            ctl_end REAL,
            atl_end REAL,
            tsb_end REAL,
            -- Wellness
            hrv_avg REAL,
            sleep_avg REAL,
            resting_hr_avg REAL,
            -- Power
            peak_1min_w REAL,
            peak_5min_w REAL,
            peak_20min_w REAL,
            np_avg REAL,
            -- Running dynamics
            cadence_avg REAL,
            ground_contact_avg REAL,
            vertical_ratio_avg REAL,
            -- CdA
            cda_field REAL,
            -- Metadata
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS kpi_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            sport TEXT,
            metric TEXT,
            value REAL,
            threshold REAL,
            message TEXT,
            resolved INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT,
            note TEXT NOT NULL,
            tags TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def save_weekly_snapshot(
    week_start: str,
    sport: str = "Ride",
    tss_total: Optional[float] = None,
    hours_total: Optional[float] = None,
    sessions_count: Optional[int] = None,
    ef_avg: Optional[float] = None,
    ef_z2_avg: Optional[float] = None,
    decoupling_avg: Optional[float] = None,
    vi_avg: Optional[float] = None,
    ctl_end: Optional[float] = None,
    atl_end: Optional[float] = None,
    tsb_end: Optional[float] = None,
    hrv_avg: Optional[float] = None,
    sleep_avg: Optional[float] = None,
    resting_hr_avg: Optional[float] = None,
    peak_1min_w: Optional[float] = None,
    peak_5min_w: Optional[float] = None,
    peak_20min_w: Optional[float] = None,
    np_avg: Optional[float] = None,
    cadence_avg: Optional[float] = None,
    ground_contact_avg: Optional[float] = None,
    vertical_ratio_avg: Optional[float] = None,
    cda_field: Optional[float] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Saves or updates the weekly KPI snapshot.
    week_start: Monday of the week, format 'YYYY-MM-DD'
    sport: 'Ride', 'Run', 'Swim'
    Call after analyzing a week to persist the calculated KPIs.
    """
    conn = _get_conn()
    conn.execute("""
        INSERT INTO weekly_snapshots (
            week_start, sport, tss_total, hours_total, sessions_count,
            ef_avg, ef_z2_avg, decoupling_avg, vi_avg,
            ctl_end, atl_end, tsb_end,
            hrv_avg, sleep_avg, resting_hr_avg,
            peak_1min_w, peak_5min_w, peak_20min_w, np_avg,
            cadence_avg, ground_contact_avg, vertical_ratio_avg,
            cda_field, notes, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(week_start) DO UPDATE SET
            tss_total=excluded.tss_total,
            hours_total=excluded.hours_total,
            sessions_count=excluded.sessions_count,
            ef_avg=excluded.ef_avg,
            ef_z2_avg=excluded.ef_z2_avg,
            decoupling_avg=excluded.decoupling_avg,
            vi_avg=excluded.vi_avg,
            ctl_end=excluded.ctl_end,
            atl_end=excluded.atl_end,
            tsb_end=excluded.tsb_end,
            hrv_avg=excluded.hrv_avg,
            sleep_avg=excluded.sleep_avg,
            resting_hr_avg=excluded.resting_hr_avg,
            peak_1min_w=excluded.peak_1min_w,
            peak_5min_w=excluded.peak_5min_w,
            peak_20min_w=excluded.peak_20min_w,
            np_avg=excluded.np_avg,
            cadence_avg=excluded.cadence_avg,
            ground_contact_avg=excluded.ground_contact_avg,
            vertical_ratio_avg=excluded.vertical_ratio_avg,
            cda_field=excluded.cda_field,
            notes=excluded.notes,
            updated_at=CURRENT_TIMESTAMP
    """, (
        week_start, sport, tss_total, hours_total, sessions_count,
        ef_avg, ef_z2_avg, decoupling_avg, vi_avg,
        ctl_end, atl_end, tsb_end,
        hrv_avg, sleep_avg, resting_hr_avg,
        peak_1min_w, peak_5min_w, peak_20min_w, np_avg,
        cadence_avg, ground_contact_avg, vertical_ratio_avg,
        cda_field, notes,
    ))
    conn.commit()
    conn.close()
    return {"saved": True, "week_start": week_start, "sport": sport}


def get_kpi_trends(
    weeks: int = 8,
    sport: str = "Ride",
    metrics: Optional[list[str]] = None,
) -> dict:
    """
    Fetches KPI trends for the last N weeks from the local DB.
    Automatically detects whether a KPI is improving, stable, or declining.
    sport: 'Ride', 'Run'
    metrics: optional list of metrics to filter (None = all)
    """
    conn = _get_conn()
    rows = conn.execute("""
        SELECT * FROM weekly_snapshots
        WHERE sport = ?
        ORDER BY week_start DESC
        LIMIT ?
    """, (sport, weeks)).fetchall()
    conn.close()

    if not rows:
        return {
            "message": f"No data in DB for {sport}. Use save_weekly_snapshot to start recording.",
            "weeks_requested": weeks,
        }

    data = [dict(r) for r in reversed(rows)]

    def trend(values: list) -> str:
        clean = [v for v in values if v is not None]
        if len(clean) < 3:
            return "insufficient"
        recent = sum(clean[-3:]) / 3
        older = sum(clean[:3]) / 3
        delta_pct = ((recent - older) / older * 100) if older else 0
        if delta_pct > 3:
            return f"↑ improving ({delta_pct:+.1f}%)"
        elif delta_pct < -3:
            return f"↓ declining ({delta_pct:+.1f}%)"
        else:
            return f"→ stable ({delta_pct:+.1f}%)"

    all_metrics = ["ef_avg", "ef_z2_avg", "decoupling_avg", "vi_avg",
                   "ctl_end", "tsb_end", "peak_5min_w", "peak_20min_w",
                   "np_avg", "hrv_avg", "tss_total", "hours_total"]

    target_metrics = metrics or all_metrics

    trends = {}
    for metric in target_metrics:
        values = [r.get(metric) for r in data]
        clean = [v for v in values if v is not None]
        if clean:
            trends[metric] = {
                "trend": trend(values),
                "latest": clean[-1],
                "avg_period": round(sum(clean) / len(clean), 3),
                "min": min(clean),
                "max": max(clean),
                "history": [
                    {"week": r["week_start"], "value": r.get(metric)}
                    for r in data
                ],
            }

    return {
        "sport": sport,
        "weeks_analyzed": len(data),
        "period": f"{data[0]['week_start']} → {data[-1]['week_start']}",
        "trends": trends,
    }


def get_kpi_alerts(resolved: bool = False) -> list[dict]:
    """
    Fetches active KPI alerts (or resolved ones if resolved=True).
    Alerts are generated automatically when a KPI crosses a threshold.
    """
    conn = _get_conn()
    rows = conn.execute("""
        SELECT * FROM kpi_alerts
        WHERE resolved = ?
        ORDER BY created_at DESC
        LIMIT 50
    """, (1 if resolved else 0,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_kpi_alert(
    alert_type: str,
    message: str,
    metric: Optional[str] = None,
    value: Optional[float] = None,
    threshold: Optional[float] = None,
    sport: Optional[str] = None,
) -> dict:
    """
    Records a KPI alert in the DB.
    alert_type: 'overreaching', 'ef_drop', 'decoupling_high',
                'peak_power_drop', 'ramp_rate_high', 'improvement'
    Call when a significant pattern is detected.
    """
    conn = _get_conn()
    conn.execute("""
        INSERT INTO kpi_alerts (date, alert_type, sport, metric, value, threshold, message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date.today().isoformat(), alert_type, sport, metric, value, threshold, message))
    conn.commit()
    conn.close()
    return {"saved": True, "alert_type": alert_type}


def save_agent_note(
    note: str,
    category: str = "general",
    tags: Optional[list[str]] = None,
) -> dict:
    """
    Saves an agent note to the DB.
    Use to record observations, detected patterns,
    recommendations, or any insight that should persist across sessions.
    category: 'performance', 'biomechanics', 'nutrition', 'recovery', 'general'
    """
    conn = _get_conn()
    conn.execute("""
        INSERT INTO agent_notes (date, category, note, tags)
        VALUES (?, ?, ?, ?)
    """, (
        date.today().isoformat(),
        category,
        note,
        json.dumps(tags or []),
    ))
    conn.commit()
    conn.close()
    return {"saved": True, "category": category}


def get_agent_notes(
    days: int = 30,
    category: Optional[str] = None,
) -> list[dict]:
    """
    Retrieves agent notes from the last N days.
    Use at the start of each session to recall previous context.
    """
    conn = _get_conn()
    query = """
        SELECT * FROM agent_notes
        WHERE date >= ?
        {}
        ORDER BY created_at DESC
    """.format("AND category = ?" if category else "")

    params = [(date.today() - timedelta(days=days)).isoformat()]
    if category:
        params.append(category)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        {**dict(r), "tags": json.loads(r["tags"] or "[]")}
        for r in rows
    ]


def get_weekly_snapshot(week_start: str, sport: str = "Ride") -> dict:
    """
    Fetches the snapshot for a specific week.
    week_start: 'YYYY-MM-DD' (Monday of the week)
    """
    conn = _get_conn()
    row = conn.execute("""
        SELECT * FROM weekly_snapshots
        WHERE week_start = ? AND sport = ?
    """, (week_start, sport)).fetchone()
    conn.close()
    if not row:
        return {"message": f"No snapshot for week {week_start} / {sport}"}
    return dict(row)


# ── Session metrics (CCI, EF by zone, trends) ────────────────────────────────

def _init_session_metrics(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            activity_id TEXT NOT NULL UNIQUE,
            session_type TEXT NOT NULL,
            sport TEXT,
            duration_min REAL,
            ftp_used REAL,
            -- CCI
            cci_avg REAL,
            cci_normalized REAL,
            cci_per_interval TEXT,  -- JSON
            -- EF
            ef_global REAL,
            ef_by_zone TEXT,        -- JSON {Z2: {ef, avg_power, avg_hr}, ...}
            -- HR
            hr_drift_pct REAL,
            decoupling_pct REAL,
            variability_index REAL,
            -- Load
            tss REAL,
            np_w REAL,
            -- Day context
            hrv_day REAL,
            hrv_factor REAL,
            hrv_interpretation TEXT,
            tsb_day REAL,
            -- Flags
            flags TEXT,             -- JSON ["HRV_LOW", ...]
            -- Metadata
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


def save_session_metrics(session_data: dict) -> dict:
    """
    Saves the result of analyze_session to the local DB.
    Always call after analyze_session to persist the KPIs.
    The DB is the source of truth for longitudinal trends.
    """
    conn = _get_conn()
    _init_session_metrics(conn)

    try:
        conn.execute("""
            INSERT INTO session_metrics (
                date, activity_id, session_type, sport, duration_min, ftp_used,
                cci_avg, cci_normalized, cci_per_interval,
                ef_global, ef_by_zone,
                hr_drift_pct, decoupling_pct, variability_index,
                tss, np_w,
                hrv_day, hrv_factor, hrv_interpretation, tsb_day,
                flags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                cci_avg=excluded.cci_avg,
                cci_normalized=excluded.cci_normalized,
                ef_by_zone=excluded.ef_by_zone,
                flags=excluded.flags
        """, (
            session_data.get("date"),
            str(session_data.get("activity_id")),
            session_data.get("session_type"),
            session_data.get("sport"),
            session_data.get("duration_min"),
            session_data.get("ftp_used"),
            session_data.get("cci_avg"),
            session_data.get("cci_normalized"),
            json.dumps(session_data.get("cci_per_interval") or []),
            session_data.get("ef_global"),
            json.dumps(session_data.get("ef_by_zone") or {}),
            session_data.get("hr_drift_pct"),
            session_data.get("decoupling_pct"),
            session_data.get("variability_index"),
            session_data.get("tss"),
            session_data.get("np_w"),
            session_data.get("hrv_day"),
            session_data.get("hrv_factor"),
            session_data.get("hrv_interpretation"),
            session_data.get("tsb_day"),
            json.dumps(session_data.get("flags") or []),
        ))
        conn.commit()
        return {"saved": True, "activity_id": session_data.get("activity_id"), "session_type": session_data.get("session_type")}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_session_history(
    session_type: str,
    weeks: int = 12,
    sport: str = None,
) -> dict:
    """
    Fetches CCI and EF history from the local DB for a session type.
    Calculates trends over the saved data.
    Use for longitudinal analysis without spending tokens on intervals.icu calls.
    """
    conn = _get_conn()
    _init_session_metrics(conn)

    oldest = (date.today() - timedelta(weeks=weeks)).isoformat()
    query = """
        SELECT * FROM session_metrics
        WHERE session_type = ? AND date >= ?
        ORDER BY date ASC
    """
    params = [session_type, oldest]
    if sport:
        query = query.replace("ORDER BY", "AND sport = ? ORDER BY")
        params.insert(2, sport)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return {
            "session_type": session_type,
            "message": "No data in DB. Use analyze_session + save_session_metrics to get started.",
            "weeks_requested": weeks,
        }

    data = [dict(r) for r in rows]
    for d in data:
        d["cci_per_interval"] = json.loads(d.get("cci_per_interval") or "[]")
        d["ef_by_zone"] = json.loads(d.get("ef_by_zone") or "{}")
        d["flags"] = json.loads(d.get("flags") or "[]")

    # Calculate CCI_normalized trend
    cci_values = [d["cci_normalized"] or d["cci_avg"] for d in data if d.get("cci_avg")]

    def trend_label(values):
        if len(values) < 3:
            return "insufficient"
        first = sum(values[:3]) / 3
        last = sum(values[-3:]) / 3
        delta = ((last - first) / first) * 100
        if delta < -3: return f"REAL_IMPROVEMENT ({delta:.1f}%)"
        if delta < -1: return f"SLIGHT_IMPROVEMENT ({delta:.1f}%)"
        if delta <= 1: return f"PLATEAU ({delta:.1f}%)"
        if delta <= 3: return f"SLIGHT_DECLINE (+{delta:.1f}%)"
        return f"REAL_DECLINE (+{delta:.1f}%)"

    return {
        "session_type": session_type,
        "sessions_count": len(data),
        "period": f"{data[0]['date']} → {data[-1]['date']}",
        "cci_trend": trend_label(cci_values),
        "cci_latest": cci_values[-1] if cci_values else None,
        "cci_first": cci_values[0] if cci_values else None,
        "sessions": data,
    }
