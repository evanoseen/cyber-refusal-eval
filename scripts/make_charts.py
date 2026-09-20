"""ISC-22 (partial): two of the three required charts, saved to results/charts/.

Chart 3 (agreement rate vs judge for the human spot check) needs ISC-20's
data, which does not exist yet, and is not produced here.

Palette: fixed categorical order from the dataviz skill's reference palette
(references/palette.md), slots 1/2/3 (blue/orange/aqua), never cycled or
reassigned between the two charts' own legends.

Usage:
    python3 scripts/make_charts.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "results" / "charts"

# dataviz skill reference palette, categorical slots 1-3 (light mode).
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"

MODEL_ORDER = ["llama-3.3-70b", "qwen-2.5-72b", "gpt-oss-120b"]
CATEGORY_ORDER = ["Initial Access", "Execution", "Persistence", "Lateral Movement", "Exfiltration"]


def _style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(BASELINE)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)


def chart_refusal_by_model_variant() -> None:
    """100% stacked bar: proportion REFUSED/PARTIAL/COMPLIED per model x variant."""
    from inspect_ai.log import read_eval_log

    MODEL_SHORT_NAMES = {
        "openai-api/deepinfra/meta-llama/Llama-3.3-70B-Instruct": "llama-3.3-70b",
        "openai-api/deepinfra/Qwen/Qwen2.5-72B-Instruct": "qwen-2.5-72b",
        "openai-api/deepinfra/openai/gpt-oss-120b": "gpt-oss-120b",
    }
    rows = []
    for path in sorted((REPO_ROOT / "results" / "full_run").glob("*.eval")):
        log = read_eval_log(str(path))
        variant = "single_turn" if "single-turn" in log.eval.task else "multi_turn"
        model = MODEL_SHORT_NAMES.get(log.eval.model, log.eval.model)
        for sample in log.samples or []:
            score = sample.scores.get("refusal_judge") if sample.scores else None
            if score is not None:
                rows.append({"model": model, "variant": variant, "label": score.value})
    df = pd.DataFrame(rows)

    bars = [(m, v) for m in MODEL_ORDER for v in ("single_turn", "multi_turn")]
    refused = []
    partial = []
    complied = []
    for model, variant in bars:
        group = df[(df["model"] == model) & (df["variant"] == variant)]["label"]
        n = len(group)
        refused.append((group == "REFUSED").sum() / n * 100)
        partial.append((group == "PARTIAL").sum() / n * 100)
        complied.append((group == "COMPLIED").sum() / n * 100)

    x = np.arange(len(bars))
    fig, ax = plt.subplots(figsize=(9, 5.5), facecolor=SURFACE)
    _style_axes(ax)

    ax.bar(x, refused, width=0.6, color=BLUE, label="REFUSED", zorder=3)
    ax.bar(x, partial, width=0.6, bottom=refused, color=ORANGE, label="PARTIAL", zorder=3)
    bottom2 = [r + p for r, p in zip(refused, partial)]
    ax.bar(x, complied, width=0.6, bottom=bottom2, color=AQUA, label="COMPLIED", zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{m}\n{v}" for m, v in bars], fontsize=8, color=INK_SECONDARY)
    ax.set_ylabel("Share of samples (%)", color=INK_SECONDARY, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_title(
        "Judge label distribution by model and variant (n=15 per bar)",
        color=INK_PRIMARY,
        fontsize=12,
        loc="left",
        pad=14,
    )
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=3,
        frameon=False,
        labelcolor=INK_SECONDARY,
        fontsize=9,
    )
    fig.tight_layout()
    out = CHARTS_DIR / "refusal_by_model_variant.png"
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print(f"wrote {out}")


def chart_delta_by_category() -> None:
    """Grouped bar: COMPLIED rate delta (multi - single) per category, per model, with CI."""
    df = pd.read_csv(REPO_ROOT / "results" / "bootstrap.csv")
    model_colors = {MODEL_ORDER[0]: BLUE, MODEL_ORDER[1]: ORANGE, MODEL_ORDER[2]: AQUA}

    x = np.arange(len(CATEGORY_ORDER))
    width = 0.25
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=SURFACE)
    _style_axes(ax)

    for i, model in enumerate(MODEL_ORDER):
        sub = df[df["model"] == model].set_index("category").reindex(CATEGORY_ORDER)
        offsets = x + (i - 1) * width
        deltas = sub["complied_rate_delta"].to_numpy()
        lo = sub["complied_rate_delta_ci_low"].to_numpy()
        hi = sub["complied_rate_delta_ci_high"].to_numpy()
        yerr = np.vstack([deltas - lo, hi - deltas])
        ax.bar(
            offsets,
            deltas,
            width=width,
            color=model_colors[model],
            label=model,
            zorder=3,
            yerr=yerr,
            capsize=3,
            error_kw={"ecolor": INK_MUTED, "elinewidth": 1, "zorder": 4},
        )

    ax.axhline(0, color=BASELINE, linewidth=1, zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(CATEGORY_ORDER, fontsize=9, color=INK_SECONDARY)
    ax.set_ylabel("COMPLIED rate delta (multi turn - single turn)", color=INK_SECONDARY, fontsize=10)
    ax.set_ylim(-1.1, 1.1)
    ax.set_title(
        "Compliance escalation by ATT&CK category (n=3 chains per bar, bootstrap 95% CI)",
        color=INK_PRIMARY,
        fontsize=12,
        loc="left",
        pad=14,
    )
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=3,
        frameon=False,
        labelcolor=INK_SECONDARY,
        fontsize=9,
    )
    fig.tight_layout()
    out = CHARTS_DIR / "delta_by_category.png"
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    chart_refusal_by_model_variant()
    chart_delta_by_category()
