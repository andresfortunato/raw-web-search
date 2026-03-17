"""Phase 2: Benchmark embedding models for chunk selection.

Reads pre-fetched content from benchmark_corpus.json and tests
all-MiniLM, BGE-small, and nomic-embed across all queries.
No network I/O — pure embedding speed + quality comparison.

Usage:
  python research/benchmark_fetch.py     # run once to fetch content
  python research/benchmark_embeddings.py  # run this to benchmark
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from open_search_mcp.chunker import _split_paragraphs, _cosine_similarity

MODELS = {
    "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
    "BGE-small-en-v1.5": "BAAI/bge-small-en-v1.5",
    "nomic-embed-v1.5": "nomic-ai/nomic-embed-text-v1.5",
}

TARGET_CHARS = 500


def run_chunk_selection(model, query: str, content: str, target_chars: int) -> dict:
    """Run chunk selection with a specific model. Returns metrics + output."""
    chunks = _split_paragraphs(content)
    if not chunks:
        return {"output": content[:target_chars], "time_ms": 0, "chars": min(len(content), target_chars)}

    total_chars = sum(len(c) for c in chunks)
    if total_chars <= target_chars:
        return {"output": content, "time_ms": 0, "chars": len(content), "skipped": True}

    all_texts = [query] + chunks
    t0 = time.perf_counter()
    embeddings = list(model.embed(all_texts))
    embed_time = (time.perf_counter() - t0) * 1000

    emb_array = np.array(embeddings)
    query_emb = emb_array[0]
    chunk_embs = emb_array[1:]
    scores = _cosine_similarity(query_emb, chunk_embs)

    ranked = np.argsort(scores)[::-1]
    selected = []
    char_count = 0
    for idx in ranked:
        chunk_len = len(chunks[idx])
        if char_count + chunk_len > target_chars and selected:
            break
        selected.append(int(idx))
        char_count += chunk_len

    selected.sort()
    output = "\n\n".join(chunks[i] for i in selected)

    return {
        "output": output,
        "time_ms": round(embed_time, 1),
        "chars": len(output),
        "n_chunks": len(chunks),
        "n_selected": len(selected),
        "top_score": round(float(scores[ranked[0]]), 4),
    }


def main():
    from fastembed import TextEmbedding

    corpus_path = Path(__file__).parent / "benchmark_corpus.json"
    if not corpus_path.exists():
        print("Run benchmark_fetch.py first to create benchmark_corpus.json")
        sys.exit(1)

    with open(corpus_path) as f:
        corpus = json.load(f)

    total_pages = sum(len(q["pages"]) for q in corpus)
    print(f"Loaded corpus: {len(corpus)} queries, {total_pages} pages\n")

    # Load models
    loaded = {}
    for name, model_id in MODELS.items():
        print(f"Loading {name}...", end=" ", flush=True)
        t0 = time.perf_counter()
        loaded[name] = TextEmbedding(model_name=model_id)
        print(f"{time.perf_counter() - t0:.1f}s")

    print()

    # Run benchmark
    all_results = {}
    for model_name in MODELS:
        all_results[model_name] = {"per_query": [], "total_chars": 0, "total_time_ms": 0, "total_full_chars": 0}

    for qi, entry in enumerate(corpus, 1):
        query = entry["query"]
        pages = entry["pages"]
        if not pages:
            print(f"[{qi}] {query} — no pages, skipping")
            continue

        print(f"[{qi}] {query} ({len(pages)} pages)")

        for model_name, model in loaded.items():
            query_chars = 0
            query_time = 0
            query_full = 0
            outputs = []

            for page in pages:
                m = run_chunk_selection(model, query, page["content"], TARGET_CHARS)
                query_chars += m["chars"]
                query_time += m["time_ms"]
                query_full += len(page["content"])
                outputs.append(m["output"][:200])  # truncated sample

            r = all_results[model_name]
            r["per_query"].append({
                "query": query,
                "total_chars": query_chars,
                "avg_chars": round(query_chars / len(pages)),
                "time_ms": round(query_time, 1),
                "full_chars": query_full,
                "sample": outputs[0] if outputs else "",
            })
            r["total_chars"] += query_chars
            r["total_time_ms"] += query_time
            r["total_full_chars"] += query_full

            print(f"  {model_name:<22} {query_chars:>5}ch  {query_time:>6.1f}ms  "
                  f"({round(query_chars/len(pages))}ch/result)")

    # Summary
    n_queries = len([e for e in corpus if e["pages"]])
    n_pages = total_pages

    print("\n" + "=" * 95)
    print(f"{'Model':<24} {'Avg ch/result':>13} {'Avg ms/page':>12} {'Tot tok/query':>14} {'Compression':>12} {'Model MB':>9}")
    print("-" * 95)

    model_sizes = {"all-MiniLM-L6-v2": 80, "BGE-small-en-v1.5": 130, "nomic-embed-v1.5": 500}

    for model_name in MODELS:
        r = all_results[model_name]
        avg_chars = r["total_chars"] / n_pages
        avg_time = r["total_time_ms"] / n_pages
        avg_tok = r["total_chars"] / n_queries / 4
        compression = r["total_chars"] / r["total_full_chars"] if r["total_full_chars"] else 1
        mb = model_sizes.get(model_name, "?")

        print(f"{model_name:<24} {avg_chars:>11.0f}ch {avg_time:>10.1f}ms {avg_tok:>12.0f}tok {compression:>10.1%} {mb:>7}MB")

    # No-chunking baseline
    total_full = sum(r["total_full_chars"] for r in all_results.values()) // len(MODELS)
    avg_full = total_full / n_pages
    print(f"{'no-chunking':<24} {avg_full:>11.0f}ch {'0':>10}ms {total_full/n_queries/4:>12.0f}tok {'100.0%':>10} {'—':>7}  ")

    # External baselines
    print(f"{'tavily (research)':<24} {'565':>11}ch {'—':>10}   {'706':>12}tok {'—':>10} {'—':>7}  ")
    print(f"{'claude WebSearch':<24} {'—':>11}   {'—':>10}   {'~1500':>12}tok {'—':>10} {'—':>7}  ")
    print("=" * 95)

    # Save detailed results
    out_path = Path(__file__).parent / "benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nDetailed results saved to {out_path}")

    # Print a sample output comparison for one query
    print("\n--- Sample output comparison (query 1) ---")
    for model_name in MODELS:
        sample = all_results[model_name]["per_query"][0]["sample"]
        print(f"\n[{model_name}]")
        print(sample + "...")


if __name__ == "__main__":
    main()
