# Open Source Search MCP: Feasibility Analysis

## The Problem

Claude Code's built-in web tools are suboptimal for AI-assisted development:

| Issue | WebSearch | WebFetch |
|-------|-----------|----------|
| **Returns** | Titles + URLs only (no content) | Haiku-summarized content (lossy) |
| **Token cost** | Low per call, but forces separate fetch | Hidden Haiku call + 100KB truncation |
| **Reliability** | Can't be auto-approved; blocked in background agents | 403s on Wikipedia; hangs indefinitely (no timeout); domain preflight blocked by VPNs/firewalls |
| **JS rendering** | N/A | None — static HTML only |
| **Round-trip** | Search → get URLs → fetch each → summarize = slow multi-step | Single page only |

**The two-step pattern** (WebSearch → WebFetch for each result) is slower, more token-expensive, and more failure-prone than a single MCP call that returns pre-extracted content.

---

## What Tavily Does (The Gold Standard)

Tavily is purpose-built for LLM consumption. Single API call pipeline:

```
Query → Search (own index) → Fetch top 20 sites → AI scoring/filtering → Clean extraction → Return
```

### Key value-adds over raw search:
1. **Pre-extracted content** — clean markdown/text per result, not just URLs
2. **Relevance scoring** — 0.0-1.0 AI-scored relevance per result
3. **Semantic chunking** — multiple relevant chunks per page (advanced mode)
4. **Answer synthesis** — optional LLM-generated answer from results
5. **Domain filtering** — include/exclude domains
6. **180ms p50 latency** — very fast

### API surface: 5 endpoints
- `/search` — core search (1-2 credits)
- `/extract` — content from known URLs (1 credit/5 URLs)
- `/crawl` — graph-based site traversal
- `/map` — sitemap generation
- `/research` — autonomous multi-step research (4-250 credits)

### Pricing: $0.008/credit, 1,000 free/month

---

## Existing MCP Landscape

### Commercial Search MCPs

| Server | Tools | Free Tier | Quality | Unique Feature |
|--------|-------|-----------|---------|----------------|
| **Tavily MCP** | 4 (search, extract, map, crawl) | 1,000/mo | Highest | AI relevance scoring + answer synthesis |
| **Brave MCP** | 6 (web, local, video, image, news, summarizer) | ~1,000/mo ($5 credit) | High | Most tool variety |
| **Exa MCP** | 8+ (web, code, company, deep research) | Limited | High | Neural/semantic search |
| **Perplexity MCP** | 4 (search, ask, research, reason) | Paid only | Highest | Own LLM models for synthesis |

### Free/Open Source Search MCPs

| Server | Stars | API Key? | Search Source | Content Extract? |
|--------|-------|----------|---------------|------------------|
| **DuckDuckGo MCP** | 890 | No | DuckDuckGo | Yes (basic) |
| **web-search-mcp** (mrkrsl) | 639 | No | Bing/Brave/DDG fallback | Yes + relevance check |
| **SearXNG MCPs** (multiple) | 100-532 | No (self-host) | 70+ aggregated engines | Some have it |
| **Google AI Mode MCP** | 86 | No | Google AI Mode | Pre-synthesized |
| **one-search-mcp** | 89 | Optional | 9 backends | Yes |

### Key Gap in Open Source
No open source MCP combines all of:
- High-quality multi-engine search
- Content extraction + cleaning optimized for LLMs
- Relevance scoring per result
- Token-efficient structured output
- Zero/minimal cost

The closest is SearXNG MCP + Jina Reader, but it's two separate systems without integrated scoring.

---

## Technical Building Blocks Available

### Search Backends

| Option | Cost | Quality | Rate Limits | Status |
|--------|------|---------|-------------|--------|
| **SearXNG** (self-hosted) | Free | High (aggregates 70+) | None (your infra) | Active |
| **Brave Search API** | $5/1K queries | High | 1/sec on free | Active |
| **Serper.dev** | $1/1K (Google results) | Highest | 300/sec | Active |
| **DuckDuckGo** (scraping) | Free | Medium | ~20-30/min | Fragile |
| **Google Custom Search** | N/A | N/A | N/A | **DEAD** (closed to new users) |
| **Bing Search API** | N/A | N/A | N/A | **DEAD** (retired Aug 2025) |

**Winner: SearXNG for free tier; Brave or Serper for paid quality.**

### Content Extraction Libraries

| Library | F1 Score | Language | JS Rendering | Output Formats |
|---------|----------|----------|--------------|----------------|
| **Trafilatura** | 0.958 | Python | No | TXT, MD, JSON, HTML, XML |
| **Newspaper4k** | 0.949 | Python | No | Text + metadata |
| **@mozilla/readability** | 0.947 | JS | No | HTML + text |
| **readability-lxml** | 0.922 | Python | No | HTML |
| **Jina Reader** | N/A | API | Yes (hosted) | Markdown |
| **Crawl4AI** | N/A | Python | Yes (local) | Markdown |

**Winner: Trafilatura (Python, highest accuracy, markdown output built-in).**

### Token Efficiency

- Raw HTML → Clean Markdown: **~67% token reduction**
- Typical web page: 50-200KB HTML → 2-10KB clean text
- Target per result: **2,000-4,000 tokens** after extraction
- 5 results = 10K-20K tokens total (vs. WebFetch doing 25K tokens for ONE large page)

---

## Architecture for an Open Source Alternative

### Pipeline Design

```
User Query
    │
    ▼
┌──────────────────┐
│  1. Search        │  SearXNG (free) or Brave API ($5/1K)
│                   │  → Top N URLs + snippets
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  2. Concurrent    │  aiohttp/httpx with 5-10s timeouts
│     Fetch         │  Fallback: Playwright for JS-heavy pages
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  3. Extract &     │  Trafilatura (primary) → readability fallback
│     Clean         │  Output: Markdown, truncated to relevant sections
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  4. Rank &        │  BM25 or embedding similarity against query
│     Filter        │  Drop low-relevance results
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  5. Return        │  JSON: title, url, content (markdown), score
│     Results       │  Optional: merged summary
└──────────────────┘
```

### MCP Tool Interface

```json
{
  "tools": [
    {
      "name": "search",
      "description": "Search the web and return extracted content optimized for LLM consumption",
      "parameters": {
        "query": "string (required)",
        "max_results": "int (1-10, default 5)",
        "search_depth": "'fast' | 'thorough' (default 'fast')",
        "include_domains": "string[] (optional)",
        "exclude_domains": "string[] (optional)",
        "time_range": "'day' | 'week' | 'month' | 'year' (optional)",
        "include_raw_content": "bool (default false)"
      }
    },
    {
      "name": "extract",
      "description": "Extract clean content from specific URLs",
      "parameters": {
        "urls": "string | string[] (required, max 10)",
        "query": "string (optional, for relevance-based chunking)",
        "format": "'markdown' | 'text' (default 'markdown')"
      }
    }
  ]
}
```

### Minimal Viable Stack

| Component | Tool | Cost |
|-----------|------|------|
| Search | SearXNG (Docker) | Free |
| HTTP Fetch | aiohttp / httpx | Free |
| Content Extract | trafilatura | Free |
| JS Fallback | Playwright (optional) | Free |
| Relevance Scoring | BM25 (rank_bm25 lib) | Free |
| MCP Server | Python MCP SDK | Free |
| **Total** | | **$0** |

---

## Difficulty Assessment

### What's Easy (1-2 days)
- Setting up SearXNG in Docker
- Basic MCP server with search + extract tools
- Trafilatura content extraction
- Returning structured JSON results

### What's Medium (3-5 days)
- Concurrent fetching with proper timeout/retry logic
- Relevance scoring (BM25 or lightweight embeddings)
- Caching layer (URL → extracted content, with TTL)
- Handling edge cases (paywalls, rate limits, timeouts, encoding)
- Playwright fallback for JS-rendered pages

### What's Hard (1-2 weeks)
- Matching Tavily's relevance scoring quality (they use proprietary AI)
- Answer synthesis (requires LLM call, adds cost/latency)
- Handling the long tail of weird web pages gracefully
- Making it production-reliable at scale

### Overall Estimate
**MVP (better than WebSearch+WebFetch): 2-3 days**
- SearXNG + trafilatura + basic BM25 scoring + MCP wrapper
- Would already be a significant improvement over built-in tools

**Polished v1.0 (approaching Tavily quality): 1-2 weeks**
- Multi-backend search, caching, Playwright fallback, robust error handling
- Configurable search depth, domain filtering, content chunking

---

## Comparison: What We Can Build vs. Alternatives

| Feature | Built-in WebSearch+Fetch | Tavily ($8/1K) | Our MCP (Free) | Our MCP + Brave ($5/1K) |
|---------|-------------------------|----------------|-----------------|--------------------------|
| Content in results | No (titles only) | Yes (cleaned) | Yes (cleaned) | Yes (cleaned) |
| Token efficiency | Poor (Haiku overhead) | Good (~2K/result) | Good (~2-4K/result) | Good (~2-4K/result) |
| Relevance scoring | None | AI-scored (0-1) | BM25 scored | BM25 scored |
| JS rendering | None | Yes | Optional (Playwright) | Optional (Playwright) |
| Answer synthesis | None | Yes (LLM) | No (can add) | No (can add) |
| Reliability | Poor (403s, hangs) | High (99.99% SLA) | Medium (self-hosted) | Medium-High |
| Cost | Included (but wasteful) | $0.008/query | $0 | $0.005/query |
| Search quality | Single provider | Proprietary index | 70+ engines (SearXNG) | Brave + SearXNG |
| Setup effort | Zero | 1 line config | Docker + config | Docker + API key |
| Auto-approve in CC | No | Yes (MCP) | Yes (MCP) | Yes (MCP) |

---

## Recommendation

**Build it.** The MVP is straightforward and already better than built-in tools:

1. **Phase 1 (MVP)**: SearXNG + trafilatura + MCP wrapper. Zero cost, 2-3 days.
   - Beats WebSearch+WebFetch on: content extraction, token efficiency, reliability, auto-approval
   - Missing vs Tavily: AI relevance scoring, answer synthesis, speed

2. **Phase 2 (Enhanced)**: Add Brave API as optional premium backend, caching, Playwright fallback.
   - Approaches Tavily quality at 60% lower cost

3. **Phase 3 (Advanced)**: Lightweight relevance model, optional LLM answer synthesis, multi-query parallel search.
   - Matches most of Tavily's feature set

The key insight: **Tavily's real moat is speed (180ms) and their proprietary index/scoring.** Everything else — extraction, cleaning, MCP interface — is readily buildable with open source tools. For a development assistant use case (not real-time consumer product), slightly higher latency is perfectly acceptable.
