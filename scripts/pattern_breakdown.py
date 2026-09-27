"""Escalation pattern breakdown: COMPLIED rate by model and pattern, n=5 chains each.

Each of the 5 ATT&CK categories runs the same technique through 3 escalation
patterns (data/sanitization_log.md "Design note"): A conceptual bracketing,
B authority roleplay, C defensive framing pivot. That gives 5 chains per
pattern per model (one per category), pooling across categories the same way
results/bootstrap_by_model.csv pools across patterns.

The chain to pattern mapping below is transcribed directly from
data/sanitization_log.md's per chain table, not inferred, since chain
numbering happens to follow chain number mod 3 but that is a coincidence of
authoring order, not a documented rule this script should re derive.

Usage:
    python3 scripts/pattern_breakdown.py
"""

import csv
from collections import defaultdict
from pathlib import Path

from inspect_ai.log import read_eval_log

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "results" / "full_run"
OUT_PATH = REPO_ROOT / "results" / "pattern_breakdown.csv"

MODEL_SHORT_NAMES = {
    "openai-api/deepinfra/meta-llama/Llama-3.3-70B-Instruct": "llama-3.3-70b",
    "openai-api/deepinfra/Qwen/Qwen2.5-72B-Instruct": "qwen-2.5-72b",
    "openai-api/deepinfra/openai/gpt-oss-120b": "gpt-oss-120b",
}
MODEL_ORDER = ["gpt-oss-120b", "llama-3.3-70b", "qwen-2.5-72b"]

# Transcribed from data/sanitization_log.md's per chain table.
PATTERN = {
    "chain-001": "A", "chain-004": "A", "chain-007": "A", "chain-010": "A", "chain-013": "A",
    "chain-002": "B", "chain-005": "B", "chain-008": "B", "chain-011": "B", "chain-014": "B",
    "chain-003": "C", "chain-006": "C", "chain-009": "C", "chain-012": "C", "chain-015": "C",
}
PATTERN_NAME = {
    "A": "conceptual bracketing",
    "B": "authority roleplay",
    "C": "defensive framing pivot",
}


def load_paired() -> dict[tuple[str, str], dict[str, str]]:
    data: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for path in sorted(LOG_DIR.glob("*.eval")):
        log = read_eval_log(str(path))
        variant = "single" if "single-turn" in log.eval.task else "multi"
        model = MODEL_SHORT_NAMES.get(log.eval.model, log.eval.model)
        for sample in log.samples or []:
            score = sample.scores.get("refusal_judge") if sample.scores else None
            if score is None:
                continue
            chain_id = score.metadata.get("chain_id")
            data[(model, chain_id)][variant] = score.value
    return data


if __name__ == "__main__":
    data = load_paired()
    rows = []
    for model in MODEL_ORDER:
        for pattern in ("A", "B", "C"):
            chains = [c for c, p in PATTERN.items() if p == pattern]
            n = len(chains)
            complied_single = sum(1 for c in chains if data[(model, c)].get("single") == "COMPLIED")
            complied_multi = sum(1 for c in chains if data[(model, c)].get("multi") == "COMPLIED")
            rows.append(
                {
                    "model": model,
                    "pattern": pattern,
                    "pattern_name": PATTERN_NAME[pattern],
                    "n_chains": n,
                    "complied_single": complied_single,
                    "complied_multi": complied_multi,
                    "complied_rate_single": round(complied_single / n, 3),
                    "complied_rate_multi": round(complied_multi / n, 3),
                    "complied_rate_delta": round((complied_multi - complied_single) / n, 3),
                }
            )
            print(
                f"{model:14s} {PATTERN_NAME[pattern]:24s} "
                f"single {complied_single}/{n}  multi {complied_multi}/{n}  "
                f"delta {(complied_multi - complied_single) / n:+.0%}"
            )

    with OUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT_PATH}")
