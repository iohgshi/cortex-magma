# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cortex-magma is an MCP (Model Context Protocol) server built with FastMCP, plus a client script for manual testing. Package management is via `uv`; Python 3.12.

## Commands

```bash
uv sync                      # install dependencies from uv.lock
uv run cortex-magma          # start the MCP server (HTTP transport, 0.0.0.0:8000)
make test                    # run tests (needs the server already up, see Makefile)
uv add <package>             # add a dependency (updates pyproject.toml and uv.lock)
uv run pytest                # run the full test suite
```

There is no linter configured.

## Architecture

Each tool module owns its registration explicitly; nothing registers as an import side effect:

- `src/cortex_magma/server.py` — entry point and sole owner of the `FastMCP("cortex-magma")` instance. It calls `tools.register(mcp)`, then runs HTTP transport (`transport="http"`) on port 8000 (client endpoint: `http://127.0.0.1:8000/mcp`). Do not put `mcp.run()` at module level — other modules import `mcp` from here. `main()` is the console-script entry point.
- `src/cortex_magma/tools/` — one module per tool domain (e.g. `greet.py`). Every module exposes plain functions plus a `register(mcp)` that calls `mcp.tool(fn, name=..., description=...)`. Tool functions must stay importable and callable on their own, without going through a registered instance. Long tool descriptions live in module-level constants (`*_DESCRIPTION`) using triple-quoted strings.
- `src/cortex_magma/tools/__init__.py` — aggregates the per-module `register` functions. When adding a new tool module, add it to `_MODULES` and have it expose `register(mcp)`.

Code lives under `src/` so the project is a real installable package (hatchling, `[tool.hatch.build.targets.wheel] packages = ["src/cortex_magma"]`). Tests connect over HTTP to a running server — start it before running tests.

## Conventions

- Tool descriptions, docstrings, and comments are written in Chinese (Simplified); keep new ones consistent.
- Tool parameters use `typing.Annotated` with Pydantic `Field` descriptions so schemas are self-documenting for LLM clients.
