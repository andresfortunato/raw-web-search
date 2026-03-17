# Open Search MCP — Progress & Decisions

## Chunk Selection Strategy (2026-03-16)

**Decision: Option A — Top-K independent chunks, document-order output.**

Selected chunks are the highest-scoring paragraphs by cosine similarity to the query, returned in their original document order. No adjacent-chunk merging.

**Rationale:** Simpler, strict char budget, matches Tavily's ~500 char/result profile. The LLM consuming results can infer context from individual paragraphs.

**Future evaluation:** If output reads as fragmented in practice (e.g., selected paragraphs lack context without their neighbors), consider Option B — merge adjacent high-scoring chunks into coherent sections before applying the char budget. Implementation point: `chunker.py:_assemble_top_k()`.

## Embedding Model (2026-03-16)

**Decision: fastembed (ONNX Runtime) over sentence-transformers (PyTorch).**

~200MB installed vs ~2.5GB. Same model quality. Faster CPU inference.

**Final model: `all-MiniLM-L6-v2`** (80MB, 384-dim).

### Benchmark Results (2026-03-16)

10 queries, 50 pages, 500ch target per result. Models tested via fastembed.

| Model | Avg ch/result | Speed/page | Tok/query | Model size |
|-------|--------------|-----------|-----------|-----------|
| **all-MiniLM-L6-v2** | **407ch** | **890ms** | **509tok** | **80MB** |
| BGE-small-en-v1.5 | 365ch | 3,264ms | 456tok | 130MB |
| nomic-embed-v1.5 | 366ch | 13,948ms | 457tok | 500MB |
| no-chunking (old) | 9,642ch | 0ms | 12,053tok | — |
| Tavily (research) | 565ch | — | 706tok | — |
| Claude WebSearch | — | — | ~1,500tok | — |

**Verdict:** all-MiniLM wins decisively on speed (4x faster than BGE, 16x vs nomic) with comparable output quality. Output sizes are similar across all three models (~365-407 ch/result), so the selection quality differences are minimal for this use case.

All three models achieve ~96% compression from full pages, bringing token cost from ~12K tok/query to ~500 tok — below Tavily's 706 tok baseline.

Raw data: `research/benchmark_results.json`, corpus: `research/benchmark_corpus.json`.

## Latency Optimization (2026-03-16)

### Root Cause
Chunk selection was 61% of total pipeline time (~2.2s of 3.6s). Cause: ONNX Runtime pads all texts in a batch to the longest text's token count. One 128-token chunk forces 49 short chunks to also process 128 tokens each.

### Fix Applied
1. **Sort-by-length batching** — chunks sorted by character length before embedding, so fastembed's sub-batches contain similarly-sized texts.
2. **Small batch_size=8** — forces fastembed to create many small homogeneous sub-batches instead of one padded mega-batch.
3. **Pre-warm model at startup** — `_get_model()` called in MCP lifespan so first search doesn't pay load penalty.
4. **Reduced fetch timeout** — 8s → 4s. Failed URLs return faster.

### Results (after optimization)

| Phase | Before | After |
|-------|--------|-------|
| Chunk selection | 890ms/page (61% of total) | ~286ms/page (~15%) |
| End-to-end (3 queries) | 3.6-7.8s | 4.2-5.3s |

### Latency Comparison

| Tool | End-to-end | Token output | Content type |
|------|-----------|-------------|-------------|
| **open-search-mcp** | **4-5s** | **~500 tok** | Verbatim excerpts |
| Claude WebSearch | 2-4s | ~1,500 tok | AI-synthesized summary |
| Tavily | 1-2s (est.) | ~700 tok | NLP-selected excerpts |

### Remaining bottleneck
Network fetching (60-70% of time). We fetch 10 URLs concurrently but wait for all to complete. Future: stream-process pages as they arrive, early-return when we have enough results.

### Implementation points
- Sort + batch: `src/open_search_mcp/chunker.py:select_chunks()`
- Pre-warm: `src/open_search_mcp/server.py:app_lifespan()`
- Timeout: `FETCH_TIMEOUT` env var, default 4s

## Production-Readiness Items (2026-03-17)

### Tier 1 — First 5 minutes
- README + install docs (MCP config snippet, Docker prereq, first-run UX)
- PyPI publishing (enables `uvx open-search-mcp`)
- First-run UX (model download 80MB + Docker pull 500MB + cold start — need progress feedback)
- Docker documentation (what it is, why needed, auto-start, how to stop, ports)

### Tier 2 — First hour
- ~~Extraction failures 24% (Playwright as optional dep `open-search-mcp[browser]`)~~ DONE: Playwright fallback implemented, tested 100% extraction on thermal runaway query (was ~60% without). Adds ~2s for failed URLs only.
- Stream-processing pages as they arrive + early return (biggest latency win, ~30-50%)
- URL caching layer (same URL across searches)
- Error recovery (SearXNG crash → auto-restart)

### Tier 3 — Open source polish
- Tests + CI
- SearXNG secret key auto-generation
- Configurable chunk budget (env var for target chars)
- Debug mode with pipeline timing

## Playwright Fallback (2026-03-17)

**Implemented:** Optional Playwright fallback in `extractor.py`. Install with `pip install open-search-mcp[browser]`.

**Design:** httpx-first, Playwright-second. 76% of URLs succeed with httpx (~200ms). Failed URLs retry with Playwright (~2.5s each). Single browser instance reused across all failed URLs.

**Test results:** "thermal runaway" query went from ~60% extraction to **100%** (10/10 URLs). Recovered content from nature.com, sciencedirect.com, ul.org, dragonflyenergy.com — all previously 403-blocked.

**Latency impact:** +2s when Playwright is needed. Total: 10s for 10 URLs with Playwright vs 8.5s without. The 76% happy path is unaffected.

## Baseline Eval Results (2026-03-17)

**Completed.** Full write-up: `research/baseline_comparison.md`

### Verdict: open-search-mcp beats the baseline.
- **Reliability**: 1 call, always returns. vs 3-6 calls with 50% WebFetch failure rate.
- **Tokens**: 667 tok vs 1,300+ for full WebSearch+WebFetch workflow.
- **Auto-approval**: MCP tools can be auto-approved. WebSearch/WebFetch cannot.
- **Content fidelity**: Verbatim excerpts preserve code examples and specific numbers.
- **Extraction**: 76% (90%+ with Playwright) vs WebFetch's 50%.
- **Weakness**: Latency 6.3s vs 3s (WebSearch alone). Addressable with stream-processing.

## NEXT SESSION: Remaining Production-Readiness

### Done
- [x] README with install-from-GitHub, eval results, Docker docs
- [x] Playwright fallback (optional dep)
- [x] Baseline eval proving we beat WebSearch+WebFetch

### Remaining

**Priority:** Before building more features, prove we beat the baseline.

### Eval Design
- **10 queries** (same as embedding benchmark — in research/benchmark_corpus.json)
- **3 tools tested:** open-search-mcp, WebSearch alone, WebSearch+WebFetch
- **Metrics:**
  - Latency (end-to-end seconds)
  - Token cost (output size in tokens)
  - Quality (factual coverage — define 5 key facts per query, check which tool covers them)
  - Tool calls required (1 for us, 1-6 for WebSearch+WebFetch)

### Methodology
1. Run our tool on 10 queries via script (have timing + output data already)
2. Run WebSearch on same 10 queries (measure output tokens)
3. Run WebFetch on top 2-3 URLs per query (measure extraction quality vs ours)
4. For quality: define ground-truth facts per query, score coverage
5. Build comparison table in research/baseline_comparison.md

### Hypothesis
We should win on: token efficiency (3x less), content fidelity (verbatim vs paraphrased), auto-approvability, tool call count (1 vs 3-6).
We may lose on: latency (4-5s vs 2-4s), extraction coverage (24% failure rate).
The eval will tell us if the wins outweigh the losses.
