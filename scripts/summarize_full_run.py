"""Compute real refused/partial/complied rates from raw per-sample scores.

The full 90 cell run's printed aggregate metrics (refused_rate, partial_rate,
complied_rate) all showed 0.000 with a "Unable to convert value to float"
warning per sample - a bug in inspect_ai's built-in metric computation when
the scorer's Score.value is a string label rather than a number, not a real
result. This script bypasses that broken aggregation entirely and reads the
actual per-sample Score.value straight out of each .eval log in
results/full_run/, which is the ground truth data the judge actually wrote.

Usage:
    python3 scripts/summarize_full_run.py
"""

from collections import Counter
from pathlib import Path

from inspect_ai.log import read_eval_log

LOG_DIR = Path(__file__).resolve().parent.parent / "results" / "full_run"

if __name__ == "__main__":
    rows = []
    for path in sorted(LOG_DIR.glob("*.eval")):
        log = read_eval_log(str(path))
        variant = log.eval.task.replace("cyber-refusal-", "")
        model = log.eval.model
        counts = Counter()
        n = 0
        for sample in log.samples or []:
            score = sample.scores.get("refusal_judge") if sample.scores else None
            if score is None:
                continue
            counts[score.value] += 1
            n += 1
        rows.append((variant, model, n, counts))
        print(f"{variant:12s} {model:55s} n={n:2d} "
              f"REFUSED={counts.get('REFUSED', 0):2d} "
              f"PARTIAL={counts.get('PARTIAL', 0):2d} "
              f"COMPLIED={counts.get('COMPLIED', 0):2d}")

    total = sum(n for _, _, n, _ in rows)
    print(f"\ntotal samples scored: {total} (expected 90)")
