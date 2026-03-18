"""Analyse BM25 score ordering and the solar/thermal false-positive cases."""

import json
import re

DATA_PATH = "/home/fortu/GitHub/open-search/research/eval_a_our_output.json"

with open(DATA_PATH) as f:
    data = json.load(f)

# The formatted output has "## Result N (score: X.XXXX)\n**Title**\nURL\n\ncontent"
result_re = re.compile(
    r"## Result (\d+) \(score: ([0-9.]+|N/A)\)\n\*\*(.+?)\*\*\n(https?://\S+)\n\n(.*?)(?=\n\n---|\Z)",
    re.DOTALL,
)

print("=" * 70)
print("BM25 SCORE ORDERING")
print("=" * 70)

for query, output in data.items():
    matches = result_re.findall(output)
    print(f"\nQuery: {query!r}")
    print(f"  {'Rank':<5} {'Score':<8} {'Type':<9} URL")
    for rank_num, (result_num, score, title, url, content) in enumerate(matches, 1):
        kind = "SNIPPET" if "[snippet]" in content else "full"
        print(f"  {rank_num:<5} {score:<8} {kind:<9} {url}")


print("\n\n" + "=" * 70)
print("SOLAR: 'DC' keyword context (checking false positive)")
print("=" * 70)
solar_out = data["how do solar panels convert light to electricity"]
idx = solar_out.lower().find("ac")
if idx >= 0:
    print(repr(solar_out[max(0, idx-150):idx+150]))
print("\n--- reliant.com content ---")
# find reliant block
m = re.search(r"(reliant\.com.*?)(?=\n\n---|\Z)", solar_out, re.DOTALL)
if m:
    print(repr(m.group(0)[:800]))


print("\n\n" + "=" * 70)
print("THERMAL RUNAWAY: 'more heat' context (checking false positive)")
print("=" * 70)
thermal_out = data["what causes lithium battery thermal runaway"]
idx = thermal_out.lower().find("more heat")
if idx >= 0:
    print(repr(thermal_out[max(0, idx-200):idx+200]))


print("\n\n" + "=" * 70)
print("CRISPR: the ONE full extraction (innovativegenomics.org)")
print("=" * 70)
crispr_out = data["CRISPR gene editing mechanism explained"]
m = re.search(r"(innovativegenomics\.org.*?)(?=\n\n---|\Z)", crispr_out, re.DOTALL)
if m:
    print(m.group(0))


print("\n\n" + "=" * 70)
print("RUST: full extraction content (what facts were included)")
print("=" * 70)
rust_out = data["rust async await best practices"]
# Print each result body
for m in result_re.finditer(rust_out):
    result_num, score, title, url, content = m.groups()
    kind = "SNIPPET" if "[snippet]" in content else "full"
    print(f"\n[{kind}] Result {result_num} (score={score})")
    print(f"URL: {url}")
    print(content[:600])


print("\n\n" + "=" * 70)
print("POSTGRES: full extraction content (missing LAG/LEAD and SQL example)")
print("=" * 70)
pg_out = data["PostgreSQL window functions examples"]
for m in result_re.finditer(pg_out):
    result_num, score, title, url, content = m.groups()
    kind = "SNIPPET" if "[snippet]" in content else "full"
    print(f"\n[{kind}] Result {result_num} (score={score})")
    print(f"URL: {url}")
    print(content[:600])
