"""One-chain smoke test for Qwen 2.5 72B and Mistral Large 2 on DeepInfra.

Llama 3.3 70B on DeepInfra already has a real verified pilot (results/pilot/,
2026-08-25, ISC-16). Qwen and Mistral have not had a single live call against
the DeepInfra endpoint yet, so per spend.md discipline rule 1 (never run a
paid evaluation without a 1 to 3 chain smoke test first), this runs both new
models against chain-001 only, single_turn variant, before the full 90 cell
run touches them.

Usage:
    python3 scripts/smoke_test_new_models.py
"""

from inspect_ai import eval as inspect_eval

from src.task import model_string, single_turn

MODELS = [
    model_string("deepinfra", "qwen-2.5-72b"),
    model_string("deepinfra", "mistral-large-2"),
]

if __name__ == "__main__":
    logs = inspect_eval(
        tasks=single_turn,
        model=MODELS,
        sample_id="chain-001",
        log_dir="results/pilot",
    )
    for log in logs:
        status = log.status
        model = log.eval.model
        n_samples = len(log.samples) if log.samples else 0
        print(f"model={model} status={status} samples={n_samples}")
        if log.samples:
            for sample in log.samples:
                score = sample.scores
                print(f"  sample={sample.id} scores={score}")
