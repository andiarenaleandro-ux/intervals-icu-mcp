# Contribuir a intervals-icu-mcp

Gracias por el interés en contribuir. Este documento cubre cómo agregar un tool nuevo, reportar bugs y el flujo de pull requests.

## Cómo agregar un tool nuevo

El patrón es simple — registrar un tool nuevo son tres pasos:

1. **Creá la función async** en `server/tools/<modulo>.py` (o un módulo nuevo si no encaja en ninguno existente). Cada tool es una función async que llama a la API de intervals.icu con `httpx.AsyncClient()` y `settings.auth()`, o lee/escribe el estado local (SQLite, `athlete_profile.json`).

   ```python
   async def get_algo(param: str) -> dict:
       """
       Descripción corta de qué hace y cuándo usarlo.
       param: qué espera este parámetro y en qué formato.
       """
       settings.validate()
       async with httpx.AsyncClient() as client:
           r = await client.get(
               f"{settings.base_url}/algo/{param}",
               auth=settings.auth(),
               timeout=15,
           )
           r.raise_for_status()
       return r.json()
   ```

2. **Importala en `server/main.py`**, junto con las demás funciones del mismo módulo.

3. **Agregala a la lista de registro** en el loop `for fn in [...]` de `main.py`, bajo el comentario de categoría correspondiente (o uno nuevo si es una categoría nueva).

Eso es todo — `mcp.tool()(fn)` la expone automáticamente. No hay un registro central separado ni decoradores adicionales que mantener sincronizados.

Si el tool nuevo agrega una categoría al README, actualizá también la tabla de tools y el conteo en la sección "Tools disponibles".

## Cómo reportar bugs

Abrí un issue con:
- Qué esperabas que pasara vs. qué pasó.
- El tool o flujo involucrado (ej: `analyze_session` con una actividad sin FTP configurado).
- El error completo si lo hay (traceback, no solo el mensaje final).
- Versión de Python y sistema operativo.

No incluyas tu `INTERVALS_API_KEY`, `ATHLETE_ID` ni contenido de `athlete_profile.json`/`SYSTEM_PROMPT.md` en el issue — son datos personales, no hace falta para reproducir la mayoría de los bugs.

## Convenciones de código

- **Async por defecto** para cualquier tool que hable con la API de intervals.icu — usa `httpx.AsyncClient()`, nunca `requests` ni llamadas síncronas bloqueantes.
- **`settings.validate()`** al inicio de todo tool que dependa de credenciales, antes de la primera llamada HTTP.
- **Docstrings descriptivos** — son lo que Claude lee para decidir cuándo usar el tool y cómo pasarle los parámetros. Explicá qué hace, el formato esperado de cada parámetro no obvio (fechas como `'YYYY-MM-DD'`, IDs, escalas 1-7 vs 1-10), y cuándo conviene usarlo sobre otro tool similar.
- **Sin comentarios que expliquen el qué** — el código y los nombres ya lo dicen. Comentarios solo para el *por qué* cuando no es obvio (una regla de negocio no evidente, un workaround a una particularidad de la API de intervals.icu).
- **No hardcodees datos personales** — FTP, LTHR, peso, nombre del atleta, fechas de carrera. Estos valores se leen de `.env`, `SYSTEM_PROMPT.md`, `athlete_profile.json` o se resuelven dinámicamente desde intervals.icu (ver `_resolve_ftp` en `analytics.py` como referencia).
- **No hay tests automatizados todavía** — probá el tool corriendo el servidor y llamándolo desde Claude Desktop antes de abrir el PR.

## Pull requests

1. Forkeá el repo.
2. Creá una branch descriptiva: `git checkout -b feature/nombre-del-cambio` o `fix/bug-que-arregla`.
3. Hacé el cambio siguiendo las convenciones de arriba.
4. Verificá que el módulo compila (`python -m py_compile server/tools/tu_modulo.py`) y probá el flujo manualmente contra tu propia cuenta de intervals.icu.
5. Abrí el PR contra `main` con una descripción de qué cambia y por qué. Si agrega un tool, mencioná en qué categoría del README debería listarse.
