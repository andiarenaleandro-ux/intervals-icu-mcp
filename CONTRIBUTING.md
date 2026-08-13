# Contributing to intervals-icu-mcp

Thanks for your interest in contributing. This document covers how to add a new tool, how to report bugs, and the pull request workflow.

## How to add a new tool

The pattern is simple — registering a new tool takes three steps:

1. **Create the async function** in `server/tools/<module>.py` (or a new module if it doesn't fit any existing one). Each tool is an async function that calls the intervals.icu API with `httpx.AsyncClient()` and `settings.auth()`, or reads/writes local state (SQLite, `athlete_profile.json`).

   ```python
   async def get_something(param: str) -> dict:
       """
       Short description of what it does and when to use it.
       param: what this parameter expects and in what format.
       """
       settings.validate()
       async with httpx.AsyncClient() as client:
           r = await client.get(
               f"{settings.base_url}/something/{param}",
               auth=settings.auth(),
               timeout=15,
           )
           r.raise_for_status()
       return r.json()
   ```

2. **Import it in `server/main.py`**, alongside the other functions from the same module.

3. **Add it to the registration list** in the `for fn in [...]` loop in `main.py`, under the matching category comment (or a new one if it's a new category).

That's it — `mcp.tool()(fn)` exposes it automatically. There's no separate central registry or extra decorators to keep in sync.

If the new tool adds a category to the README, also update the tools table and the count in the "Available tools" section.

## How to report bugs

Open an issue with:
- What you expected to happen vs. what actually happened.
- The tool or flow involved (e.g., `analyze_session` on an activity with no FTP configured).
- The full error if there is one (traceback, not just the final message).
- Python version and operating system.

Don't include your `INTERVALS_API_KEY`, `ATHLETE_ID`, or the contents of `athlete_profile.json`/`SYSTEM_PROMPT.md` in the issue — those are personal data, and they're not needed to reproduce most bugs.

## Code conventions

- **Async by default** for any tool that talks to the intervals.icu API — use `httpx.AsyncClient()`, never `requests` or blocking synchronous calls.
- **`settings.validate()`** at the start of every tool that depends on credentials, before the first HTTP call.
- **Descriptive docstrings** — these are what Claude reads to decide when to use the tool and how to pass its parameters. Explain what it does, the expected format for any non-obvious parameter (dates like `'YYYY-MM-DD'`, IDs, 1-7 vs. 1-10 scales), and when it's preferable over a similar tool.
- **No comments explaining the what** — the code and the names already do that. Comments only for the *why* when it's not obvious (a non-evident business rule, a workaround for a quirk in the intervals.icu API).
- **Don't hardcode personal data** — FTP, LTHR, weight, athlete name, race dates. These values are read from `.env`, `SYSTEM_PROMPT.md`, `athlete_profile.json`, or resolved dynamically from intervals.icu (see `_resolve_ftp` in `analytics.py` for reference).
- **No automated tests yet** — test the tool by running the server and calling it from Claude Desktop before opening the PR.

## Pull requests

1. Fork the repo.
2. Create a descriptive branch: `git checkout -b feature/short-description` or `fix/bug-being-fixed`.
3. Make the change following the conventions above.
4. Verify the module compiles (`python -m py_compile server/tools/your_module.py`) and manually test the flow against your own intervals.icu account.
5. Open the PR against `main` with a description of what changes and why. If it adds a tool, mention which README category it should be listed under.
