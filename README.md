# raw-web-search

An experimental MCP search server for Claude Code. Returns raw, verbatim web content instead of AI-rewritten summaries.

> **This is a research project**, not a production tool. It explores whether raw web extraction can replace Claude Code's built-in WebSearch + WebFetch. The answer: it depends on the use case. See [Eval Results](#eval-results) for honest benchmarks.

## What it does

One MCP tool call that searches the web, fetches pages, extracts content, and returns the most query-relevant excerpts — all verbatim from the source.

```
search("how to implement rate limiting in FastAPI")
→ 5 results with verbatim excerpts from real pages (~1,400 tokens total)
```

Also includes `extract(urls)` for direct URL content extraction (replaces WebFetch).

## When to use this instead of WebSearch

| Use case | raw-web-search | WebSearch | Winner |
|----------|---------------|-----------|--------|
| **Code examples / API docs** | Verbatim code preserved | Paraphrased by Haiku | **raw-web-search** |
| **Batch searching (20+ searches/session)** | Auto-approvable MCP tool | Click-per-call approval | **raw-web-search** |
| **URL extraction (replacing WebFetch)** | ~100% success | ~50% success | **raw-web-search** |
| **General knowledge questions** | 72% factual coverage | 96% factual coverage | **WebSearch** |
| **Speed** | 4.5s | ~3s | **WebSearch** |
| **Token efficiency** | ~1,400 tok | ~700 tok | **WebSearch** |

**Bottom line:** Use raw-web-search when you need verbatim source text (code, docs, exact quotes) or want frictionless auto-approved searching. Use WebSearch when you need synthesized overviews or general knowledge.

## Eval Results

### Quantitative (20 queries)

| Metric | raw-web-search | WebSearch | WebSearch+WebFetch |
|--------|---------------|-----------|-------------------|
| Latency | 4.5s avg (2.7-8.1s) | ~3s | ~6-10s (multi-call) |
| Tokens/query | ~1,400 | ~700 | ~1,400+ |
| Results per query | 5 (zero failures) | 10 links + summary | 1-3 per WebFetch |
| Tool calls | 1 | 1 | 3-6 |
| Content type | Verbatim excerpts | AI-rewritten | AI-summarized |
| Extraction success | 100% | N/A | ~50% |
| Auto-approvable | Yes | No | No |

### Quality (5 queries, 25 ground-truth facts)

| Eval | Metric | raw-web-search | WebSearch |
|------|--------|---------------|-----------|
| **Factual coverage** | Facts found in output | **18/25 (72%)** | **24/25 (96%)** |
| **Technical queries** | Direct comparison | **Competitive** | Good |
| **Science/explainer** | Direct comparison | Behind | **Better** |
| **Downstream accuracy** | LLM answer quality | 0 wins, 2 ties, 1 loss | 1 win, 2 ties |

WebSearch wins on factual coverage because it uses an LLM (Haiku) to synthesize across 10+ full pages. We use embeddings to select the most relevant paragraphs from 5 pages — a fundamentally different (and less thorough) approach.

### What we learned

1. **AI synthesis > embedding selection for factual coverage.** An LLM reading full pages and picking key facts will always beat cosine-similarity paragraph selection.
2. **Verbatim text > AI summaries for code.** Paraphrased code examples and API signatures are useless. Raw extraction preserves them.
3. **Auto-approval is the killer feature.** The biggest real-world advantage isn't content quality — it's eliminating click-per-search friction.
4. **WebFetch is genuinely bad.** 50% failure rate on real-world URLs. Our `extract` tool is a clear improvement.

## How it works

```
Query
  → SearXNG (search 70+ engines via Docker)
  → Fetch HTML (httpx concurrent, 4s timeout)
  → Playwright fallback for failed URLs (JS-rendered pages)
  → Extract content (trafilatura, F1=0.958)
  → Split into paragraphs
  → Embed query + paragraphs (fastembed, all-MiniLM-L6-v2)
  → Select top chunks by cosine similarity (~1500 chars/result)
  → BM25 rank results
  → Return structured text
```

## Prerequisites

- **Python 3.10+**
- **Docker** (for SearXNG search backend)

### How Docker is used

SearXNG runs as a Docker container alongside Redis. The MCP server auto-starts containers on demand.

- **Auto-start:** Checks if SearXNG is reachable, runs `docker compose up -d` if not
- **Port:** `localhost:8888` (configurable via `SEARXNG_URL`)
- **Stopping:** `docker compose down` in the project directory

## Install

```bash
# Install globally (available in all projects)
claude mcp add -s user open-search -- uvx --from git+https://github.com/andresfortunato/open-search.git open-search-mcp

# Set as default search (one-time — tells Claude to prefer this over WebSearch)
uvx --from git+https://github.com/andresfortunato/open-search.git open-search-mcp --setup

# Optional: install Chromium for ~100% extraction success (vs 76% without)
playwright install chromium
```

## Tools

### `search`

Search the web and return extracted content.

```
search(query, max_results=5, include_domains=None, exclude_domains=None, time_range=None)
```

### `extract`

Extract content from specific URLs. Direct replacement for WebFetch.

```
extract(urls, query=None)
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_URL` | `http://localhost:8888` | SearXNG instance URL |
| `FETCH_TIMEOUT` | `4` | HTTP fetch timeout in seconds |
| `OPEN_SEARCH_CHUNK_CHARS` | `1500` | Target chars per result |
| `OPEN_SEARCH_DEBUG` | `false` | Log pipeline timing per query |

## Architecture

```
src/open_search_mcp/
  server.py     # MCP server, tool definitions, Docker lifecycle
  searcher.py   # SearXNG client + BM25 scoring
  extractor.py  # URL fetching + trafilatura + Playwright fallback
  chunker.py    # Embeddings-based chunk selection (fastembed)
  cache.py      # TTL-based URL cache
```

## Research

The `research/` directory contains all eval data, benchmarks, and analysis:
- `eval_a_v2.md` — Factual coverage scoring (72% vs WebSearch's 96%)
- `quality_eval.md` — Direct content comparison (Eval C)
- `baseline_comparison.md` — Full baseline eval write-up
- `eval_20_results.json` — 20-query benchmark data

## License

MIT
