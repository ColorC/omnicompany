# [OMNI] origin=claude-code agent=ai-ide-cbd21319 ts=2026-06-18T16:32:06Z
import json, os
from collections import Counter
from datetime import datetime

records = []
with open('data/domains/decisions/library/records.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        records.append(json.loads(line.strip()))

no_id = [r for r in records if not r.get('id')]
id_counts = Counter(r.get('id') for r in records)
dups = dict((k, v) for k, v in id_counts.items() if v > 1)
validation_fail = [r for r in records if r.get('validation', {}).get('ok') == False]

dates = []
for r in records:
    ca = r.get('created_at')
    if ca:
        try:
            dates.append(datetime.fromisoformat(ca))
        except Exception:
            pass

if dates:
    print("Date range: " + min(dates).strftime("%Y-%m-%d %H:%M") + " to " + max(dates).strftime("%Y-%m-%d %H:%M"))

idx_mtime = os.path.getmtime('data/domains/decisions/library/index.json')
rec_mtime = os.path.getmtime('data/domains/decisions/library/records.jsonl')
print("records.jsonl modified: " + datetime.fromtimestamp(rec_mtime).strftime("%Y-%m-%d %H:%M:%S"))
print("index.json modified: " + datetime.fromtimestamp(idx_mtime).strftime("%Y-%m-%d %H:%M:%S"))
if rec_mtime > idx_mtime:
    print("WARNING: index.json is stale (records.jsonl is newer), needs rebuild")

warnings = []
if no_id:
    warnings.append("Missing IDs: " + str(len(no_id)))
if dups:
    warnings.append("Duplicate IDs: " + str(len(dups)))
if validation_fail:
    warnings.append("Validation failed: " + str(len(validation_fail)))

if warnings:
    print("--- Warnings ---")
    for w in warnings:
        print("  ! " + w)
else:
    print("No data quality issues found.")
