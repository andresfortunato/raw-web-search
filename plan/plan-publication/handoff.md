# Publication Plan — Handoff

## Current Status
Plan written. No phases started.

## Start with
Phase 1 (GitHub repo polish) — prerequisite for everything else. Tasks 1.1-1.5 are all independent and can be done in parallel. Task 1.6 (verify install) should be last.

## Key decisions still needed
- **Phase 1, Task 1.3**: Keep `research/` in repo (transparency) or move to `dev/` (cleaner)? User should decide.
- **Phase 2**: Single Docker image (supervisord) vs compose profile? Recommended: single image for catalog, compose for dev.
- **Phase 3**: Need to verify if MCP registry accepts git URLs or requires PyPI.
- **Phase 4**: Need to research Claude Code plugin format — exact structure is unknown.

## Session boundary
Phase 1 is small enough for one session. Phases 2-4 may each need their own session due to external dependencies (Docker Hub, MCP registry, plugin marketplace).
