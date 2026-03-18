# Publication TODO

Test locally first. Publish when ready.

## 1. Docker MCP Catalog

No blockers. Dockerfile builds successfully.

### Steps
1. Fork `https://github.com/docker/mcp-registry`
2. Create `servers/open-search/` directory with:
   - `server.yaml` — server config (type: poci, category: search, tags)
   - `tools.json` — tool definitions for `search` and `extract`
   - `readme.md` — link to GitHub repo README
3. Install task runner: `go install github.com/go-task/task/v3/cmd/task@latest`
4. Validate: `task validate -- --name open-search`
5. Build: `task build -- --tools open-search`
6. Open PR following `.github/PULL_REQUEST_TEMPLATE.md`
7. Docker team reviews, builds, signs, and publishes image to `mcp/open-search`

### What Docker provides after approval
- Image at `hub.docker.com/mcp/open-search`
- Cryptographic signatures and provenance tracking
- SBOMs (Software Bill of Materials)
- Automatic security updates
- Listing in Docker Desktop MCP Toolkit

## 2. PyPI Publishing

Required before MCP Registry submission. Not required for Docker Catalog.

### Steps
1. Check package name availability: `pip index versions open-search-mcp`
2. Add `mcp-name: io.github.andresfortunato/raw-web-search` to README.md (registry verification marker)
3. Build: `uv build`
4. Create PyPI account if needed: https://pypi.org/account/register/
5. Create API token: https://pypi.org/manage/account/token/
6. Upload: `twine upload dist/*`
7. Verify: `pip install open-search-mcp` works

### After PyPI
- Users can install via `uvx open-search-mcp` (no git URL needed)
- Unblocks MCP Registry submission

## 3. Official MCP Registry

Blocked on PyPI publishing.

### Steps
1. Install publisher: `brew install mcp-publisher` (or download binary from GitHub releases)
2. Authenticate: `mcp-publisher login github`
3. Verify `server.json` matches schema: `mcp-publisher init` (compare with existing)
4. Publish: `mcp-publisher publish`
5. Verify: server appears at `registry.modelcontextprotocol.io`

### Registry entry format
Already created at `server.json`:
- Namespace: `io.github.andresfortunato/raw-web-search`
- Package: `open-search-mcp` on PyPI
- Schema: `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`

## 4. Claude Code Plugin

Research needed. Not started.

### What we know
- Plugins are GitHub repos with specific structure
- Can bundle MCP server config + CLAUDE.md instructions
- Discoverable via `/plugin` → Discover tab in Claude Code
- May need separate repo (`andresfortunato/raw-web-search-plugin`)

### Steps
1. Research exact plugin format (read Claude Code plugin docs)
2. Create plugin structure
3. Test with `claude plugin add`
4. Submit to marketplace (if open for community submissions)

## Order of Operations

```
Local testing (current)
  → Docker MCP Catalog (no blockers)
  → PyPI publishing (when ready for wider distribution)
  → MCP Registry (after PyPI)
  → Claude Code Plugin (after research)
```
