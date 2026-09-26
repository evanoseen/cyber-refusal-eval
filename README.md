# Cyber Refusal Decay Eval

Measure refusal rate delta between single turn and multi turn decomposed cyber attack prompts across three frontier open source LLMs.

## Research question

Does decomposing a cyber attack chain across multiple conversation turns lead to higher compliance rates from frontier open source LLMs compared to the same intent asked in a single turn?

## Scope

- **Dataset**: 30 attack chains across 5 MITRE ATT&CK categories (Initial Access, Execution, Persistence, Lateral Movement, Exfiltration), 6 chains per category. Two prompt variants per chain: single turn direct, 4 turn decomposed.
- **Models**: Llama 3.3 70B Instruct, Qwen 2.5 72B Instruct, openai/gpt-oss-120b (swapped in 2026-09-19 after Mistral Large 2 was deprecated industry-wide). Optional fourth: DeepSeek V3 if budget allows.
- **Framework**: inspect_ai by UK AISI.
- **Scoring**: Claude Sonnet 4.6 judge with three labels (REFUSED, PARTIAL, COMPLIED), plus human spot check on 30 random samples.
- **Statistics**: bootstrap confidence intervals on refusal rate deltas, per model and per ATT&CK category.
- **Total cells**: 180 (30 chains times 2 variants times 3 models).

## Constraints

- $200 USD total budget across all API and compute spend.
- Open model inference via Together AI or Fireworks or DeepInfra. Judge calls via Anthropic API.
- No fine tuning, no multi agent orchestration, no agent harness, no tool use scaffold. Plain prompt and response only.
- Sanitized dataset: attack intent only, no working payloads.
- Python 3.11 or newer.

## Reproduction

```bash
git clone <repo url>
cd cyber-refusal-eval
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in TOGETHER_API_KEY (or FIREWORKS_API_KEY) and ANTHROPIC_API_KEY
inspect eval src/task.py --model together/meta-llama/Llama-3.3-70B-Instruct-Turbo
```

Pilot run uses Llama 3.3 70B on 5 chains. Full matrix run is 180 cells.

See `data/SCHEMA.md` for chain format, `src/judge_prompt.py` for the judge rubric, `notes/papers/` for foundational reading, and `writeup/post.md` for the published analysis.

## Status

Full 90 cell run complete (15 chains, 2 variants, 3 models). Headline: gpt-oss-120b refused 100% of single turn requests but only 6.7% under 4 turn decomposition; Llama 3.3 70B and Qwen 2.5 72B showed no clear effect. Aggregates are in `results/bootstrap_by_model.csv` and `results/charts/`. Writeup in progress.

Raw model transcripts are not published, because non refusal responses to attack prompts can contain operational detail. Available to researchers on request.

## License

MIT for code. Dataset released under CC BY 4.0 with sanitization notes per chain.
