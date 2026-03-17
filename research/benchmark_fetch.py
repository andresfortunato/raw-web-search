"""Phase 1: Fetch and cache content for benchmark queries.

Saves extracted content to benchmark_corpus.json so the embedding
benchmark can run without network I/O.

Usage: python research/benchmark_fetch.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from open_search_mcp.extractor import fetch_many, extract_content
from open_search_mcp.searcher import search_searxng

SEARXNG_URL = "http://localhost:8888"
MAX_RESULTS = 5

QUERIES = [
    "how to implement rate limiting in FastAPI",
    "rust vs go performance benchmarks 2025",
    "kubernetes pod security best practices",
    "what causes lithium battery thermal runaway",
    "GDPR data processing agreement requirements",
    "how does mRNA vaccine technology work",
    "best practices for PostgreSQL index optimization",
    "climate change impact on coral reef ecosystems",
    "how to set up a SearXNG instance",
    "transformer architecture attention mechanism explained",
]


async def main():
    corpus = []

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(6.0),  # Shorter timeout to fail fast
        headers={"User-Agent": "search-mcp-benchmark/0.1"},
    ) as client:
        for qi, query in enumerate(QUERIES, 1):
            print(f"[{qi}/{len(QUERIES)}] {query}")
            t0 = time.perf_counter()

            try:
                results = await search_searxng(client, query, SEARXNG_URL, max_results=MAX_RESULTS * 2)
            except RuntimeError as e:
                print(f"  SKIP: {e}")
                continue

            urls = [r["url"] for r in results]
            html_map = await fetch_many(client, urls, max_concurrent=8)

            pages = []
            for r in results:
                html = html_map.get(r["url"])
                if html:
                    extracted = extract_content(html, r["url"])
                    if extracted and len(extracted["content"]) > 100:
                        pages.append({
                            "url": r["url"],
                            "title": extracted["title"],
                            "content": extracted["content"],
                        })
                if len(pages) >= MAX_RESULTS:
                    break

            elapsed = time.perf_counter() - t0
            print(f"  {len(pages)} pages extracted in {elapsed:.1f}s")

            corpus.append({
                "query": query,
                "pages": pages,
            })

    out_path = Path(__file__).parent / "benchmark_corpus.json"
    with open(out_path, "w") as f:
        json.dump(corpus, f, indent=2)

    total_pages = sum(len(q["pages"]) for q in corpus)
    print(f"\nSaved {total_pages} pages across {len(corpus)} queries to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
