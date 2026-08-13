# intervals-icu-mcp

**Servidor MCP que conecta Claude con tus datos de entrenamiento en intervals.icu — análisis fisiológico avanzado con IA**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![MCP Protocol](https://img.shields.io/badge/protocol-MCP-orange)

---

## Qué es y para quién

`intervals-icu-mcp` expone tus datos de [intervals.icu](https://intervals.icu) — actividades, wellness, calendario, streams segundo a segundo — como herramientas invocables por Claude Desktop, más una capa de análisis fisiológico propio (CCI, corrección HRV, aerodinámica de campo) construida encima. Corre localmente: Claude Desktop se conecta al servidor vía [MCP](https://modelcontextprotocol.io) (stdio), y el servidor habla con la API de intervals.icu usando tu API key.

No es un dashboard más. Permite análisis que hoy no existen en ninguna plataforma de entrenamiento: separar fatiga simpática de mejora aeróbica real cruzando HRV Z-Score con potencia y FC, detectar cuándo el "costo cardíaco" bajo es en realidad supresión cardíaca y no eficiencia, o estimar tu CdA en el aire a partir de ángulos de posición sin pasar por un túnel de viento. Todo conversacional, en lenguaje natural, con memoria persistente entre sesiones.

---

## Quick start

1. **Cloná el repo**
   ```bash
   git clone https://github.com/<tu-usuario>/intervals-icu-mcp.git
   cd intervals-icu-mcp
   ```

2. **Instalá todo con un comando**
   ```bash
   python install.py
   ```
   Crea el entorno virtual, instala las dependencias y copia los archivos de configuración de ejemplo (`.env`, `SYSTEM_PROMPT.md`, `athlete_profile.json`).

3. **Editá `.env`** con tus credenciales de intervals.icu:
   - `INTERVALS_ATHLETE_ID` — se ve en la URL: `https://intervals.icu/athlete/i12345` → tu ID es `i12345`
   - `INTERVALS_API_KEY` — generala en intervals.icu → **Settings → Developer Settings → API Key**

4. **Conectá Claude Desktop automáticamente**
   ```bash
   python setup_claude.py
   ```
   Detecta tu sistema operativo, encuentra `claude_desktop_config.json` y agrega la entrada del servidor sin tocar el resto de tu configuración (otros MCPs quedan intactos). Te muestra el JSON antes de escribir y pide confirmación.

5. **Reiniciá Claude Desktop.** Debería aparecer el ícono de herramientas con los tools de `intervals-icu` disponibles.

---

## Features principales

- **Full CRUD de intervals.icu** — actividades, wellness, calendario, sport settings.
- **Streams segundo a segundo** — potencia, FC, cadencia, velocidad, altitud, para análisis fino.
- **Análisis de archivos `.fit` locales** — sin depender de que la actividad esté subida a intervals.icu.
- **CCI (Cardiac Cost Index)** — métrica propia de eficiencia cardíaca (`FC / %FTP`) que separa trabajo real de laps de recuperación.
- **Corrección HRV Z-Score** — distingue fatiga simpática de adaptación real cuando el CCI baja.
- **Matriz Freshness Ratio (HRV × TSB)** — 4 cuadrantes clínicos (fresco, carga óptima, sobrecarga aguda, fatiga no funcional) en vez de mirar el TSB aislado.
- **Detección de supresión cardíaca** — identifica cuándo una FC baja es agotamiento del SNA, no mejora de eficiencia.
- **Aerodinámica** — CdA estimado por posición y CdA real de campo (método Martin et al., 1998).
- **Perfil biomecánico persistente** — historial de fitting, ángulos de posición, lesiones, contexto de entrenamiento.
- **Memoria SQLite local** — snapshots semanales y por sesión para tendencias longitudinales sin regastar tokens en refetch.

---

## Tools disponibles (48)

### Actividades (7)
| Tool | Descripción |
|---|---|
| `get_recent_activities` | Actividades de los últimos N días con todos los KPIs de intervals.icu |
| `get_activity_detail` | Detalle completo de una actividad por ID, incluyendo intervalos y streams |
| `get_activity_streams` | Streams segundo a segundo (potencia, FC, cadencia, velocidad, altitud) |
| `get_activity_intervals` | Laps/intervalos de una actividad |
| `get_activities_by_sport` | Filtra actividades por deporte (Ride, Run, Swim, ...) en los últimos N días |
| `create_manual_activity` | Crea una actividad manual en intervals.icu |
| `update_activity` | Actualiza nombre, descripción, RPE o feel de una actividad existente |

### Fitness y zonas (4)
| Tool | Descripción |
|---|---|
| `get_fitness_stats` | Histórico de CTL/ATL/TSB de los últimos N días |
| `get_current_fitness` | Snapshot actual de CTL/ATL/TSB con interpretación |
| `get_sport_settings` | Configuración completa de zonas y FTP para un deporte |
| `update_sport_settings` | Actualiza FTP o LTHR para un deporte en intervals.icu |

### Wellness (3)
| Tool | Descripción |
|---|---|
| `get_wellness` | HRV, FC reposo, sueño, peso, fatiga subjetiva de los últimos N días |
| `get_today_wellness` | Registro de wellness de hoy |
| `update_wellness` | Registra o actualiza wellness para una fecha específica |

### Perfil del atleta (3)
| Tool | Descripción |
|---|---|
| `get_athlete_profile` | Perfil completo con FTP, LTHR, zonas y modelo MMP |
| `get_upcoming_events` | Carreras y eventos tipo A/B/C en el calendario |
| `get_power_zones` | Zonas de potencia calculadas desde el FTP de ciclismo |

### Calendario (7)
| Tool | Descripción |
|---|---|
| `get_planned_workouts` | Workouts planificados para los próximos N días |
| `get_todays_plan` | Todos los eventos de hoy: workouts, notas y targets |
| `get_calendar_events` | Eventos del calendario en un rango de fechas |
| `create_workout` | Crea un evento/workout en el calendario |
| `create_weekly_plan` | Crea múltiples workouts de una sola vez |
| `update_event` | Modifica un evento existente del calendario |
| `delete_event` | Elimina un evento del calendario |

### Archivos .fit (3)
| Tool | Descripción |
|---|---|
| `list_fit_files` | Lista los archivos `.fit` disponibles en `fit_files/` |
| `analyze_fit_file` | Análisis detallado: potencia, picos 1/5/20/60min, FC, cadencia, zonas |
| `get_fit_raw_summary` | Explora los tipos de mensaje y campos disponibles de un `.fit` |

### Perfil extendido (5)
| Tool | Descripción |
|---|---|
| `get_athlete_extended_profile` | Perfil biomecánico: fitting, ángulos, historial, lesiones, contexto |
| `update_bike_fit` | Actualiza los datos de fitting de la bici en el perfil local |
| `add_fit_history_entry` | Registra un cambio de fitting con métricas antes/después |
| `add_injury` | Registra una lesión o molestia en el historial |
| `update_training_notes` | Actualiza las notas generales del perfil del atleta |

### Aerodinámica (4)
| Tool | Descripción |
|---|---|
| `estimate_cda_from_position` | Estima el CdA a partir de ángulos de torso, cadera y codo |
| `calculate_cda_from_segment` | CdA real de campo — método de Martin et al. (1998) |
| `compare_positions_cda` | Compara dos posiciones en CdA, velocidad y tiempo de carrera proyectado |
| `calculate_speed_from_power` | Velocidad esperada dado un nivel de potencia y CdA |

### Análisis avanzado (3)
| Tool | Descripción |
|---|---|
| `analyze_session` | CCI por intervalo, EF por zona, HR drift, corrección HRV por Z-Score |
| `compare_sessions` | Compara N sesiones equivalentes para detectar tendencias de adaptación |
| `get_session_ef_curve` | Curva de EF por zona a lo largo del tiempo para un tipo de sesión |

### Memoria y tendencias (9)
| Tool | Descripción |
|---|---|
| `save_weekly_snapshot` | Guarda o actualiza el snapshot semanal de KPIs en SQLite |
| `get_kpi_trends` | Tendencias de KPIs de las últimas N semanas desde la BD local |
| `get_kpi_alerts` | Alertas de KPIs activas o resueltas |
| `save_kpi_alert` | Registra una alerta de KPI en la BD |
| `save_agent_note` | Guarda una observación o insight persistente del agente |
| `get_agent_notes` | Recupera notas del agente de los últimos N días |
| `get_weekly_snapshot` | Trae el snapshot de una semana específica |
| `save_session_metrics` | Guarda el resultado de `analyze_session` en la BD local |
| `get_session_history` | Historial de CCI/EF desde la BD local, con tendencia calculada |

---

## Estructura del proyecto

```
intervals-icu-mcp/
├── install.py                     ← Instalador: venv + dependencias + config
├── setup_claude.py                ← Configura Claude Desktop automáticamente
├── requirements.txt
├── .env.example                   ← Plantilla de credenciales
├── SYSTEM_PROMPT.example.md       ← Plantilla del rol/persona del agente
├── athlete_profile.example.json   ← Plantilla del perfil biomecánico
├── fit_files/                     ← Tus archivos .fit locales
├── db/                            ← SQLite (se crea automáticamente)
└── server/
    ├── main.py                    ← Entry point: registra todos los tools
    ├── config.py                  ← Configuración (lee .env)
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

## Personalización

- **`SYSTEM_PROMPT.md`** — copiá `SYSTEM_PROMPT.example.md` (lo hace `install.py` automáticamente) y completá los placeholders (`{ATHLETE_NAME}`, `{FTP}`, `{MAX_HR}`, etc.) con tus datos. Ahí vive la persona del agente y las reglas de interpretación de CCI/HRV — son universales, no hace falta tocarlas.
- **`athlete_profile.json`** — copiá `athlete_profile.example.json` y completá tu fitting (largo de palanca, ángulos de posición), historial de lesiones y contexto de entrenamiento. Lo usan `get_athlete_extended_profile` y las tools de aerodinámica.
- **`SESSION_POWER_THRESHOLD`** — en `server/tools/analytics.py`, define el umbral de potencia (% FTP) que separa un lap de trabajo real de calentamiento/recuperación, por tipo de sesión (`BIKE_FTP`, `RUN_LONG`, etc.). Ajustalo si tu forma de estructurar sesiones difiere de la nomenclatura estándar.

---

## Ejemplos de consultas

```
"Mostrame mis actividades de la última semana"
"Analizá mi última sesión de FTP — quiero el CCI y el drift"
"Compará mis últimos 4 BIKE_FTP y decime si estoy mejorando"
"Estimá mi CdA con la posición actual"
"¿Cómo está mi CTL de cara a mi próxima carrera?"
```

---

## Tecnología

- **Stack:** Python 3.10+, [FastMCP](https://github.com/jlowin/fastmcp), `httpx`, `fitparse`, SQLite
- **Protocolo:** [MCP (Model Context Protocol)](https://modelcontextprotocol.io)
- **Transporte:** stdio (local) — cada usuario corre su propio servidor, sin backend compartido

---

## Limitaciones

- Requiere Claude Desktop (o cualquier cliente MCP compatible con stdio).
- Un usuario = un atleta (single-tenant); no está pensado para múltiples atletas en la misma instancia.
- Sin tests automatizados ni CI.
- Sin deploy remoto — corre localmente, no hay versión hosteada.

---

## Contribuciones

¿Querés agregar un tool, arreglar un bug o mejorar el análisis? Mirá [CONTRIBUTING.md](CONTRIBUTING.md) para el flujo de trabajo y las convenciones del proyecto.

---

## Licencia

[MIT](LICENSE)
