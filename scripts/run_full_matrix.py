"""Full 90 cell matrix run for ISC-18/ISC-19: 15 chains x 2 variants x 3 models.

Models: Llama 3.3 70B, Qwen 2.5 72B, openai/gpt-oss-120b, all via DeepInfra
(the only provider that hosts all three, per ISA.md Decisions). Runs both
task variants (single_turn, multi_turn) across all three models in one
process, so the slow inspect_ai import cost is paid once, not six times.

Per spend.md discipline rule 1, this only runs after: Llama (2026-08-25
pilot), Qwen and gpt-oss-120b (2026-09-19 smoke tests) were each already
confirmed live against DeepInfra. Per discipline rule 3, log every run to
spend.md before closing the session that made the spend.

Usage:
    python3 scripts/run_full_matrix.py
"""

from inspect_ai import eval as inspect_eval

from src.task import model_string, multi_turn, single_turn

MODELS = [
    model_string("deepinfra", "llama-3.3-70b"),
    model_string("deepinfra", "qwen-2.5-72b"),
    model_string("deepinfra", "gpt-oss-120b"),
]

if __name__ == "__main__":
    for label, task in (("single_turn", single_turn), ("multi_turn", multi_turn)):
        print(f"=== {label} across {len(MODELS)} models, 15 chains each ===", flush=True)
        logs = inspect_eval(
            tasks=task,
            model=MODELS,
            log_dir="results/full_run",
        )
        for log in logs:
            n_samples = len(log.samples) if log.samples else 0
            print(f"{label} model={log.eval.model} status={log.status} samples={n_samples}", flush=True)
