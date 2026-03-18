# Publication Plan: raw-web-search

## Goal

Publish raw-web-search across 4 channels: polished GitHub repo, Official MCP Registry, Docker MCP Catalog, and Claude Code Plugin marketplace. Each channel reaches a different audience and has different prerequisites.

## Constraints

- **No PyPI publishing yet** — install via `uvx --from git+...` or Docker
- **Don't break existing install path** — `claude mcp add open-search -- uvx --from git+...` must keep working
- **research/ files are internal** — move to a dev-only location or gitignore, not in published artifacts
- **Docker image must be self-contained** — users shouldn't need to clone the repo to use the Docker image
- **Plugin must be minimal** — just the MCP server config + CLAUDE.md instruction, not a full distribution

## Decisions Made

- **Secret key**: Generated at runtime from template (already implemented)
- **Default search preference**: Via CLAUDE.md instruction (already in README)
- **Playwright**: Optional dep, not bundled in base Docker image (too heavy)
- **pyproject.toml URLs**: Need updating from `raw-web-search` org to `andresfortunato` (actual GitHub user)

## Repo Context

```
src/open_search_mcp/     # Python package (server, searcher, extractor, chunker, cache)
tests/                   # 15 tests
docker-compose.yml       # SearXNG + Redis
searxng/settings.yml.template  # SearXNG config template
.github/workflows/tests.yml    # CI
research/                # Internal benchmarks, evals (10 files)
archive/, brainstorms/, plan/  # Development artifacts
progress.md              # Decision log
```

## Phases

### Phase 1: GitHub Repo Polish
- Intent: Make the repo presentable for public visitors
- Prerequisite for: all other phases
- See: `phases/phase-1.md`

### Phase 2: Docker Image + MCP Catalog
- Intent: Self-contained Docker image, submitted to Docker MCP Catalog
- Depends on: Phase 1 (clean repo)
- See: `phases/phase-2.md`

### Phase 3: Official MCP Registry
- Intent: Register in the official MCP server registry
- Depends on: Phase 1 (clean repo, server.json)
- See: `phases/phase-3.md`

### Phase 4: Claude Code Plugin
- Intent: Bundle as installable Claude Code plugin
- Depends on: Phase 1 (clean repo)
- See: `phases/phase-4.md`

## Phase Dependencies

```
Phase 1 (repo polish)
  ├── Phase 2 (Docker + catalog)
  ├── Phase 3 (MCP registry)
  └── Phase 4 (Claude Code plugin)
```

Phases 2-4 are independent of each other and can be done in parallel after Phase 1.
