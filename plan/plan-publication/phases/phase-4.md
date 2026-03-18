# Phase 4: Claude Code Plugin

## Intent
Package raw-web-search as a Claude Code plugin so users can install it via `/plugin` → Discover tab. This bundles the MCP server config + CLAUDE.md instruction into a one-click install.

## Key Context
Claude Code plugins are GitHub repos with a specific structure. They can include:
- **Skills** (slash commands)
- **Agents** (custom agents)
- **Hooks** (pre/post tool execution)
- **MCP Server configurations** (what we need)

The plugin would configure the MCP server and add the CLAUDE.md instruction that makes Claude prefer our search tools over WebSearch.

## Research Needed
- Exact plugin directory structure (read Claude Code plugin docs)
- How to declare an MCP server dependency in a plugin
- How to get listed in the Discover tab (Anthropic-managed? Community submission?)
- Whether a plugin can add to CLAUDE.md automatically or just recommend it

## Tasks

### 4.1: Research plugin format
- Read Claude Code plugin documentation
- Look at existing plugins for structure reference
- Determine: can a plugin auto-configure an MCP server?
- Verification: understand the exact file structure needed

### 4.2: Create plugin repo structure
- May be a separate repo (e.g., `andresfortunato/raw-web-search-plugin`) or a directory in this repo
- Plugin manifest with name, description, MCP server config
- CLAUDE.md instruction bundled as a skill or hook
- Verification: plugin structure matches spec

### 4.3: Test plugin installation
- Install via `claude plugin add` or equivalent
- Verify MCP server is configured
- Verify search preference instruction is active
- Verification: `search` tool available, Claude prefers it over WebSearch

### 4.4: Submit to Claude Code marketplace
- Determine submission process (Anthropic review? Self-publish?)
- Submit if possible
- Verification: plugin discoverable via `/plugin` → Discover

## Done when
- Plugin repo/structure created
- Plugin installs correctly
- MCP server auto-configured on install
- Submitted to marketplace (if open for submissions)

## Open Questions
- Is the Claude Code plugin marketplace open for community submissions?
- Can plugins bundle MCP server configs, or do users still need to run `claude mcp add` manually?
- Should this be a separate repo or part of this repo?
