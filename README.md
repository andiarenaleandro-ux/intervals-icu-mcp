# intervals-icu-mcp

**MCP server that connects Claude to your training data on intervals.icu — advanced physiological analysis with AI**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![MCP Protocol](https://img.shields.io/badge/protocol-MCP-orange)

---

## What it is and who it's for

`intervals-icu-mcp` exposes your [intervals.icu](https://intervals.icu) data — activities, wellness, calendar, second-by-second streams — as tools callable by Claude Desktop, plus a layer of proprietary physiological analysis (CCI, HRV correction, field aerodynamics) built on top. It runs locally: Claude Desktop connects to the server via [MCP](https://modelcontextprotocol.io) (stdio), and the server talks to the intervals.icu API using your API key.

It's not just another dashboard. It enables analysis that doesn't exist today in any training platform: separating sympathetic fatigue from real aerobic improvement by cross-referencing HRV Z-Score with power and heart rate, detecting when a lower "cardiac cost" is actually cardiac suppression rather than efficiency, or estimating your CdA in the air from position angles without setting foot in a wind tunnel. All conversational, in natural language, with persistent memory across sessions.

---

## Quick start

1. **Clone the repo**
   ```bash
   git clone https://github.com/<your-username>/intervals-icu-mcp.git
   cd intervals-icu-mcp
   ```

2. **Install everything with one command**
   ```bash
   python install.py
   ```
   Creates the virtual environment, installs dependencies, and copies the example config files (`.env`, `SYSTEM_PROMPT.md`, `athlete_profile.json`).

3. **Edit `.env`** with your intervals.icu credentials:
   - `INTERVALS_ATHLETE_ID` — visible in the URL: `https://intervals.icu/athlete/i12345` → your ID is `i12345`
   - `INTERVALS_API_KEY` — generate it in intervals.icu → **Settings → Developer Settings → API Key**

4. **Connect Claude Desktop automatically**
   ```bash
   python setup_claude.py
   ```
   Detects your operating system, finds `claude_desktop_config.json`, and adds the server entry without touching the rest of your configuration (other MCPs stay intact). Shows you the JSON before writing and asks for confirmation.

5. **Restart Claude Desktop.** The tools icon should appear with the `intervals-icu` tools available.

---

## Main features

- **Full CRUD for intervals.icu** — activities, wellness, calendar, sport settings.
- **Second-by-second streams** — power, heart rate, cadence, speed, elevation, for fine-grained analysis.
- **Local `.fit` file analysis** — no need for the activity to be uploaded to intervals.icu.
- **CCI (Cardiac Cost Index)** — proprietary cardiac efficiency metric (`HR / %FTP`) that separates real work from recovery laps.
- **HRV Z-Score correction** — distinguishes sympathetic fatigue from real adaptation when CCI drops.
- **Freshness Ratio matrix (HRV × TSB)** — 4 clinical quadrants (fresh, optimal load, acute overload, non-functional overreaching) instead of looking at TSB in isolation.
- **Cardiac suppression detection** — identifies when a lower heart rate is autonomic nervous system exhaustion, not improved efficiency.
- **Aerodynamics** — estimated CdA from position and real field CdA (Martin et al. 1998 method).
- **Persistent biomechanical profile** — fitting history, position angles, injuries, training context.
- **Local SQLite memory** — weekly and per-session snapshots for longitudinal trends without re-spending tokens on refetches.

---

## Available tools (48)

### Activities (7)
| Tool | Description |
|---|---|
| `get_recent_activities` | Activities from the last N days with all intervals.icu KPIs |
| `get_activity_detail` | Full detail of an activity by ID, including intervals and streams |
| `get_activity_streams` | Second-by-second streams (power, HR, cadence, speed, elevation) |
| `get_activity_intervals` | Laps/intervals of an activity |
| `get_activities_by_sport` | Filters activities by sport (Ride, Run, Swim, ...) over the last N days |
| `create_manual_activity` | Creates a manual activity in intervals.icu |
| `update_activity` | Updates name, description, RPE, or feel of an existing activity |

### Fitness & zones (4)
| Tool | Description |
|---|---|
| `get_fitness_stats` | CTL/ATL/TSB history for the last N days |
| `get_current_fitness` | Current CTL/ATL/TSB snapshot with interpretation |
| `get_sport_settings` | Full zone and FTP configuration for a sport |
| `update_sport_settings` | Updates FTP or LTHR for a sport in intervals.icu |

### Wellness (3)
| Tool | Description |
|---|---|
| `get_wellness` | HRV, resting HR, sleep, weight, subjective fatigue for the last N days |
| `get_today_wellness` | Today's wellness record |
| `update_wellness` | Records or updates wellness for a specific date |

### Athlete profile (3)
| Tool | Description |
|---|---|
| `get_athlete_profile` | Full profile with FTP, LTHR, zones, and MMP model |
| `get_upcoming_events` | Type A/B/C races and events on the calendar |
| `get_power_zones` | Power zones calculated from cycling FTP |

### Calendar (7)
| Tool | Description |
|---|---|
| `get_planned_workouts` | Planned workouts for the next N days |
| `get_todays_plan` | All of today's events: workouts, notes, and targets |
| `get_calendar_events` | Calendar events over a date range |
| `create_workout` | Creates an event/workout on the calendar |
| `create_weekly_plan` | Creates multiple workouts at once |
| `update_event` | Modifies an existing calendar event |
| `delete_event` | Deletes a calendar event |

### .fit files (3)
| Tool | Description |
|---|---|
| `list_fit_files` | Lists the `.fit` files available in `fit_files/` |
| `analyze_fit_file` | Detailed analysis: power, 1/5/20/60min peaks, HR, cadence, zones |
| `get_fit_raw_summary` | Explores the message types and fields available in a `.fit` file |

### Extended profile (5)
| Tool | Description |
|---|---|
| `get_athlete_extended_profile` | Biomechanical profile: fitting, angles, history, injuries, context |
| `update_bike_fit` | Updates the bike fitting data in the local profile |
| `add_fit_history_entry` | Records a fitting change with before/after metrics |
| `add_injury` | Records an injury or issue in the history |
| `update_training_notes` | Updates the athlete's general profile notes |

### Aerodynamics (4)
| Tool | Description |
|---|---|
| `estimate_cda_from_position` | Estimates CdA from torso, hip, and elbow angles |
| `calculate_cda_from_segment` | Real field CdA — Martin et al. (1998) method |
| `compare_positions_cda` | Compares two positions in CdA, speed, and projected race time |
| `calculate_speed_from_power` | Expected speed given a power level and CdA |

### Advanced analytics (3)
| Tool | Description |
|---|---|
| `analyze_session` | CCI per interval, EF by zone, HR drift, HRV Z-Score correction |
| `compare_sessions` | Compares N equivalent sessions to detect adaptation trends |
| `get_session_ef_curve` | EF-by-zone curve over time for a session type |

### Memory & trends (9)
| Tool | Description |
|---|---|
| `save_weekly_snapshot` | Saves or updates the weekly KPI snapshot in SQLite |
| `get_kpi_trends` | KPI trends for the last N weeks from the local DB |
| `get_kpi_alerts` | Active or resolved KPI alerts |
| `save_kpi_alert` | Records a KPI alert in the DB |
| `save_agent_note` | Saves a persistent observation or insight from the agent |
| `get_agent_notes` | Retrieves agent notes from the last N days |
| `get_weekly_snapshot` | Fetches the snapshot for a specific week |
| `save_session_metrics` | Saves the result of `analyze_session` in the local DB |
| `get_session_history` | CCI/EF history from the local DB, with calculated trend |

---

## Project structure

```
intervals-icu-mcp/
├── install.py                     ← Installer: venv + dependencies + config
├── setup_claude.py                ← Configures Claude Desktop automatically
├── requirements.txt
├── .env.example                   ← Credentials template
├── SYSTEM_PROMPT.example.md       ← Agent role/persona template
├── athlete_profile.example.json   ← Biomechanical profile template
├── fit_files/                     ← Your local .fit files
├── db/                            ← SQLite (created automatically)
└── server/
    ├── main.py                    ← Entry point: registers all tools
    ├── config.py                  ← Configuration (reads .env)
    └── tools/
        ├── activities.py
        ├── fitness.py
        ├── wellness.py
        ├── athlete.py
        ├── calendar.py
        ├── fit_parser.py
        ├── profile.py
        ├── aerodynamics.py
        ├── analytics.py
        └── memory.py
```

---

## Customization

- **`SYSTEM_PROMPT.md`** — copy `SYSTEM_PROMPT.example.md` (`install.py` does this automatically) and fill in the placeholders (`{ATHLETE_NAME}`, `{FTP}`, `{MAX_HR}`, etc.) with your data. This is where the agent's persona and the CCI/HRV interpretation rules live — those are universal, no need to touch them.
- **`athlete_profile.json`** — copy `athlete_profile.example.json` and fill in your fitting (crank length, position angles), injury history, and training context. Used by `get_athlete_extended_profile` and the aerodynamics tools.
- **`SESSION_POWER_THRESHOLD`** — in `server/tools/analytics.py`, defines the power threshold (% FTP) that separates a real work lap from warmup/recovery, per session type (`BIKE_FTP`, `RUN_LONG`, etc.). Adjust it if the way you structure sessions differs from the standard naming convention.

---

## Example queries

```
"Show me my activities from the last week"
"Analyze my last FTP session — I want the CCI and the drift"
"Compare my last 4 BIKE_FTP sessions and tell me if I'm improving"
"Estimate my CdA with my current position"
"How's my CTL looking ahead of my next race?"
```

---

## Technology

- **Stack:** Python 3.10+, [FastMCP](https://github.com/jlowin/fastmcp), `httpx`, `fitparse`, SQLite
- **Protocol:** [MCP (Model Context Protocol)](https://modelcontextprotocol.io)
- **Transport:** stdio (local) — each user runs their own server, no shared backend

---

## Limitations

- Requires Claude Desktop (or any MCP client compatible with stdio).
- One user = one athlete (single-tenant); not designed for multiple athletes on the same instance.
- No automated tests or CI.
- No remote deployment — runs locally, no hosted version.

---

## Contributing

Want to add a tool, fix a bug, or improve the analysis? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow and project conventions.

---

## License

[MIT](LICENSE)
