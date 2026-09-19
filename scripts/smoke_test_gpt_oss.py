"""One-chain smoke test for openai/gpt-oss-120b on DeepInfra.

gpt-oss-120b replaced Mistral Large 2 in the locked 3-model list on
2026-09-19 after Mistral Large 2 was found deprecated industry-wide (see
ISA.md Decisions). This has never had a single live call against DeepInfra,
so per spend.md discipline rule 1 (never run a paid evaluation without a 1
to 3 chain smoke test first), this runs it against chain-001 only,
single_turn variant, before the full 90 cell run touches it.

Usage:
    python3 scripts/smoke_test_gpt_oss.py
"""

from inspect_ai import eval as inspect_eval

from src.task import model_string, single_turn

MODEL = model_string("deepinfra", "gpt-oss-120b")

if __name__ == "__main__":
    logs = inspect_eval(
        tasks=single_turn,
        model=[MODEL],
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
                print(f"  sample={sample.id} scores={sample.scores}")
