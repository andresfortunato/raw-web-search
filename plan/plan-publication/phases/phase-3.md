# Phase 3: Official MCP Registry

## Intent
Register raw-web-search in the official MCP server registry at `modelcontextprotocol.io`. This makes it discoverable by any MCP client, not just Claude Code.

## Prerequisites
- The registry requires a published package (PyPI or npm). Since we're skipping PyPI, we need to check if git+https URLs are accepted as package locations.
- If git URLs aren't accepted, we may need to do a minimal PyPI publish after all — just `python -m build && twine upload`.

## Tasks

### 3.1: Research registry requirements
- Read `github.com/modelcontextprotocol/registry` for exact submission format
- Determine if `git+https://` is accepted as a server location
- Check if `mcp-publisher` CLI is required or if manual PR is accepted
- Verification: clear understanding of what's needed

### 3.2: Create server.json
- Format per MCP registry spec
- Namespace: `io.github.andresfortunato/raw-web-search`
- Server location: git URL or PyPI package name
- Tools: `search`, `extract`
- Environment variables documented
- Verification: valid JSON matching registry schema

### 3.3: Publish to PyPI (if required by registry)
- Only if git URLs aren't accepted
- Minimal publish: `uv build && twine upload dist/*`
- Ensure package name `raw-web-search` is available
- Verification: `pip install raw-web-search` works

### 3.4: Submit to registry
- Use `mcp-publisher` CLI or manual PR to `modelcontextprotocol/registry`
- Verification: PR submitted and accepted

## Done when
- server.json created and validated
- Submitted to MCP registry (PR or CLI)
- Server appears in registry listing
