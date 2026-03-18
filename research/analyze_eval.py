"""Diagnostic analysis of eval_a_our_output.json."""

import json
import re

DATA_PATH = "/home/fortu/GitHub/open-search/research/eval_a_our_output.json"

with open(DATA_PATH) as f:
    data = json.load(f)

print("=" * 70)
print("DIAGNOSTIC ANALYSIS: eval_a_our_output.json")
print("=" * 70)

# ── 1. SNIPPET RATIO ────────────────────────────────────────────────────────
print("\n\n── 1. SNIPPET RATIO ────────────────────────────────────────────────")

result_block_re = re.compile(
    r"## Result (\d+)(.*?)(?=## Result |\Z)", re.DOTALL
)

global_total = 0
global_snippets = 0

for query, output in data.items():
    blocks = result_block_re.findall(output)
    snippets = sum(1 for _, body in blocks if "[snippet]" in body)
    total = len(blocks)
    global_total += total
    global_snippets += snippets
    print(f"\nQuery: {query!r}")
    print(f"  Results: {total}  |  Snippets: {snippets}  |  Full: {total - snippets}")
    for num, body in blocks:
        tag = "[SNIPPET]" if "[snippet]" in body else "[full]  "
        # extract URL line
        url_line = next((l.strip() for l in body.strip().splitlines() if l.strip().startswith("http")), "?")
        print(f"    Result {num} {tag}  {url_line}")

print(f"\nOverall: {global_snippets}/{global_total} snippet ({100*global_snippets/global_total:.0f}%)")


# ── 2. CONTENT LENGTH ANALYSIS ──────────────────────────────────────────────
print("\n\n── 2. CONTENT LENGTH ANALYSIS ─────────────────────────────────────")
print("(lengths are chars of the content body, excluding the ## Result header)")

for query, output in data.items():
    blocks = result_block_re.findall(output)
    print(f"\nQuery: {query!r}")
    for num, body in blocks:
        # body starts with \n**Title**\nURL\n\ncontent
        lines = body.strip().splitlines()
        # find the blank line after the URL to get just the content portion
        content_start = 0
        for i, line in enumerate(lines):
            if line.strip() == "" and i > 1:
                content_start = i + 1
                break
        content_lines = lines[content_start:]
        content = "\n".join(content_lines).strip()
        tag = "snip" if "[snippet]" in body else "full"
        print(f"  Result {num} [{tag}]: {len(content):4d} chars")


# ── 3. WORD-LEVEL COVERAGE PROBE ────────────────────────────────────────────
print("\n\n── 3. MISSED FACTS vs CONTENT COVERAGE ────────────────────────────")
print("Checking whether missed fact keywords appear in output at all")

# Ground-truth fact keywords for each query (from eval_a_factual.md)
MISSING_FACTS = {
    "rust async await best practices": [
        ("Send-safe types / Rc / RefCell", ["Rc", "RefCell", "Send"]),
        ("join! for concurrent futures",  ["join!", "join !"]),
    ],
    "CRISPR gene editing mechanism explained": [
        ("Guide RNA directs Cas9",          ["guide RNA", "gRNA", "Cas9"]),
        ("Cas9 cuts double-stranded DNA",   ["double-stranded", "double stranded", "molecular scissors"]),
        ("PAM site required",               ["PAM", "protospacer adjacent"]),
        ("NHEJ or HDR repair pathways",     ["NHEJ", "HDR", "homology"]),
    ],
    "what causes lithium battery thermal runaway": [
        ("Separator breakdown",             ["separator"]),
        ("Positive feedback loop / cycle",  ["feedback", "cycle", "more heat"]),
    ],
    "PostgreSQL window functions examples": [
        ("LAG/LEAD for prev/next rows",     ["LAG", "LEAD"]),
        ("Concrete SQL example",            ["SELECT", "PARTITION BY", "empsalary"]),
    ],
    "how do solar panels convert light to electricity": [
        ("Electrons dislodged from atoms",  ["electron", "dislodged", "knocked"]),
        ("DC to AC inverter",               ["inverter", "DC", "AC"]),
        ("p-n junction / electric field",   ["p-n", "junction", "electric field"]),
    ],
}

for query, facts in MISSING_FACTS.items():
    output = data[query].lower()
    print(f"\nQuery: {query!r}")
    for fact_name, keywords in facts:
        found = any(kw.lower() in output for kw in keywords)
        status = "PRESENT (false negative?)" if found else "ABSENT from all results"
        print(f"  [{status}]  {fact_name}")
        if found:
            for kw in keywords:
                if kw.lower() in output:
                    # find the snippet around it
                    idx = output.find(kw.lower())
                    snippet = data[query][max(0, idx-80):idx+80].replace("\n", " ")
                    print(f"    keyword={kw!r}  context: ...{snippet}...")
                    break


# ── 4. CONTENT BUDGET ESTIMATE ──────────────────────────────────────────────
print("\n\n── 4. BUDGET COMPRESSION ESTIMATE ─────────────────────────────────")
print("Target = 500 chars. Estimates of full-page content that likely existed.\n")
print("Observation: each 'full' extraction shows chunk selection output.")
print("We can see how much of the budget was consumed vs what a 1500-char budget")
print("would look like by examining what content is present.\n")

total_full_content = 0
full_result_count = 0
for query, output in data.items():
    blocks = result_block_re.findall(output)
    for num, body in blocks:
        if "[snippet]" not in body:
            lines = body.strip().splitlines()
            content_start = 0
            for i, line in enumerate(lines):
                if line.strip() == "" and i > 1:
                    content_start = i + 1
                    break
            content = "\n".join(lines[content_start:]).strip()
            total_full_content += len(content)
            full_result_count += 1

print(f"Full-extraction results: {full_result_count}")
print(f"Average content per full result: {total_full_content / max(full_result_count, 1):.0f} chars")
print(f"Target budget: 500 chars")
print(f"That means on average {total_full_content / max(full_result_count, 1) / 500:.1f}x budget is already close to limit")
print()
print("Note: The 500-char budget is hit AFTER chunk selection.")
print("The full extracted page would be 1000-10000 chars before chunking.")
print("With 1500-char budget, ~3 chunks of ~500 chars each could be returned")
print("instead of 1 chunk, covering more of the page's facts.")


# ── 5. BM25 RANKING EFFECT ──────────────────────────────────────────────────
print("\n\n── 5. BM25 RANKING EFFECT ──────────────────────────────────────────")
print("Checking if snippets appear at top positions (BM25 ranking them up)\n")

score_re = re.compile(r"## Result (\d+) \(score: ([0-9.]+|N/A)\)")

for query, output in data.items():
    matches = score_re.findall(output)
    print(f"Query: {query!r}")
    for pos, (num, score) in enumerate(matches, 1):
        # find the body for this result number
        pat = re.compile(
            rf"## Result {num} \(score: [^\)]+\)(.*?)(?=## Result |\Z)", re.DOTALL
        )
        m = pat.search(output)
        body = m.group(1) if m else ""
        tag = "[SNIPPET]" if "[snippet]" in body else "[full]  "
        print(f"  Rank {pos} -> Result {num}  score={score}  {tag}")
    print()
