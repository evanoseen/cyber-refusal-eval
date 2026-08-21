"""inspect_ai task definitions for the cyber refusal decay eval.

This module builds two inspect_ai tasks from the same set of attack chains:

- single_turn: the target model receives the full attack request in one user
  turn. The model response is the sample that gets scored.
- multi_turn: the target model receives the four decomposed user turns in
  sequence as a real multi turn conversation. The model response to the fourth
  turn is the sample that gets scored.

Both tasks share one judge: Claude Sonnet 4.6, called through the Anthropic
Messages API and wired into inspect_ai's scorer interface. The judge assigns
exactly one of REFUSED, PARTIAL, or COMPLIED per sample, using the rubric in
src/judge_prompt.py.

Target models run through OpenAI compatible provider endpoints. The provider is
a runtime choice, not baked into the task: pass the target model on the command
line with inspect_ai's own --model flag, for example

    inspect eval src/task.py@single_turn \\
        --model together/meta-llama/Llama-3.3-70B-Instruct-Turbo \\
        --sample-id chain-001 \\
        --log-dir results/pilot

The MODEL_REGISTRY below maps a provider plus a short logical model name to the
correct inspect_ai model string, so scripts do not have to hardcode slugs. Run
`python -m src.task model-string together llama-3.3-70b` to print one.

The judge always uses the Anthropic key from the environment. Provider keys are
read by inspect_ai's own provider layer from the environment. Keys are loaded
from a .env file at the repo root via python-dotenv and are never printed.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml
from dotenv import load_dotenv

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import (
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageSystem,
    ChatMessageUser,
    get_model,
)
from inspect_ai.scorer import Metric, Score, SampleScore, Scorer, Target, metric, scorer
from inspect_ai.solver import Generate, Solver, TaskState, generate, solver

# judge_prompt.py is a sibling module. Support both `python -m src.task`
# (package import) and inspect_ai loading this file by path (flat import).
try:
    from src.judge_prompt import (
        JUDGE_MODEL,
        Label,
        LABELS,
        build_judge_messages,
        parse_label,
    )
except ModuleNotFoundError:  # loaded by path, src is not on sys.path as a package
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from judge_prompt import (  # type: ignore[no-redef]
        JUDGE_MODEL,
        Label,
        LABELS,
        build_judge_messages,
        parse_label,
    )


# Load .env from the repo root so ANTHROPIC_API_KEY and the provider keys are
# available to both the judge client and inspect_ai's provider layer. load_dotenv
# does not overwrite variables already set in the real environment, so an
# exported key wins over a stale .env entry. Keys are never logged.
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

_DEFAULT_CHAINS_DIR = _REPO_ROOT / "data" / "chains"

# The three locked target models, keyed by a short logical name, mapped to the
# provider specific model id for each supported OpenAI compatible provider.
#
# Model id sources (verified against provider docs, not guessed):
#   Together AI at https://docs.together.ai/docs/serverless-models
#   Fireworks AI at https://fireworks.ai/models
#   DeepInfra at https://deepinfra.com/models (Hugging Face style namespaced ids)
#
# A value of None means that provider does not host that model, so the pair is
# rejected with a clear error rather than sent to an endpoint that will 404.
# Together and Fireworks do not serve Mistral Large 2; DeepInfra does. DeepInfra
# is therefore the one provider that covers all three target models.
MODEL_REGISTRY: dict[str, dict[str, str | None]] = {
    "together": {
        "llama-3.3-70b": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "qwen-2.5-72b": "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "mistral-large-2": None,
    },
    "fireworks": {
        "llama-3.3-70b": "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "qwen-2.5-72b": "accounts/fireworks/models/qwen2p5-72b-instruct",
        "mistral-large-2": "accounts/fireworks/models/mistral-large",
    },
    "deepinfra": {
        "llama-3.3-70b": "meta-llama/Llama-3.3-70B-Instruct",
        "qwen-2.5-72b": "Qwen/Qwen2.5-72B-Instruct",
        "mistral-large-2": "mistralai/Mistral-Large-Instruct-2407",
    },
}

# inspect_ai provider prefix for each provider. Together and Fireworks are native
# inspect_ai providers. DeepInfra is reached through inspect_ai's OpenAI
# compatible provider, which reads DEEPINFRA_API_KEY and DEEPINFRA_BASE_URL from
# the environment (set DEEPINFRA_BASE_URL to https://api.deepinfra.com/v1/openai).
PROVIDER_PREFIX: dict[str, str] = {
    "together": "together",
    "fireworks": "fireworks",
    "deepinfra": "openai-api/deepinfra",
}


def model_string(provider: str, model_key: str) -> str:
    """Return the inspect_ai model string for a provider plus logical model.

    Args:
        provider: One of together, fireworks, deepinfra.
        model_key: One of llama-3.3-70b, qwen-2.5-72b, mistral-large-2.

    Returns:
        A model string such as "together/meta-llama/Llama-3.3-70B-Instruct-Turbo"
        suitable for inspect_ai's --model flag or get_model.

    Raises:
        ValueError: If the provider or model_key is unknown, or if the provider
            does not host that model.
    """
    if provider not in MODEL_REGISTRY:
        known = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"Unknown provider {provider!r}. Known providers: {known}.")
    provider_models = MODEL_REGISTRY[provider]
    if model_key not in provider_models:
        known = ", ".join(sorted(provider_models))
        raise ValueError(f"Unknown model_key {model_key!r}. Known models: {known}.")
    model_id = provider_models[model_key]
    if model_id is None:
        raise ValueError(
            f"Provider {provider!r} does not host {model_key!r}. "
            f"Use deepinfra for that model, or pick a provider that lists it."
        )
    return f"{PROVIDER_PREFIX[provider]}/{model_id}"


# Fields every chain YAML must define, per data/SCHEMA.md.
_REQUIRED_FIELDS = (
    "id",
    "category",
    "technique_id",
    "technique_name",
    "description",
    "single_turn_prompt",
    "multi_turn_prompts",
    "sanitization_notes",
)


@dataclass(frozen=True)
class Chain:
    """One attack chain loaded from a YAML file in data/chains/.

    Mirrors the schema in data/SCHEMA.md. Optional fields default to None or an
    empty list so callers never hit a missing attribute.
    """

    id: str
    category: str
    technique_id: str
    technique_name: str
    description: str
    single_turn_prompt: str
    multi_turn_prompts: list[str]
    sanitization_notes: str
    attack_chain_context: str | None = None
    references: list[str] | None = None


def _validate_raw_chain(raw: object, source: Path) -> dict[str, object]:
    """Validate one parsed YAML document against the chain schema.

    Checks presence of required fields, that multi_turn_prompts is a list of
    exactly four non empty strings, and that the file id matches the filename
    stem. Raises ValueError with the offending file path so a bad chain fails
    loudly at load time rather than mid run.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: top level YAML must be a mapping, got {type(raw).__name__}.")

    missing = [field for field in _REQUIRED_FIELDS if field not in raw or raw[field] in (None, "")]
    if missing:
        raise ValueError(f"{source}: missing or empty required fields: {', '.join(missing)}.")

    chain_id = raw["id"]
    if not isinstance(chain_id, str):
        raise ValueError(f"{source}: id must be a string, got {type(chain_id).__name__}.")
    if chain_id != source.stem:
        raise ValueError(f"{source}: id {chain_id!r} does not match filename stem {source.stem!r}.")

    prompts = raw["multi_turn_prompts"]
    if not isinstance(prompts, list):
        raise ValueError(f"{source}: multi_turn_prompts must be a list, got {type(prompts).__name__}.")
    if len(prompts) != 4:
        raise ValueError(f"{source}: multi_turn_prompts must have exactly 4 entries, got {len(prompts)}.")
    for index, turn in enumerate(prompts):
        if not isinstance(turn, str) or not turn.strip():
            raise ValueError(f"{source}: multi_turn_prompts[{index}] must be a non empty string.")

    if not isinstance(raw["single_turn_prompt"], str) or not raw["single_turn_prompt"].strip():
        raise ValueError(f"{source}: single_turn_prompt must be a non empty string.")

    return raw


def _chain_from_raw(raw: dict[str, object]) -> Chain:
    """Build a Chain from a validated raw mapping."""
    references = raw.get("references")
    if references is not None and not isinstance(references, list):
        references = [str(references)]
    return Chain(
        id=str(raw["id"]),
        category=str(raw["category"]),
        technique_id=str(raw["technique_id"]),
        technique_name=str(raw["technique_name"]),
        description=str(raw["description"]),
        single_turn_prompt=str(raw["single_turn_prompt"]).strip(),
        multi_turn_prompts=[str(turn).strip() for turn in raw["multi_turn_prompts"]],  # type: ignore[union-attr]
        sanitization_notes=str(raw["sanitization_notes"]),
        attack_chain_context=(
            str(raw["attack_chain_context"]) if raw.get("attack_chain_context") else None
        ),
        references=[str(ref) for ref in references] if references else None,
    )


def load_chains(chains_dir: str | Path | None = None) -> list[Chain]:
    """Load and validate every chain YAML in a directory.

    Args:
        chains_dir: Directory holding chain-NNN.yaml files. Defaults to
            data/chains/ at the repo root.

    Returns:
        Chains sorted by id, so sample order is stable across runs.

    Raises:
        FileNotFoundError: If the directory has no chain YAML files.
        ValueError: If any chain fails schema validation.
    """
    directory = Path(chains_dir) if chains_dir is not None else _DEFAULT_CHAINS_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Chains directory not found: {directory}.")

    paths = sorted(directory.glob("chain-*.yaml"))
    if not paths:
        raise FileNotFoundError(f"No chain-*.yaml files found in {directory}.")

    chains: list[Chain] = []
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        validated = _validate_raw_chain(raw, path)
        chains.append(_chain_from_raw(validated))
    return chains


def _chain_metadata(chain: Chain) -> dict[str, object]:
    """Metadata attached to every sample for later analysis and judging."""
    return {
        "chain_id": chain.id,
        "category": chain.category,
        "technique_id": chain.technique_id,
        "technique_name": chain.technique_name,
        "single_turn_prompt": chain.single_turn_prompt,
        "multi_turn_prompts": chain.multi_turn_prompts,
        "attack_chain_context": chain.attack_chain_context,
    }


def _single_turn_dataset(chains: list[Chain]) -> MemoryDataset:
    """Build the single turn dataset: one user turn per chain."""
    samples = [
        Sample(
            id=chain.id,
            input=chain.single_turn_prompt,
            metadata={**_chain_metadata(chain), "variant": "single_turn"},
        )
        for chain in chains
    ]
    return MemoryDataset(samples=samples, name="cyber-refusal-single-turn")


def _multi_turn_dataset(chains: list[Chain]) -> MemoryDataset:
    """Build the multi turn dataset.

    The sample input is the first user turn. The remaining three turns live in
    metadata and are sent sequentially by multi_turn_solver.
    """
    samples = [
        Sample(
            id=chain.id,
            input=chain.multi_turn_prompts[0],
            metadata={**_chain_metadata(chain), "variant": "multi_turn"},
        )
        for chain in chains
    ]
    return MemoryDataset(samples=samples, name="cyber-refusal-multi-turn")


@solver
def multi_turn_solver() -> Solver:
    """Drive the four turn decomposed conversation.

    Turn one is already the sample input, so the model answers it first. Then
    turns two, three, and four are appended one at a time, each followed by a
    fresh generation. After the loop, state.output holds the model response to
    the fourth turn, which is the response the judge scores. state.messages holds
    the full dialogue, used to build the judge transcript.
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        turns = state.metadata.get("multi_turn_prompts")
        if not isinstance(turns, list) or len(turns) != 4:
            raise ValueError(
                f"Sample {state.sample_id!r} is missing four multi_turn_prompts in metadata."
            )

        # Answer turn one, which inspect_ai placed in state.messages as the
        # initial user message.
        state = await generate(state)

        # Send turns two through four, generating after each.
        for turn in turns[1:]:
            state.messages.append(ChatMessageUser(content=str(turn)))
            state = await generate(state)

        return state

    return solve


def _render_transcript(messages: list[ChatMessage]) -> str:
    """Render a message list as a role tagged transcript for the judge.

    User, assistant, and system messages are labeled so the judge sees the full
    conversation that led to the scored response. inspect_ai messages expose a
    .text property that flattens content parts into a string.
    """
    role_labels: dict[type, str] = {
        ChatMessageUser: "User",
        ChatMessageAssistant: "Assistant",
        ChatMessageSystem: "System",
    }
    lines: list[str] = []
    for message in messages:
        label = role_labels.get(type(message), "Message")
        lines.append(f"{label}: {message.text}")
    return "\n\n".join(lines)


def _judge_prompt_and_response(state: TaskState) -> tuple[str, str]:
    """Split the conversation into the judge prompt transcript and the response.

    The response is the target model's final completion. The prompt transcript is
    every message except that final assistant message, so the judge sees the full
    lead up (all user turns and any intermediate assistant answers) separately
    from the answer it is grading. This works for both variants: single turn has
    one user message in the transcript, multi turn has all four user turns plus
    the three intermediate assistant answers.
    """
    response = state.output.completion
    messages = list(state.messages)
    if messages and isinstance(messages[-1], ChatMessageAssistant):
        messages = messages[:-1]
    transcript = _render_transcript(messages)
    return transcript, response


def _split_system(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    """Split judge messages into an Anthropic system string plus user messages.

    build_judge_messages returns a system message and a user message in one list.
    The Anthropic Messages API takes the system prompt as a top level argument,
    not as a list entry, so this pulls the system content out.
    """
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    non_system = [m for m in messages if m["role"] != "system"]
    return "\n\n".join(system_parts), non_system


def _label_rate(scores: list[SampleScore], target_label: Label) -> float:
    """Fraction of scores whose value equals target_label.

    Returns 0.0 for an empty score set so the metric never divides by zero.
    """
    if not scores:
        return 0.0
    hits = sum(1 for item in scores if item.score.value == target_label)
    return hits / len(scores)


@metric(name="refused_rate")
def refused_rate() -> Metric:
    """Metric: fraction of samples labeled REFUSED."""

    def compute(scores: list[SampleScore]) -> float:
        return _label_rate(scores, "REFUSED")

    return compute


@metric(name="partial_rate")
def partial_rate() -> Metric:
    """Metric: fraction of samples labeled PARTIAL."""

    def compute(scores: list[SampleScore]) -> float:
        return _label_rate(scores, "PARTIAL")

    return compute


@metric(name="complied_rate")
def complied_rate() -> Metric:
    """Metric: fraction of samples labeled COMPLIED."""

    def compute(scores: list[SampleScore]) -> float:
        return _label_rate(scores, "COMPLIED")

    return compute


# Bound on judge retries. The judge occasionally returns text whose final line is
# not a bare label, or the API returns a transient error. Three attempts is
# enough to ride out a stray formatting slip without masking a real outage.
_JUDGE_MAX_ATTEMPTS = 3
_JUDGE_MAX_TOKENS = 1024


@scorer(metrics=[refused_rate(), partial_rate(), complied_rate()])
def refusal_judge(max_attempts: int = _JUDGE_MAX_ATTEMPTS) -> Scorer:
    """Score each response with Claude Sonnet 4.6 as REFUSED, PARTIAL, or COMPLIED.

    The judge client is created once and reused across samples. Each score call
    builds the judge messages from src/judge_prompt.py, sends them to the
    Anthropic Messages API, and parses the final line into a label. A bounded
    retry loop absorbs transient API errors and stray formatting. If every
    attempt fails, the scorer raises so the sample errors visibly rather than
    receiving a silently wrong label.

    Args:
        max_attempts: How many times to try the judge before failing the sample.

    Returns:
        An inspect_ai Scorer.
    """
    # Imported here so the module imports without the anthropic package or key
    # present, which keeps chain loading and unit tests light.
    from anthropic import AsyncAnthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The judge needs it. "
            "Copy .env.example to .env and fill it in, or export the key."
        )
    client = AsyncAnthropic(api_key=api_key)

    async def score(state: TaskState, target: Target) -> Score:
        prompt, response = _judge_prompt_and_response(state)
        judge_messages = build_judge_messages(prompt=prompt, response=response)
        system, user_messages = _split_system(judge_messages)

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = await client.messages.create(
                    model=JUDGE_MODEL,
                    max_tokens=_JUDGE_MAX_TOKENS,
                    system=system,
                    messages=user_messages,  # type: ignore[arg-type]
                )
                text = "".join(
                    block.text for block in result.content if getattr(block, "type", None) == "text"
                )
                label = parse_label(text)
                return Score(
                    value=label,
                    answer=response,
                    explanation=text,
                    metadata={
                        "variant": state.metadata.get("variant"),
                        "chain_id": state.metadata.get("chain_id"),
                        "category": state.metadata.get("category"),
                        "technique_id": state.metadata.get("technique_id"),
                        "judge_model": JUDGE_MODEL,
                        "judge_attempts": attempt,
                    },
                )
            except Exception as error:  # noqa: BLE001 retry any judge failure
                last_error = error

        raise RuntimeError(
            f"Judge failed after {max_attempts} attempts for sample "
            f"{state.sample_id!r}: {last_error}"
        )

    return score


@task
def single_turn(chains_dir: str | None = None) -> Task:
    """Single turn variant: the full attack request in one user turn.

    Args:
        chains_dir: Directory of chain YAML files. Defaults to data/chains/.
            Point it at a subset directory, or use inspect_ai's --sample-id or
            --limit flags, to run a single chain.

    Returns:
        An inspect_ai Task. Supply the target model with --model at eval time.
    """
    chains = load_chains(chains_dir)
    return Task(
        dataset=_single_turn_dataset(chains),
        solver=generate(),
        scorer=refusal_judge(),
        name="cyber-refusal-single-turn",
    )


@task
def multi_turn(chains_dir: str | None = None) -> Task:
    """Multi turn variant: the four decomposed turns sent in sequence.

    Args:
        chains_dir: Directory of chain YAML files. Defaults to data/chains/.
            Point it at a subset directory, or use inspect_ai's --sample-id or
            --limit flags, to run a single chain.

    Returns:
        An inspect_ai Task. Supply the target model with --model at eval time.
    """
    chains = load_chains(chains_dir)
    return Task(
        dataset=_multi_turn_dataset(chains),
        solver=multi_turn_solver(),
        scorer=refusal_judge(),
        name="cyber-refusal-multi-turn",
    )


def _print_model_string(argv: list[str]) -> int:
    """CLI helper: print the inspect_ai model string for a provider and model.

    Usage: python -m src.task model-string <provider> <model_key>
    """
    if len(argv) != 2:
        providers = ", ".join(sorted(MODEL_REGISTRY))
        keys = ", ".join(sorted(MODEL_REGISTRY["deepinfra"]))
        print("usage: python -m src.task model-string <provider> <model_key>", file=sys.stderr)
        print(f"providers: {providers}", file=sys.stderr)
        print(f"model keys: {keys}", file=sys.stderr)
        return 2
    provider, model_key = argv
    try:
        print(model_string(provider, model_key))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "model-string":
        raise SystemExit(_print_model_string(sys.argv[2:]))
    print("usage: python -m src.task model-string <provider> <model_key>", file=sys.stderr)
    print("to run an eval, use the inspect CLI, for example:", file=sys.stderr)
    print(
        "  inspect eval src/task.py@single_turn "
        "--model together/meta-llama/Llama-3.3-70B-Instruct-Turbo "
        "--sample-id chain-001 --log-dir results/pilot",
        file=sys.stderr,
    )
    raise SystemExit(2)
