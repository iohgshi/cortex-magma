# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cortex-magma is an MCP (Model Context Protocol) server built with FastMCP, plus a client script for manual testing. Package management is via `uv`; Python 3.12.

## Commands

```bash
uv sync                      # install dependencies from uv.lock
uv run server.py             # start the MCP server (HTTP transport, 0.0.0.0:8000)
uv run client.py             # smoke-test client — must be run with the server already up
uv add <package>             # add a dependency (updates pyproject.toml and uv.lock)
```

There is no test suite or linter configured.

## Architecture

Tool registration happens at import time via decorators on a shared instance:

- `app.py` — the shared `FastMCP("cortex-magma")` instance. Every tool module imports `mcp` from here (this avoids circular imports through the entry point).
- `tools/` — one module per tool domain (e.g. `tools/greet.py`). `tools/__init__.py` imports each module to trigger registration; when adding a new tool module, add a line there. Long tool descriptions live in module-level constants (`*_DESCRIPTION`) using triple-quoted strings.
- `server.py` — entry point: imports `tools` (side-effect registration), then runs HTTP transport (`transport="http"`) on port 8000 (client endpoint: `http://127.0.0.1:8000/mcp`).
- `client.py` — a throwaway-style test harness that connects to the running server, lists tools with their input schemas, and calls them to verify behavior. When adding or changing a tool, update the calls here to match.

## Conventions

- Tool descriptions, docstrings, and comments are written in Chinese (Simplified); keep new ones consistent.
- Tool parameters use `typing.Annotated` with Pydantic `Field` descriptions so schemas are self-documenting for LLM clients.
