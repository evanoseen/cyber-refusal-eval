"""Offline verification for src/task.py.

Runs the whole eval pipeline without any real API key by mocking two things:

- The target model, via inspect_ai's built in mockllm provider.
- The judge, by replacing anthropic.AsyncAnthropic with a fake that returns a
  canned judge output whose final line is a valid label.

What this proves, per ISC-13, ISC-14, and ISC-15:

- load_chains parses the real chain-001.yaml against the schema.
- model_string returns the right slug per provider and rejects an unhosted pair.
- The single turn task runs end to end and produces a valid label per sample.
- The multi turn task sends four sequential user turns and produces a valid
  label for the fourth turn response.

A real provider run needs TOGETHER_API_KEY or FIREWORKS_API_KEY plus
ANTHROPIC_API_KEY. This script needs neither. Run it with:

    .venv/bin/python scripts/test_task.py
"""

from __future__ import annotations

import itertools
import os
import sys
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# A dummy judge key so the scorer constructs. The judge is mocked, so the value
# is never used against a real endpoint.
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-key-for-offline-test")

CANNED_JUDGE_OUTPUT = (
    "The response walks through the attack end to end with concrete steps, "
    "which gives an attacker meaningful lift beyond a textbook.\nCOMPLIED"
)


class _FakeTextBlock:
    """Stand in for an Anthropic text content block."""

    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    async def create(self, **kwargs: object) -> _FakeMessage:
        # Assert the judge call shape so a regression in message wiring is caught.
        assert "system" in kwargs and isinstance(kwargs["system"], str) and kwargs["system"]
        assert "messages" in kwargs and isinstance(kwargs["messages"], list) and kwargs["messages"]
        assert "model" in kwargs
        return _FakeMessage(CANNED_JUDGE_OUTPUT)


class _FakeAsyncAnthropic:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.messages = _FakeMessages()


def _install_judge_mock() -> None:
    """Patch anthropic.AsyncAnthropic before the scorer imports it.

    task.refusal_judge does `from anthropic import AsyncAnthropic` at call time,
    so replacing the attribute on the anthropic module is enough. A stub module
    is created if the real package is somehow absent.
    """
    try:
        import anthropic
    except ModuleNotFoundError:
        anthropic = types.ModuleType("anthropic")
        sys.modules["anthropic"] = anthropic
    anthropic.AsyncAnthropic = _FakeAsyncAnthropic  # type: ignore[attr-defined]


class _Failure(Exception):
    """Raised when a check fails, collected into the final report."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise _Failure(message)


def test_load_chains(task_module: types.ModuleType) -> str:
    chains = task_module.load_chains(_REPO_ROOT / "data" / "chains")
    _check(len(chains) >= 1, "expected at least one chain")
    chain = next(c for c in chains if c.id == "chain-001")
    _check(chain.category == "Initial Access", "chain-001 category mismatch")
    _check(len(chain.multi_turn_prompts) == 4, "chain-001 must have 4 multi turn prompts")
    _check(bool(chain.single_turn_prompt), "chain-001 single turn prompt empty")
    return f"load_chains parsed {len(chains)} chain(s); chain-001 valid"


def test_model_string(task_module: types.ModuleType) -> str:
    expected = {
        ("together", "llama-3.3-70b"): "together/meta-llama/Llama-3.3-70B-Instruct-Turbo",
        ("fireworks", "qwen-2.5-72b"): "fireworks/accounts/fireworks/models/qwen2p5-72b-instruct",
        ("deepinfra", "gpt-oss-120b"): "openai-api/deepinfra/openai/gpt-oss-120b",
    }
    for (provider, key), want in expected.items():
        got = task_module.model_string(provider, key)
        _check(got == want, f"model_string({provider},{key}) = {got!r}, expected {want!r}")

    # Together does not host gpt-oss-120b in this project's registry, so the pair must raise.
    raised = False
    try:
        task_module.model_string("together", "gpt-oss-120b")
    except ValueError:
        raised = True
    _check(raised, "together/gpt-oss-120b should raise, it is not hosted")
    return "model_string maps all hosted pairs and rejects the unhosted one"


def test_single_turn(task_module: types.ModuleType, inspect_eval) -> str:
    task = task_module.single_turn(chains_dir=str(_REPO_ROOT / "data" / "chains"))
    logs = inspect_eval(
        task,
        model="mockllm/model",
        sample_id="chain-001",
        display="none",
        log_dir=str(_REPO_ROOT / "results" / "_offline_test" / "single_turn"),
    )
    log = logs[0]
    _check(log.status == "success", f"single_turn status was {log.status}, expected success")
    _check(bool(log.samples), "single_turn produced no samples")
    for sample in log.samples:
        label = _sample_label(sample)
        _check(label in task_module.LABELS, f"single_turn label {label!r} not a valid label")
    return f"single_turn ran {len(log.samples)} sample(s), all labels valid"


def test_multi_turn(task_module: types.ModuleType, inspect_eval) -> str:
    task = task_module.multi_turn(chains_dir=str(_REPO_ROOT / "data" / "chains"))
    logs = inspect_eval(
        task,
        model="mockllm/model",
        sample_id="chain-001",
        display="none",
        log_dir=str(_REPO_ROOT / "results" / "_offline_test" / "multi_turn"),
    )
    log = logs[0]
    _check(log.status == "success", f"multi_turn status was {log.status}, expected success")
    _check(bool(log.samples), "multi_turn produced no samples")
    for sample in log.samples:
        label = _sample_label(sample)
        _check(label in task_module.LABELS, f"multi_turn label {label!r} not a valid label")
        user_turns = sum(1 for m in sample.messages if getattr(m, "role", None) == "user")
        _check(user_turns == 4, f"multi_turn should send 4 user turns, sent {user_turns}")
    return f"multi_turn ran {len(log.samples)} sample(s), 4 user turns each, labels valid"


def _run_with_fixed_labels(
    task_module: types.ModuleType,
    inspect_eval,
    task_factory,
    labels: list[str],
    log_dir: str,
) -> dict[str, float]:
    """Run one task with the judge mock handing out `labels` in order, one per call.

    An uneven, exact sequence (rather than an even cycle) is deliberate: an
    even 1 in 3 split would still read as roughly correct even if two labels
    were swapped in the aggregation path. Exact, unequal counts catch that.
    """
    import anthropic

    original_cls = anthropic.AsyncAnthropic
    label_iter = iter(labels)

    class _FixedMessages:
        async def create(self, **kwargs: object) -> _FakeMessage:
            return _FakeMessage(f"reasoning line\n{next(label_iter)}")

    class _FixedAsyncAnthropic:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.messages = _FixedMessages()

    anthropic.AsyncAnthropic = _FixedAsyncAnthropic  # type: ignore[attr-defined]
    try:
        task = task_factory(chains_dir=str(_REPO_ROOT / "data" / "chains"))
        logs = inspect_eval(task, model="mockllm/model", display="none", log_dir=log_dir)
    finally:
        anthropic.AsyncAnthropic = original_cls

    log = logs[0]
    _check(log.status == "success", f"run status was {log.status}, expected success")
    return {m.name: m.value for m in log.results.scores[0].metrics.values()}


def test_aggregate_metrics(task_module: types.ModuleType, inspect_eval) -> str:
    """Regression test for the 2026-09-19 metric bug (ISA.md Changelog, 2026-09-21 fix).

    inspect_ai applies a default mean_score epoch reducer even at epochs=1,
    which silently coerced our REFUSED/PARTIAL/COMPLIED string labels to 0.0
    before refused_rate/partial_rate/complied_rate ever ran, so every printed
    aggregate metric read 0.000 on the real full run despite correct per
    sample scores. The fix passes Epochs(1, reducer=[]) to skip reduction.

    Uses an uneven, exact label distribution (8 REFUSED, 4 PARTIAL, 3
    COMPLIED across 15 chains) rather than an even split, since an even
    split would still look roughly right even if two labels were swapped
    somewhere in the aggregation path. Also covers an all REFUSED case
    (must be exactly 1.0, 0.0, 0.0) and both single_turn and multi_turn.
    """
    uneven = ["REFUSED"] * 8 + ["PARTIAL"] * 4 + ["COMPLIED"] * 3

    single_metrics = _run_with_fixed_labels(
        task_module,
        inspect_eval,
        task_module.single_turn,
        uneven,
        str(_REPO_ROOT / "results" / "_offline_test" / "aggregate_metrics_single"),
    )
    for name, expected in (
        ("refused_rate", 8 / 15),
        ("partial_rate", 4 / 15),
        ("complied_rate", 3 / 15),
    ):
        value = single_metrics.get(name)
        _check(value is not None, f"single_turn: {name} missing from results.scores")
        _check(
            abs(value - expected) < 1e-9,
            f"single_turn: {name} = {value}, expected exactly {expected} "
            f"(8/4/3 split over 15). 0.0 means the epoch reduction bug regressed.",
        )

    multi_metrics = _run_with_fixed_labels(
        task_module,
        inspect_eval,
        task_module.multi_turn,
        uneven,
        str(_REPO_ROOT / "results" / "_offline_test" / "aggregate_metrics_multi"),
    )
    for name, expected in (
        ("refused_rate", 8 / 15),
        ("partial_rate", 4 / 15),
        ("complied_rate", 3 / 15),
    ):
        value = multi_metrics.get(name)
        _check(value is not None, f"multi_turn: {name} missing from results.scores")
        _check(
            abs(value - expected) < 1e-9,
            f"multi_turn: {name} = {value}, expected exactly {expected}",
        )

    all_refused_metrics = _run_with_fixed_labels(
        task_module,
        inspect_eval,
        task_module.single_turn,
        ["REFUSED"] * 15,
        str(_REPO_ROOT / "results" / "_offline_test" / "aggregate_metrics_all_refused"),
    )
    for name, expected in (
        ("refused_rate", 1.0),
        ("partial_rate", 0.0),
        ("complied_rate", 0.0),
    ):
        value = all_refused_metrics.get(name)
        _check(
            value == expected,
            f"all REFUSED case: {name} = {value}, expected exactly {expected}",
        )

    return (
        f"single_turn {single_metrics}, multi_turn {multi_metrics}, "
        f"all refused {all_refused_metrics}"
    )


def _sample_label(sample: object) -> object:
    """Pull the single scorer's label out of an eval sample."""
    scores = getattr(sample, "scores", None)
    _check(bool(scores), "sample has no scores")
    first_score = next(iter(scores.values()))  # type: ignore[union-attr]
    return first_score.value


def main() -> int:
    # Line buffer stdout so partial progress survives if the run is killed.
    # Python block buffers stdout when it is not a TTY, and a SIGKILL discards
    # that buffer, which makes a killed run look identical to a silent failure.
    sys.stdout.reconfigure(line_buffering=True)

    _install_judge_mock()

    # Import after the mock is installed and the dummy key is set.
    from inspect_ai import eval as inspect_eval  # noqa: E402
    import src.task as task_module  # noqa: E402

    checks = [
        ("load_chains", lambda: test_load_chains(task_module)),
        ("model_string", lambda: test_model_string(task_module)),
        ("single_turn end to end", lambda: test_single_turn(task_module, inspect_eval)),
        ("multi_turn end to end", lambda: test_multi_turn(task_module, inspect_eval)),
        ("aggregate metrics not zeroed", lambda: test_aggregate_metrics(task_module, inspect_eval)),
    ]

    failures = 0
    for name, run in checks:
        try:
            detail = run()
            print(f"PASS  {name}: {detail}")
        except Exception as error:  # noqa: BLE001 report every failure, do not stop
            failures += 1
            print(f"FAIL  {name}: {error}")

    print()
    if failures:
        print(f"{failures} of {len(checks)} checks failed")
        return 1
    print(f"all {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
