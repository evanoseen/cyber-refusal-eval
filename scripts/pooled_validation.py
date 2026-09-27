"""Pool the spot check and the gpt-oss-120b weighted verbosity check, deduplicated.

Both scripts/build_spot_check.py and scripts/build_verbosity_check.py sample
from the same 90 cell pool, so some (chain, model, variant) triples appear
in both. This script identifies the overlap, builds a deduplicated pooled
set, and reports disagreement direction overall and per model.

The golden set (MEMORY/golden_set_answer_key.md) is deliberately excluded
from this pool. It structurally overlaps 5 chains with the spot check and 2
with the verbosity check (all Llama), but Evan's own per item labels from
that check were never saved to a file, only the aggregate result (16/20,
4 disagreements, all COMPLIED-human/PARTIAL-judge). Without per item labels
there is no way to know whether any of those 4 disagreements fall on the
overlapping chains, so it cannot be merged into this pool without risking
double counting. Report it separately.

Usage:
    python3 scripts/pooled_validation.py "<verbosity check reply string>"
"""

import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPOT_CHECK_CSV = REPO_ROOT / "results" / "spot_check.csv"
VERBOSITY_ANSWER_KEY = REPO_ROOT / "MEMORY" / "verbosity_check_answer_key.md"
OUT_PATH = REPO_ROOT / "results" / "pooled_validation.csv"

ORDER = {"REFUSED": 0, "PARTIAL": 1, "COMPLIED": 2}


def load_spot_check() -> list[dict]:
    rows = []
    with SPOT_CHECK_CSV.open() as f:
        for row in csv.DictReader(f):
            rows.append(
                {
                    "chain": row["chain"],
                    "model": row["model"],
                    "variant": row["variant"],
                    "human": row["human_label"],
                    "judge": row["judge_label"],
                }
            )
    return rows


def parse_human_labels(reply: str) -> dict[int, str]:
    labels = {}
    for match in re.finditer(r"(\d+)\s*[:.]?\s*(REFUSED|PARTIAL|COMPLIED)", reply, re.IGNORECASE):
        labels[int(match.group(1))] = match.group(2).upper()
    return labels


def load_verbosity_check(reply: str) -> list[dict]:
    human_labels = parse_human_labels(reply)
    rows = []
    text = VERBOSITY_ANSWER_KEY.read_text()
    for line in text.splitlines():
        match = re.match(
            r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(REFUSED|PARTIAL|COMPLIED)\s*\|",
            line,
        )
        if match:
            item = int(match.group(1))
            rows.append(
                {
                    "chain": match.group(2),
                    "model": match.group(3),
                    "variant": "multi_turn",
                    "human": human_labels[item],
                    "judge": match.group(4),
                }
            )
    return rows


def dedupe(spot: list[dict], verbosity: list[dict]) -> tuple[dict, int]:
    pooled = {}
    for row in spot:
        pooled[(row["chain"], row["model"], row["variant"])] = row
    added = 0
    for row in verbosity:
        key = (row["chain"], row["model"], row["variant"])
        if key not in pooled:
            pooled[key] = row
            added += 1
    return pooled, added


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('usage: python3 scripts/pooled_validation.py "1 REFUSED, 2 PARTIAL, ..."')
        sys.exit(1)

    spot = load_spot_check()
    verbosity = load_verbosity_check(sys.argv[1])
    pooled, added = dedupe(spot, verbosity)

    print(f"spot check items: {len(spot)}")
    print(f"verbosity check items: {len(verbosity)}")
    print(f"new items added from verbosity check (non overlap): {added}")
    print(f"total deduplicated pooled items: {len(pooled)}")
    print()

    rows_out = []
    for (chain, model, variant), row in sorted(pooled.items()):
        agree = row["human"] == row["judge"]
        direction = "" if agree else ("judge_more_generous" if ORDER[row["judge"]] > ORDER[row["human"]] else "human_more_generous")
        rows_out.append(
            {
                "chain": chain,
                "model": model,
                "variant": variant,
                "human_label": row["human"],
                "judge_label": row["judge"],
                "agree": agree,
                "direction": direction,
            }
        )

    with OUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)

    for model in ["gpt-oss-120b", "llama-3.3-70b", "qwen-2.5-72b"]:
        model_rows = [r for r in rows_out if r["model"] == model]
        disagreements = [r for r in model_rows if not r["agree"]]
        judge_higher = sum(1 for r in disagreements if r["direction"] == "judge_more_generous")
        human_higher = sum(1 for r in disagreements if r["direction"] == "human_more_generous")
        print(
            f"{model}: n={len(model_rows)}, disagreements={len(disagreements)}, "
            f"judge more generous={judge_higher}, human more generous={human_higher}"
        )

    all_disagreements = [r for r in rows_out if not r["agree"]]
    print()
    print(f"pooled total: n={len(rows_out)}, disagreements={len(all_disagreements)}, "
          f"judge more generous={sum(1 for r in all_disagreements if r['direction']=='judge_more_generous')}, "
          f"human more generous={sum(1 for r in all_disagreements if r['direction']=='human_more_generous')}")
    print(f"wrote {OUT_PATH}")
