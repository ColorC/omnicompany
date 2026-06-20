# [OMNI] origin=claude-code agent=ai-ide-cbd21319 ts=2026-06-18T20:40:38Z
import json
from collections import Counter

records = []
with open("data/domains/decisions/library/records.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        records.append(json.loads(line.strip()))

id_counts = Counter(r.get("id") for r in records)
dups = dict((k, v) for k, v in id_counts.items() if v > 1)
print("Duplicate IDs count:", len(dups))
print("Total records:", len(records))

validation_fail = [r for r in records if r.get("validation", {}).get("ok") == False]
print("Validation failed:", len(validation_fail))
for r in validation_fail[:10]:
    issues = r.get("validation", {}).get("issues", [])
    stmt = r.get("statement", "")[:60]
    print("  ", r.get("id", ""), "| kind=" + r.get("kind", ""), "| issues:", issues)

no_kind = [r for r in records if not r.get("kind")]
print("No kind field:", len(no_kind))

no_statement = [r for r in records if not r.get("statement")]
print("No statement field:", len(no_statement))
