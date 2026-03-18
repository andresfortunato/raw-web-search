# Phase 1: GitHub Repo Polish

## Intent
Make the repo presentable for public visitors. Every other publication channel links back to GitHub — this is the foundation.

## Tasks

### 1.1: Add LICENSE file
- Create `LICENSE` with MIT text (already declared in pyproject.toml, but no actual file)
- Verification: `LICENSE` exists at repo root

### 1.2: Fix pyproject.toml URLs
- Change URLs from `raw-web-search/raw-web-search` to `andresfortunato/raw-web-search` (actual repo)
- Verification: URLs point to the real repo

### 1.3: Clean up development artifacts
- Move `research/`, `archive/`, `brainstorms/`, `plan/`, `progress.md` to a `dev/` directory or add to `.gitignore`
- Decision needed: keep in repo (useful for transparency) or remove (cleaner for visitors)?
- Recommendation: move to `dev/` — keeps history accessible but doesn't clutter the root
- Verification: repo root only has production files

### 1.4: Update README Architecture section
- `searxng/settings.yml` reference should mention it's generated from template
- Verification: README matches actual file structure

### 1.5: Set GitHub repo metadata
- Description: "Open source MCP search server for Claude Code. Replaces WebSearch + WebFetch."
- Topics: `mcp`, `claude-code`, `search`, `web-search`, `searxng`, `mcp-server`
- Verification: visible on GitHub repo page (use `gh` CLI)

### 1.6: Verify install path works
- Test `uvx --from git+https://github.com/andresfortunato/raw-web-search.git raw-web-search` from a clean environment
- Verification: command runs without error, MCP server starts

## Done when
- LICENSE file exists
- pyproject.toml URLs correct
- Root directory is clean (no dev artifacts)
- README matches actual structure
- GitHub repo has description + topics
- Install path verified
