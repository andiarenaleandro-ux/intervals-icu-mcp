from pathlib import Path
from fastmcp import FastMCP

_prompt_path = Path(__file__).parent.parent / "SYSTEM_PROMPT.md"
_instructions = _prompt_path.read_text(encoding="utf-8") if _prompt_path.exists() else ""

mcp = FastMCP(name="intervals-icu-mcp", instructions=_instructions)

from server.tools.activities import (
    get_recent_activities, get_activity_detail, get_activity_streams,
    get_activity_intervals, get_activities_by_sport,
    create_manual_activity, update_activity,
)
from server.tools.fitness import (
    get_fitness_stats, get_current_fitness,
    get_sport_settings, update_sport_settings,
)
from server.tools.wellness import (
    get_wellness, get_today_wellness, update_wellness,
)
from server.tools.athlete import (
    get_athlete_profile, get_upcoming_events, get_power_zones,
)
from server.tools.calendar import (
    get_planned_workouts, get_todays_plan, get_calendar_events,
    create_workout, create_weekly_plan, update_event, delete_event,
)
from server.tools.fit_parser import (
    list_fit_files, analyze_fit_file, get_fit_raw_summary,
)
from server.tools.profile import (
    get_athlete_extended_profile, update_bike_fit,
    add_fit_history_entry, add_injury, update_training_notes,
)
from server.tools.aerodynamics import (
    estimate_cda_from_position, calculate_cda_from_segment,
    compare_positions_cda, calculate_speed_from_power,
)
from server.tools.memory import (
    save_weekly_snapshot, get_kpi_trends,
    get_kpi_alerts, save_kpi_alert,
    save_agent_note, get_agent_notes,
    get_weekly_snapshot,
    save_session_metrics, get_session_history,
)
from server.tools.analytics import (
    analyze_session,
    compare_sessions,
    get_session_ef_curve,
)

for fn in [
    # Activities
    get_recent_activities, get_activity_detail, get_activity_streams,
    get_activity_intervals, get_activities_by_sport,
    create_manual_activity, update_activity,
    # Fitness & zones
    get_fitness_stats, get_current_fitness,
    get_sport_settings, update_sport_settings,
    # Wellness
    get_wellness, get_today_wellness, update_wellness,
    # Athlete
    get_athlete_profile, get_upcoming_events, get_power_zones,
    # Calendar
    get_planned_workouts, get_todays_plan, get_calendar_events,
    create_workout, create_weekly_plan, update_event, delete_event,
    # Local .fit
    list_fit_files, analyze_fit_file, get_fit_raw_summary,
    # Extended profile
    get_athlete_extended_profile, update_bike_fit,
    add_fit_history_entry, add_injury, update_training_notes,
    # Aerodynamics
    estimate_cda_from_position, calculate_cda_from_segment,
    compare_positions_cda, calculate_speed_from_power,
    # Memory & trends
    save_weekly_snapshot, get_kpi_trends,
    get_kpi_alerts, save_kpi_alert,
    save_agent_note, get_agent_notes,
    get_weekly_snapshot,
    save_session_metrics, get_session_history,
    # Analytics (CCI, EF por zona, tendencias)
    analyze_session, compare_sessions, get_session_ef_curve,
]:
    mcp.tool()(fn)

if __name__ == "__main__":
    mcp.run()
