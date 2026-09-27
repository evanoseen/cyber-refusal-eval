"""Compare the original judge run against the framing sensitivity rescore.

Reads results/framing_rescore.csv (written by
scripts/framing_sensitivity_rescore.py) and reports COMPLIED counts by model
and variant, original versus rescored, plus an exact McNemar test on the
rescored labels, single turn versus multi turn COMPLIED, paired by chain,
same method as scripts/mcnemar_test.py. This is a sensitivity check. It does
not modify results/full_run/, results/bootstrap*.csv, results/mcnemar.csv,
or writeup/post.md.

Usage:
    python3 scripts/compare_rescore.py
"""

import csv
from collections import defaultdict
from math import comb
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESCORE_CSV = REPO_ROOT / "results" / "framing_rescore.csv"
OUT_PATH = REPO_ROOT / "results" / "framing_rescore_mcnemar.csv"

MODEL_ORDER = ["gpt-oss-120b", "llama-3.3-70b", "qwen-2.5-72b"]


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return float("nan")
    k = min(b, c)
    p_one_side = sum(comb(n, i) for i in range(0, k + 1)) * (0.5**n)
    return min(1.0, 2 * p_one_side)


if __name__ == "__main__":
    rows = list(csv.DictReader(RESCORE_CSV.open()))

    print("=== COMPLIED counts by model x variant, original vs rescored ===")
    for model in MODEL_ORDER:
        for variant in ["single_turn", "multi_turn"]:
            subset = [r for r in rows if r["model"] == model and r["variant"] == variant]
            orig = sum(1 for r in subset if r["original_label"] == "COMPLIED")
            resc = sum(1 for r in subset if r["rescored_label"] == "COMPLIED")
            print(f"{model:14s} {variant:11s} original {orig}/{len(subset)}  rescored {resc}/{len(subset)}")

    print()
    print("=== COMPLIED counts by escalation pattern, pooled across models ===")
    for pattern in ["A", "B", "C"]:
        subset = [r for r in rows if r["pattern"] == pattern]
        orig = sum(1 for r in subset if r["original_label"] == "COMPLIED")
        resc = sum(1 for r in subset if r["rescored_label"] == "COMPLIED")
        print(f"pattern {pattern}: original {orig}/{len(subset)}  rescored {resc}/{len(subset)}")

    data = defaultdict(dict)
    for r in rows:
        data[(r["model"], r["chain"])][r["variant"]] = r["rescored_label"]

    print()
    print("=== exact McNemar on RESCORED labels, COMPLIED, single vs multi turn ===")
    out_rows = []
    for model in MODEL_ORDER:
        b = c = 0
        for i in range(1, 16):
            chain = f"chain-{i:03d}"
            v = data[(model, chain)]
            s_c = v.get("single_turn") == "COMPLIED"
            m_c = v.get("multi_turn") == "COMPLIED"
            if s_c and not m_c:
                b += 1
            elif not s_c and m_c:
                c += 1
        p = mcnemar_exact(b, c)
        out_rows.append(
            {"model": model, "b_single_complied_multi_not": b, "c_single_not_multi_complied": c, "p_value_exact": round(p, 6)}
        )
        print(f"{model}: b={b} c={c} p={p:.6f}")

    with OUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"\nwrote {OUT_PATH}")
