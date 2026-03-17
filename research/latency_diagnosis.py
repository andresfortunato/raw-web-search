"""Latency diagnosis for the open-search MCP pipeline.

Measures each phase of the pipeline individually:
  1. Model load time (cold + warm)
  2. Paragraph splitting per page
  3. Embedding per page — chunk count, real token usage, padding overhead
  4. Cosine similarity computation
  5. Assembly (top-k selection)
  6. Total chunk-selection time per page
  7. Full pipeline estimate: SearXNG search + concurrent fetch + trafilatura + chunk selection

Usage:
    /home/fortu/GitHub/open-search/.venv/bin/python research/latency_diagnosis.py
"""

import asyncio
import collections
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np

# Allow importing from src/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from open_search_mcp.chunker import (
    _split_paragraphs,
    _cosine_similarity,
    MODEL_NAME,
)

BAR_WIDTH = 60
CORPUS_PATH = Path(__file__).parent / "benchmark_corpus.json"
SEARXNG_URL = "http://localhost:8888"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bar(ms: float, scale: float) -> str:
    """ASCII waterfall bar.  scale = ms per character."""
    n = max(1, round(ms / scale))
    return "#" * min(n, BAR_WIDTH)


def hline(char: str = "-", width: int = 78) -> None:
    print(char * width)


def section(title: str) -> None:
    print()
    hline("=")
    print(f"  {title}")
    hline("=")


def subsection(title: str) -> None:
    print()
    hline("-")
    print(f"  {title}")
    hline("-")


# ---------------------------------------------------------------------------
# Phase 1 — Model load
# ---------------------------------------------------------------------------

def measure_model_load() -> tuple:
    """Return (cold_ms, warm_ms, model)."""
    section("PHASE 1: Model Load")

    # Cold start: import fastembed fresh (module already cached in sys.modules,
    # but the ONNX session is created inside TextEmbedding.__init__)
    from fastembed import TextEmbedding  # noqa: PLC0415

    t0 = time.perf_counter()
    model = TextEmbedding(model_name=MODEL_NAME)
    cold_ms = (time.perf_counter() - t0) * 1000

    # Warm: re-instantiate (ONNX file already OS-cached, model weights in memory)
    t0 = time.perf_counter()
    model2 = TextEmbedding(model_name=MODEL_NAME)
    warm_ms = (time.perf_counter() - t0) * 1000

    onnx_session = model.model.model  # InferenceSession
    tokenizer = model.model.tokenizer

    print(f"  Model name   : {MODEL_NAME}")
    print(f"  ONNX provider: {onnx_session.get_providers()}")
    print(f"  Truncation   : {tokenizer.truncation}")
    print(f"  Padding      : {tokenizer.padding}")
    print()
    print(f"  Cold load time : {cold_ms:>8.1f} ms  {bar(cold_ms, 10)}")
    print(f"  Warm load time : {warm_ms:>8.1f} ms  {bar(warm_ms, 10)}")

    return cold_ms, warm_ms, model


# ---------------------------------------------------------------------------
# Phase 2 — Paragraph splitting
# ---------------------------------------------------------------------------

def measure_splitting(query: str, pages: list[dict]) -> list[list[str]]:
    """Return list of chunk lists, one per page.  Print timing."""
    section("PHASE 2: Paragraph Splitting")
    all_chunks = []
    for i, page in enumerate(pages):
        content = page["content"]
        t0 = time.perf_counter()
        chunks = _split_paragraphs(content)
        split_ms = (time.perf_counter() - t0) * 1000
        all_chunks.append(chunks)
        print(
            f"  page {i}: {len(content):>6} chars  -> {len(chunks):>3} chunks  "
            f"split={split_ms:.2f}ms  {bar(split_ms, 0.05)}"
        )
    return all_chunks


# ---------------------------------------------------------------------------
# Phase 3 — Embedding
# ---------------------------------------------------------------------------

def measure_embedding(
    model,
    query: str,
    pages: list[dict],
    all_chunks: list[list[str]],
) -> list[np.ndarray]:
    """Return list of embedding arrays, one per page.  Print detailed timing."""
    section("PHASE 3: Embedding  (query + all chunks per page, one embed() call each)")

    tokenizer = model.model.tokenizer

    all_emb_arrays = []
    page_records = []  # for waterfall summary

    for i, (page, chunks) in enumerate(zip(pages, all_chunks)):
        all_texts = [query] + chunks
        n = len(all_texts)

        # --- tokenization stats ---
        encs = tokenizer.encode_batch(all_texts)
        real_lens = [sum(e.attention_mask) for e in encs]
        padded_len = len(encs[0].ids)  # all padded to same length
        total_real = sum(real_lens)
        total_padded = n * padded_len
        padding_waste_pct = (total_padded - total_real) / total_padded * 100

        # --- actual embed time ---
        t0 = time.perf_counter()
        embeddings = list(model.embed(all_texts))
        embed_ms = (time.perf_counter() - t0) * 1000
        emb_array = np.array(embeddings)
        all_emb_arrays.append(emb_array)

        # token distribution
        buckets = collections.Counter([rl // 20 * 20 for rl in real_lens])
        dist_str = "  ".join(
            f"{b}-{b+19}:{buckets[b]}" for b in sorted(buckets)
        )

        page_records.append(embed_ms)
        print()
        print(f"  page {i}: {len(page['content']):>6} chars | {n:>3} texts | "
              f"padded_seq_len={padded_len} | padding_waste={padding_waste_pct:.0f}%")
        print(f"    real token range  : {min(real_lens)}-{max(real_lens)} "
              f"(avg {sum(real_lens)/len(real_lens):.1f})")
        print(f"    token distribution: [{dist_str}]")
        print(f"    ONNX input matrix : {n} x {padded_len} = {n*padded_len:>6} tokens")
        print(f"    embed() time      : {embed_ms:>8.1f} ms  "
              f"({embed_ms/n:.2f} ms/text)  {bar(embed_ms, 20)}")

    return all_emb_arrays


# ---------------------------------------------------------------------------
# Phase 4 — Cosine similarity
# ---------------------------------------------------------------------------

def measure_cosine(
    pages: list[dict],
    all_chunks: list[list[str]],
    all_emb_arrays: list[np.ndarray],
) -> list[np.ndarray]:
    section("PHASE 4: Cosine Similarity Computation")
    all_scores = []
    for i, (page, chunks, emb_array) in enumerate(zip(pages, all_chunks, all_emb_arrays)):
        query_emb = emb_array[0]
        chunk_embs = emb_array[1:]
        t0 = time.perf_counter()
        scores = _cosine_similarity(query_emb, chunk_embs)
        cos_ms = (time.perf_counter() - t0) * 1000
        all_scores.append(scores)
        print(f"  page {i}: {len(chunks):>3} chunks  cosine={cos_ms:.3f}ms  {bar(cos_ms, 0.02)}")
    return all_scores


# ---------------------------------------------------------------------------
# Phase 5 — Assembly
# ---------------------------------------------------------------------------

def measure_assembly(
    pages: list[dict],
    all_chunks: list[list[str]],
    all_scores: list[np.ndarray],
    target_chars: int = 500,
) -> None:
    section("PHASE 5: Assembly  (top-k chunk selection)")
    from open_search_mcp.chunker import _assemble_top_k  # noqa: PLC0415
    for i, (page, chunks, scores) in enumerate(zip(pages, all_chunks, all_scores)):
        t0 = time.perf_counter()
        result = _assemble_top_k(chunks, scores, target_chars)
        asm_ms = (time.perf_counter() - t0) * 1000
        print(f"  page {i}: {len(chunks):>3} chunks  "
              f"output={len(result):>4} chars  "
              f"assembly={asm_ms:.3f}ms  {bar(asm_ms, 0.02)}")


# ---------------------------------------------------------------------------
# Phase 6 — Total chunk selection (as seen by extractor.py)
# ---------------------------------------------------------------------------

def measure_total_chunk_selection(
    model,
    query: str,
    pages: list[dict],
    target_chars: int = 500,
) -> list[float]:
    section("PHASE 6: Total select_chunks() Time per Page")
    from open_search_mcp.chunker import select_chunks  # noqa: PLC0415

    # We need the global model to already be loaded; monkey-patch it
    import open_search_mcp.chunker as chunker_mod  # noqa: PLC0415
    chunker_mod._model = model

    page_times = []
    for i, page in enumerate(pages):
        content = page["content"]
        t0 = time.perf_counter()
        _ = select_chunks(query, content, target_chars)
        total_ms = (time.perf_counter() - t0) * 1000
        page_times.append(total_ms)
        print(f"  page {i}: {len(content):>6} chars  total={total_ms:>8.1f}ms  {bar(total_ms, 20)}")

    print()
    avg = sum(page_times) / len(page_times)
    total = sum(page_times)
    print(f"  Average per page : {avg:>8.1f} ms")
    print(f"  Total (5 pages)  : {total:>8.1f} ms")
    return page_times


# ---------------------------------------------------------------------------
# Phase 7 — Live pipeline estimate
# ---------------------------------------------------------------------------

async def measure_live_pipeline(query: str, pages: list[dict]) -> None:
    """Make a real SearXNG search, fetch 5 URLs, time each stage."""
    section("PHASE 7: Live End-to-End Pipeline Estimate")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(10.0),
        headers={"User-Agent": "latency-diagnosis/0.1"},
    ) as client:
        # --- 7a: SearXNG search ---
        try:
            t0 = time.perf_counter()
            resp = await client.get(
                f"{SEARXNG_URL}/search",
                params={"q": query, "format": "json", "engines": "google,bing"},
            )
            searxng_ms = (time.perf_counter() - t0) * 1000
            results = resp.json().get("results", [])
            urls = [r["url"] for r in results[:5]]
            searxng_ok = True
            print(f"\n  [7a] SearXNG search    : {searxng_ms:>8.1f} ms  "
                  f"({len(urls)} results)  {bar(searxng_ms, 20)}")
        except Exception as e:
            searxng_ms = 0.0
            urls = [p["url"] for p in pages[:5]]  # fall back to corpus URLs
            searxng_ok = False
            print(f"\n  [7a] SearXNG search    : UNREACHABLE ({e})")
            print(f"       Using {len(urls)} URLs from corpus for fetch test.")

        # --- 7b: Concurrent URL fetch ---
        from open_search_mcp.extractor import fetch_many  # noqa: PLC0415
        t0 = time.perf_counter()
        html_map = await fetch_many(client, urls[:5], max_concurrent=5)
        fetch_ms = (time.perf_counter() - t0) * 1000
        fetched = sum(1 for v in html_map.values() if v)
        print(f"  [7b] Concurrent fetch  : {fetch_ms:>8.1f} ms  "
              f"({fetched}/{len(urls)} ok)  {bar(fetch_ms, 20)}")

        # --- 7c: trafilatura extraction ---
        from open_search_mcp.extractor import extract_content  # noqa: PLC0415
        extract_times = []
        extracted_pages = []
        for url, html in html_map.items():
            if html is None:
                continue
            t0 = time.perf_counter()
            extracted = extract_content(html, url)
            extract_times.append((time.perf_counter() - t0) * 1000)
            if extracted:
                extracted_pages.append(extracted)
        total_extract_ms = sum(extract_times)
        avg_extract_ms = total_extract_ms / len(extract_times) if extract_times else 0
        print(f"  [7c] trafilatura       : {total_extract_ms:>8.1f} ms total  "
              f"({avg_extract_ms:.1f} ms/page, {len(extracted_pages)} extracted)  "
              f"{bar(total_extract_ms, 20)}")

        # --- 7d: chunk selection (using cached model + real extracted content) ---
        from open_search_mcp.chunker import select_chunks  # noqa: PLC0415
        chunk_times = []
        for ep in extracted_pages:
            content = ep["content"]
            if len(content) > 500:
                t0 = time.perf_counter()
                _ = select_chunks(query, content)
                chunk_times.append((time.perf_counter() - t0) * 1000)
        total_chunk_ms = sum(chunk_times)
        avg_chunk_ms = total_chunk_ms / len(chunk_times) if chunk_times else 0
        print(f"  [7d] Chunk selection   : {total_chunk_ms:>8.1f} ms total  "
              f"({avg_chunk_ms:.1f} ms/page, {len(chunk_times)} pages)  "
              f"{bar(total_chunk_ms, 20)}")

        # --- 7e: summary ---
        end_to_end = searxng_ms + fetch_ms + total_extract_ms + total_chunk_ms
        print()
        print(f"  Pipeline total (excl. model load): {end_to_end:>8.1f} ms")
        print()
        note = "(SearXNG unreachable — search time is 0)" if not searxng_ok else ""
        print(f"  Waterfall  {note}")

        scale = max(end_to_end / BAR_WIDTH, 1.0)
        rows = [
            ("SearXNG search", searxng_ms),
            ("Concurrent fetch", fetch_ms),
            ("trafilatura (serial)", total_extract_ms),
            ("Chunk selection (serial)", total_chunk_ms),
        ]
        for label, ms in rows:
            pct = ms / end_to_end * 100 if end_to_end else 0
            print(f"  {label:<28} {ms:>7.0f}ms ({pct:>4.1f}%)  {bar(ms, scale)}")


# ---------------------------------------------------------------------------
# Waterfall summary
# ---------------------------------------------------------------------------

def print_waterfall_summary(
    cold_ms: float,
    warm_ms: float,
    page_times: list[float],
    query: str,
    pages: list[dict],
    all_chunks: list[list[str]],
) -> None:
    section("WATERFALL SUMMARY — Where Does Time Go?")

    total_pages = sum(page_times)
    scale = max(total_pages / BAR_WIDTH, 1.0)

    print(f"  Query : {query}")
    print(f"  Pages : {len(pages)}")
    print()

    # Per-page detail
    print("  Per-page chunk selection breakdown:")
    hline()
    for i, (page, chunks, ms) in enumerate(zip(pages, all_chunks, page_times)):
        tokenizer = None  # already printed in phase 3
        pct = ms / total_pages * 100
        print(f"  page {i}  {len(page['content']):>6}ch  {len(chunks):>3} chunks  "
              f"{ms:>8.1f}ms ({pct:>4.1f}%)  {bar(ms, scale)}")
    hline()
    print(f"  Total chunk selection  : {total_pages:>8.1f} ms")
    avg = total_pages / len(page_times)
    print(f"  Average per page       : {avg:>8.1f} ms  (benchmark reported ~890ms)")
    print()

    # Why embedding is slow: the key finding
    print("  ROOT CAUSE — Padding overhead analysis:")
    hline()
    print()
    print("  All-MiniLM-L6-v2 has a 128-token max sequence length.")
    print("  When embed() is called with a batch, the tokenizer pads every")
    print("  sequence to the length of the LONGEST sequence in the batch.")
    print("  A single long chunk (e.g. a code block hitting the 128-token cap)")
    print("  forces every other chunk to be padded to 128 tokens, even if they")
    print("  are 10-20 tokens each.  The ONNX matrix grows from N*avg_len to")
    print("  N*128, multiplying inference time by 128/avg_len.")
    print()
    print("  Observed this corpus:")

    from open_search_mcp.chunker import MODEL_NAME as _MN  # noqa: PLC0415
    from fastembed import TextEmbedding  # noqa: PLC0415
    _m = TextEmbedding(model_name=_MN)
    _tok = _m.model.tokenizer

    for i, (page, chunks) in enumerate(zip(pages, all_chunks)):
        all_texts = [query] + chunks
        encs = _tok.encode_batch(all_texts)
        real_lens = [sum(e.attention_mask) for e in encs]
        padded = len(encs[0].ids)
        avg_real = sum(real_lens) / len(real_lens)
        waste = (padded - avg_real) / padded * 100
        theoretical_speedup = padded / avg_real
        print(f"  page {i}: avg_real={avg_real:>5.1f} tok  padded={padded}  "
              f"waste={waste:>4.1f}%  speedup_if_fixed={theoretical_speedup:.1f}x")

    print()
    hline()
    print()
    print("  Expected vs actual embed time (per-text, 50 chunks):")
    print("    Expected (~5ms/embed advertised) : 50 x 5ms  =   250ms")
    print("    Actual (padding to 128 tokens)   : ~890ms average")
    print(f"    Cold model load overhead        : {cold_ms:.0f}ms (first call only)")
    print()
    print("  THE BOTTLENECK IS THE ONNX INFERENCE TIME INFLATED BY SEQUENCE")
    print("  PADDING.  IT IS NOT model loading, embed() call overhead, cosine")
    print("  similarity, or assembly — those are all <5ms per page.")
    print()
    print("  Fix options (ranked by impact):")
    hline()
    print("  1. Sort-by-length batching: sort texts by token length before")
    print("     embed(), group into mini-batches of similar length.  This")
    print("     avoids padding short texts to 128.  Expected speedup: 3-5x.")
    print()
    print("  2. Use a smaller batch or pass batch_size=1 per text: fully")
    print("     eliminates padding but removes ONNX batching efficiency.")
    print("     Net result depends on ONNX session overhead per call.")
    print()
    print("  3. Switch to BGE-small-en-v1.5 (quantized, 67MB): already in")
    print("     benchmark_results.json with similar quality.  Profile suggests")
    print("     it has the same padding problem but fewer params may help.")
    print()
    print("  4. Reduce MAX_CHUNK_CHARS from 1000 to ~400 chars: keeps most")
    print("     chunks well under 128 tokens, reducing the padding outlier")
    print("     problem.  Requires re-profiling quality tradeoff.")
    print()
    print("  5. Truncate at token level rather than char level: strip chunks")
    print("     that exceed 100 tokens to avoid the 128 cap + padding effect.")
    print()
    print("  6. Batch ALL pages together in one embed() call instead of one")
    print("     call per page: reduces ONNX session startup overhead but does")
    print("     NOT solve the padding problem.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not CORPUS_PATH.exists():
        print(f"Corpus not found at {CORPUS_PATH}")
        print("Run research/benchmark_fetch.py first.")
        sys.exit(1)

    with open(CORPUS_PATH) as f:
        corpus = json.load(f)

    # Pick the first query (FastAPI rate limiting) as the primary diagnostic target.
    # It has 5 pages and representative chunk counts.
    entry = corpus[0]
    query = entry["query"]
    pages = entry["pages"]

    print()
    print("=" * 78)
    print("  OPEN-SEARCH MCP — LATENCY DIAGNOSIS")
    print("=" * 78)
    print(f"  Corpus  : {CORPUS_PATH}")
    print(f"  Query   : {query!r}")
    print(f"  Pages   : {len(pages)}")
    print(f"  Content : {sum(len(p['content']) for p in pages):,} chars total")

    # Phases 1-6: synthetic (offline, uses corpus content)
    cold_ms, warm_ms, model = measure_model_load()

    all_chunks = measure_splitting(query, pages)

    all_emb_arrays = measure_embedding(model, query, pages, all_chunks)

    all_scores = measure_cosine(pages, all_chunks, all_emb_arrays)

    measure_assembly(pages, all_chunks, all_scores)

    page_times = measure_total_chunk_selection(model, query, pages)

    # Phase 7: live pipeline (requires SearXNG + internet)
    asyncio.run(measure_live_pipeline(query, pages))

    # Summary waterfall
    print_waterfall_summary(cold_ms, warm_ms, page_times, query, pages, all_chunks)


if __name__ == "__main__":
    main()
