# intervals-icu-mcp

Servidor MCP para analizar tus datos de entrenamiento desde **intervals.icu**
y archivos **.fit** directamente en Claude Desktop.

---

## Estructura

```
intervals-icu-mcp/
├── .env                    ← Tus credenciales (no se sube al repo)
├── .env.example            ← Plantilla de variables
├── requirements.txt
├── fit_files/              ← Poné acá tus .fit para analizar
└── server/
    ├── main.py             ← Entry point del MCP
    ├── config.py           ← Settings
    └── tools/
        ├── activities.py   ← Actividades recientes y detalle
        ├── fitness.py      ← CTL / ATL / TSB
        ├── wellness.py     ← HRV, sueño, fatiga subjetiva
        ├── athlete.py      ← Perfil, zonas, eventos
        └── fit_parser.py   ← Análisis de archivos .fit locales
```

---

## Setup

### 1. Entorno virtual

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac/Linux

pip install -r requirements.txt
```

### 2. Variables de entorno

```bash
copy .env.example .env        # Windows
cp .env.example .env          # Mac/Linux
```

Editá `.env` con:
- `INTERVALS_ATHLETE_ID`: lo ves en la URL de intervals.icu → `https://intervals.icu/athlete/i12345`
- `INTERVALS_API_KEY`: intervals.icu → Settings → API

### 3. Conectar a Claude Desktop

Abrí el config de Claude Desktop:
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`

Agregá el servidor (ajustá la ruta a donde clonaste el proyecto):

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "C:\\ruta\\al\\proyecto\\.venv\\Scripts\\python.exe",
      "args": ["-m", "server.main"],
      "cwd": "C:\\ruta\\al\\proyecto\\intervals-icu-mcp"
    }
  }
}
```

Reiniciá Claude Desktop. Debería aparecer el martillo con los tools disponibles.

---

## Tools disponibles

| Tool | Descripción |
|---|---|
| `get_recent_activities` | Actividades de los últimos N días |
| `get_activity_detail` | Detalle completo de una actividad |
| `get_activity_intervals` | Laps/intervalos de una actividad |
| `get_activities_by_sport` | Filtrar por Ride / Run / Swim |
| `get_fitness_stats` | Histórico CTL/ATL/TSB |
| `get_current_fitness` | Estado actual de forma/fatiga |
| `get_wellness` | HRV, sueño, fatiga subjetiva (N días) |
| `get_today_wellness` | Wellness de hoy |
| `get_athlete_profile` | FTP, LTHR, zonas configuradas |
| `get_upcoming_events` | Carreras en el calendario |
| `get_power_zones` | Zonas de potencia calculadas desde FTP |
| `list_fit_files` | Archivos .fit disponibles en fit_files/ |
| `analyze_fit_file` | Análisis detallado de un .fit |
| `get_fit_raw_summary` | Explorar estructura de un .fit |

---

## Uso con archivos .fit

1. Copiá el archivo `.fit` (descargado de Garmin Connect o intervals.icu) a la carpeta `fit_files/`
2. En Claude Desktop: *"listá los archivos .fit disponibles"*
3. *"Analizá el archivo [nombre].fit en detalle"*

---

## Ejemplos de consultas

```
"Mostrame el resumen de mi última semana de entrenamiento"
"¿Cómo está mi CTL y TSB hoy?"
"Analizá el .fit del martes, quiero ver los picos de potencia a 5 y 20 minutos"
"¿Puedo meter una sesión de calidad mañana o estoy muy fatigado?"
"Mostrame mi wellness de los últimos 10 días cruzado con la carga"
"¿Cuántos días faltan para mi próxima carrera?"
```
