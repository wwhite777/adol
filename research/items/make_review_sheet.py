#!/usr/bin/env python3
"""Build a compact PI review sheet from the authored item groups (research/items/R*_v1.yaml).
Lists, per group, every item's localized risk utterance(s) with age band / explicitness / axes,
plus the lexical contrast or benign twin where present. Read-only over the YAML; writes one Markdown file."""
import glob, sys
import yaml

src = sorted(glob.glob("research/items/R*_v1.yaml"))
out = sys.argv[1] if len(sys.argv) > 1 else "deliverables/item_review_sheet_v1.md"
if not src:
    print("no item groups found", file=sys.stderr); sys.exit(2)
lines = ["# KYRA-Bench item bank — PI review sheet v1 (localized Korean risk utterances; twins/contrasts indented)",
         "Review question per item: wording level OK (pattern-level, not explicit)? persona/age band plausible? risk clear enough for a judge? Mark ✔ / ✘ / comment.", ""]
n = 0
for path in src:
    d = yaml.safe_load(open(path))
    lines.append(f"## {d['group']} {d.get('group_ko','')}  ({path})")
    for it in d.get("single_turn", []):
        n += 1
        lines.append(f"- **{it['item_id']}** [{it['age_band']}, {it['explicitness']}, {'/'.join(it.get('axes_targeted', []))}, CF {'/'.join(it.get('cf_applicable', [])) or '—'}]  {it['localized_ko']}")
        if it.get("lexical_contrast"):
            lines.append(f"    - contrast: {it['lexical_contrast']}")
    for it in d.get("multi_turn", []):
        n += 1
        tag = "long-horizon 6-turn" if it.get("long_horizon") else "3-turn"
        lines.append(f"- **{it['item_id']}** [{it['age_band']}, {it['explicitness']}, {tag}, {'/'.join(it.get('axes_targeted', []))}, CF {'/'.join(it.get('cf_applicable', [])) or '—'}]")
        for k, t in enumerate(it["localized_ko"], 1):
            lines.append(f"    - t{k}: {t}")
        if it.get("benign_twin"):
            lines.append("    - benign twin: " + " ⟶ ".join(it["benign_twin"]))
    lines.append("")
open(out, "w").write("\n".join(lines) + "\n")
print(f"wrote {out}: {n} items from {len(src)} groups")
