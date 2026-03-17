# Open Search MCP: Conversation Context Export

> Exported from the initial research & prototyping conversation (2026-03-16).
> This document captures all key decisions, findings, and open work so a new session can continue without re-deriving anything.

## What We Built So Far

An MCP search server with two tools (`search`, `extract`) using:
- **SearXNG** (Docker, self-hosted) as search backend — aggregates 70+ search engines
- **Trafilatura** (F1: 0.958) for HTML → markdown content extraction
- **BM25** (rank_bm25) for relevance scoring
- **httpx** for async concurrent fetching
- **Python MCP SDK** (FastMCP) for the MCP server interface

### Files
- `server.py` — MCP server entry point, tool definitions, pipeline orchestration
- `searcher.py` — SearXNG client + BM25 scoring
- `extractor.py` — async URL fetching + trafilatura extraction
- `docker-compose.yml` — SearXNG + Redis
- `searxng/settings.yml` — SearXNG config (JSON format enabled, rate limiter off)
- `pyproject.toml` — Python project config
- `research/search-mcp-analysis.md` — Full feasibility analysis (Tavily, MCP ecosystem, building blocks)

### Current State: Working MVP
- SearXNG returns results from Google, Brave, DuckDuckGo, Startpage
- Trafilatura extracts clean markdown from fetched pages
- BM25 scores and ranks results
- MCP server initializes correctly and exposes both tools
- End-to-end pipeline tested and functional

## Key Research Findings

### Problem: Claude Code's Built-in Web Tools Are Suboptimal
- **WebSearch**: Returns only titles+URLs (no content), forces separate WebFetch calls
- **WebFetch**: Secretly runs a Haiku 3.5 summarization (125-char quote limit, paraphrases everything), lossy and expensive. Can hang indefinitely (no timeout). 403s on Wikipedia. Domain preflight blocked by VPNs/firewalls. No JS rendering.
- Both tools can't be auto-approved in permissions config

### Tavily A/B Testing Results (Critical Finding)
We ran identical queries through Tavily and our tool. The key discovery:

**Tavily returns ~706 tokens per query. We return ~11,266 tokens. That's 16x more.**

Tavily's `content` field is NOT the full page — it's focused NLP-selected chunks:
- Average per result: **565 chars** (~141 tokens)
- Range: 131-1,180 chars per result
- The text appears to be **verbatim excerpts** (not LLM-rewritten) — selected chunks most relevant to the query

Our tool returns full extracted pages:
- Average per result: **9,013 chars** (~2,253 tokens)
- Range: 157-19,872 chars per result

### Extraction Success Rate: 76%
Across 8 queries × 10 results each:
- 61/80 pages extracted successfully
- 19/80 snippet-only (extraction failed)
- Main blockers: Reddit (403), Medium (403), various sites with anti-bot protection
- Snippet quality: avg 224 chars, most are 100-300 chars with useful content

## Decisions Made

### 1. Snippet Handling: Tag, Don't Penalize
When extraction fails (24% of the time), include the SearXNG snippet tagged as `[snippet]`.
Don't apply scoring penalties — the LLM reading results is smart enough to judge relevance.
Rationale: Many snippet-only results (especially Reddit) contain highly relevant practitioner insights.
**Status: Decision made, not yet implemented in code.**

### 2. Content Selection: Embeddings-Based Chunk Selection
The core problem: we return full pages (~9K chars each) when Tavily returns focused excerpts (~500 chars).
The solution is NOT truncation — it's **selecting the most query-relevant paragraphs**.

Pipeline change needed:
```
Current:  Extract full page → truncate at char limit → return
Target:   Extract full page → split into paragraphs → embed query + paragraphs → cosine similarity → return top chunks
```

**Target: ~500 chars per result** (matching Tavily's output profile). Start there, expand if quality is insufficient.

### 3. Embedding Model: Local OSS, No API Key Required
Decision: Use a local embedding model via `sentence-transformers` or `fastembed` (lighter, ONNX-based).

Top candidates:
- `all-MiniLM-L6-v2`: 80MB, ~5ms/embed on CPU, MTEB 56.3, Apache 2.0
- `BGE-small-en-v1.5`: 130MB, ~8ms/embed, MTEB 62.2, MIT
- `nomic-embed-text-v1.5`: 500MB, ~15ms/embed, MTEB 62.5, Apache 2.0

For our use case (ranking ~20-50 paragraphs from 5 pages against one query), even the smallest model works.
Quality gap between local models and OpenAI API models is <3 MTEB points.

**Open decision: `sentence-transformers` (standard, ~2GB installed with PyTorch) vs `fastembed` (lighter, ~200MB, ONNX Runtime).** User leaned toward keeping it lightweight.

### 4. Architecture: Single Tier (Embeddings Only)
Rejected multi-tier approach. Focus on one approach done well:
- Embeddings-based chunk selection
- No LLM summarization tier (for now)
- No fallback to naive truncation needed if embeddings work at 500 chars

### 5. BM25: Kept for Result-Level Ranking, Not Chunk Selection
BM25 is too crude for selecting paragraphs within a page (bag-of-words misses semantic similarity).
But it's still useful for ranking the final results (which page is most relevant overall).
May revisit — could replace with embedding-based scoring at the result level too.

## What Needs To Be Done Next

### Immediate (to reach Tavily-like quality)
1. **Implement chunk selection** — split extracted content into paragraphs, embed, select top chunks by cosine similarity to query. Target ~500 chars per result.
2. **Add embedding model** — choose between sentence-transformers and fastembed, add to dependencies.
3. **Implement `[snippet]` tagging** — include failed-extraction results with their SearXNG snippet, tagged.
4. **Update content budget** — replace the 20,000 char `MAX_CONTENT_LENGTH` with the embedding-based selection.

### Polish
5. **Caching** — cache extracted content by URL with TTL to avoid re-fetching
6. **SearXNG secret key** — currently hardcoded, should generate on first run or use env var
7. **README** — setup instructions, Claude Code MCP config snippet
8. **Testing** — automated tests for the pipeline

### Docker Lifecycle Management
- Change `restart: unless-stopped` → `restart: no` in docker-compose.yml
- Add auto-start logic in MCP server lifespan: check if SearXNG is running, `docker compose up -d` if not
- First search takes ~2-3s extra if containers are cold; subsequent searches are instant
- Fix Docker volume mount permissions: SearXNG runs as UID 977, which creates files the host user can't delete. Either set `user:` in compose or use a named volume for the config.

### Future Considerations
- Playwright fallback for JS-rendered pages (Reddit, Medium)
- LLM summarization tier (optional, user brings API key)
- Multi-backend search (Brave API as optional premium backend)
- Answer synthesis (Tavily's `include_answer` equivalent)

## Token Budget Analysis

| Config | Tokens per query | vs Tavily |
|--------|-----------------|-----------|
| Current (20K cap, 5 results) | ~11,266 | 16x more |
| Target (500ch/result, 5 results) | ~625 | 0.9x (matched) |
| Tavily basic | ~706 | baseline |
| Claude Code WebSearch | ~918 | titles only |

## Technical Notes

### SearXNG Setup
- Must enable JSON format in `settings.yml`: `search.formats: [json]` (disabled by default, returns 403 without it)
- Port 8888 (not 8080, to avoid conflicts)
- Redis for caching
- `limiter: false` for self-hosted use

### MCP Server
- Uses `FastMCP` with `lifespan` pattern for shared httpx client
- Tools return `str` (formatted text), not JSON — this is what the LLM consumes
- `asyncio.to_thread()` wraps trafilatura (CPU-bound) to avoid blocking event loop
- Overfetches 2x from SearXNG to compensate for extraction failures

### Known Issues
- SearXNG secret key is hardcoded in settings.yml (should be env var or auto-generated)
- No caching layer yet (same URL fetched multiple times across searches)
- The `__pycache__` and `.venv` directories from the durin location are NOT copied (clean start)
