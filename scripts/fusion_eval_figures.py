"""Static report figures for ``scripts/fusion_eval.py`` (matplotlib, Agg, PNG at 200 dpi).

Colours come from the reference data-viz palette: categorical slots 1-3 (validated
all-pairs), a one-hue blue sequential ramp for the agreement heatmap, and text in ink
tokens rather than series colours. Every figure has a CSV next to it as its table view.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")  # categorical slots 1-3
BLUE_RAMP = ("#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b")
DPI = 200

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
    "xtick.color": INK_2, "ytick.color": INK_2, "text.color": INK,
    "font.size": 9, "axes.titlesize": 9, "axes.spines.top": False, "axes.spines.right": False,
})


def _weight_label(w: dict) -> str:
    return f"{w['w_v']:.1f}/{w['w_t']:.1f}"


def _thresholds(ax, low: float, high: float, right_labels: bool) -> None:
    for y in (low, high):
        ax.axhline(y, color=INK_2, linewidth=0.8, linestyle=(0, (3, 3)), zorder=1)
    if right_labels:
        for y, text in ((low / 2, "Low"), ((low + high) / 2, "Medium"), ((high + 100) / 2, "High")):
            ax.text(1.02, y, text, transform=ax.get_yaxis_transform(), color=INK_2,
                    va="center", ha="left", fontsize=8)


def e2_figures(rows: list[dict], protocol: dict, out_dir: Path) -> list[str]:
    weights = protocol["e2"]["weights"]
    strata = protocol["e2"]["strata"]
    low, high = protocol["fixed_runtime"]["threshold_low"], protocol["fixed_runtime"]["threshold_high"]
    names = protocol["operational_reference_policy"]["names"]
    ref_of = {s["id"]: next(r["reference"] for r in rows if r["stratum"] == s["id"]) for s in strata}
    written = []

    # 1. RiskScore per pair, per weight setting, per stratum (small multiples).
    fig, axes = plt.subplots(2, 3, figsize=(9.6, 5.6), sharex=True, sharey=True)
    for ax, stratum in zip(axes.flat, strata):
        for j, _ in enumerate(weights):
            cell = sorted((r for r in rows if r["stratum"] == stratum["id"] and r["weight_index"] == j),
                          key=lambda r: r["pair_id"])
            xs = [j + (i - (len(cell) - 1) / 2) * 0.045 for i in range(len(cell))]
            ax.scatter(xs, [r["RiskScore"] for r in cell], s=14, color=SERIES[0],
                       edgecolors=SURFACE, linewidths=0.6, zorder=3)
            scores = sorted(r["RiskScore"] for r in cell)
            median = (scores[len(scores) // 2] + scores[(len(scores) - 1) // 2]) / 2
            ax.plot([j - 0.3, j + 0.3], [median, median], color=INK, linewidth=1.6, zorder=4,
                    solid_capstyle="round")
        _thresholds(ax, low, high, right_labels=ax in axes[:, -1])
        ax.set_title(f"{stratum['id']}  V {stratum['vision']} / T {stratum['telemetry']}\n"
                     f"reference {ref_of[stratum['id']]}", loc="left")
        ax.set_ylim(-3, 103)
        ax.set_yticks([0, low, high, 100])
        ax.set_xticks(range(len(weights)), [_weight_label(w) for w in weights])
    for ax in axes[:, 0]:
        ax.set_ylabel("RiskScore (0-100)")
    for ax in axes[-1]:
        ax.set_xlabel("fusion weights w_v / w_t")
    fig.suptitle("E2: RiskScore of 10 constructed pairs per stratum under the five Table 9 weights "
                 "(dots = pairs, bar = median)", x=0.01, ha="left", fontsize=10)
    fig.tight_layout(rect=(0, 0, 0.97, 0.96))
    path = out_dir / "e2_scores_by_stratum.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    written.append(path.name)

    # 2. Agreement with the operational reference, stratum x weight.
    grid = [[sum(r["agrees"] for r in rows if r["stratum"] == s["id"] and r["weight_index"] == j)
             for j in range(len(weights))] for s in strata]
    n = protocol["e2"]["pairs_per_stratum"]
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    fig, ax = plt.subplots(figsize=(8.4, 3.9))
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=n, aspect="auto")
    for i, row in enumerate(grid):
        for j, value in enumerate(row):
            ax.text(j, i, f"{value}/{n}", ha="center", va="center", fontsize=9,
                    color=SURFACE if value >= 0.6 * n else INK)
    ax.set_xticks(range(len(weights)), [_weight_label(w) for w in weights])
    ax.set_yticks(range(len(strata)),
                  [f"{s['id']} V-{s['vision']} / T-{s['telemetry']} ({ref_of[s['id']]})" for s in strata])
    ax.set_xlabel("fusion weights w_v / w_t")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    allowed = protocol["operational_reference_policy"]["levels"]
    ax.set_title("E2: pairs agreeing with the pre-declared operational reference\n"
                 f"({names['no_branch_non_safe']} = {'/'.join(allowed['no_branch_non_safe'])}, "
                 f"{names['exactly_one_branch_non_safe']} = {'/'.join(allowed['exactly_one_branch_non_safe'])}, "
                 f"{names['both_branches_non_safe']} = {'/'.join(allowed['both_branches_non_safe'])})",
                 loc="left")
    fig.tight_layout()
    path = out_dir / "e2_reference_agreement.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    written.append(path.name)
    return written


VARIANT_STYLE = {
    "FUSED": ("as declared (both branches vary)", SERIES[0], "-"),
    # Line style is the secondary encoding (slot 3 is below 3:1 on the surface).
    "VISION_HELD_SAFE": ("vision held safe (telemetry varies)", SERIES[1], (0, (5, 2))),
    "TELEMETRY_HELD_SAFE": ("telemetry held Safe (vision varies)", SERIES[2], (0, (1.5, 1.5))),
}


def e5_figure(by_variant: dict[str, list[dict]], manifest: dict, protocol: dict,
              out_dir: Path) -> list[str]:
    low, high = protocol["fixed_runtime"]["threshold_low"], protocol["fixed_runtime"]["threshold_high"]
    severity = {"NORMAL": 0, "CAUTION": 1, "HIGH_ALERT": 2}
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9.6, 5.6), sharex=True,
                                  gridspec_kw={"height_ratios": (3, 1.25)})
    # Drawn widest first, so a line that coincides with another still shows at its edges.
    widths = {"FUSED": 4.0, "VISION_HELD_SAFE": 2.4, "TELEMETRY_HELD_SAFE": 1.6}
    for z, (variant, windows) in enumerate(by_variant.items()):
        label, color, style = VARIANT_STYLE[variant]
        t = [w["meta"]["pos_ms"] / 1000 for w in windows]
        ax.plot(t, [w["RiskScore"] for w in windows], color=color, linewidth=widths[variant],
                linestyle=style, label=label, zorder=3 + z)
        ax2.step(t, [severity[w["AlertSeverity"]] for w in windows], where="post", color=color,
                 linewidth=widths[variant], linestyle=style, zorder=3 + z)
    for a in (ax, ax2):
        for segment in manifest["segments"][1:]:
            a.axvline(segment["start_ms"] / 1000, color=GRID, linewidth=1, zorder=1)
    key = []
    for segment in manifest["segments"]:
        mid = (segment["start_ms"] + segment["duration_ms"] / 2) / 1000
        ax.text(mid, 102, str(segment["index"] + 1), ha="center", va="bottom", fontsize=8, color=INK)
        key.append(f"{segment['index'] + 1} {segment['title']} (V {segment['vision_class']} / "
                   f"T {segment['telemetry_label']})")
    fig.text(0.01, 0.935, "segments:  " + "   ".join(key[:4]) + "\n" + " " * 21 + "   ".join(key[4:]),
             fontsize=7.5, color=INK_2, va="top")
    _thresholds(ax, low, high, right_labels=True)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, low, high, 100])
    ax.set_ylabel("RiskScore (0-100)")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.02, 1, 0), ncol=3, frameon=False, fontsize=8,
              mode="expand")
    ax2.set_yticks([0, 1, 2], ["NORMAL", "CAUTION", "HIGH_ALERT"])
    ax2.set_ylim(-0.3, 2.3)
    ax2.set_ylabel("AlertSeverity")
    ax2.set_xlabel("scenario time (s)")
    ax2.set_xlim(0, manifest["duration_ms"] / 1000)
    fig.suptitle("E5 (light): viva_compact constructed scenario, as declared and with one branch held "
                 "safe (0.5/0.5, 10 windows/s)", x=0.01, ha="left", fontsize=10, y=0.995)
    ax2.grid(axis="y", color=GRID, linewidth=0.6, zorder=0)
    fig.tight_layout(rect=(0, 0, 0.95, 0.88))
    path = out_dir / "e5_timeline.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return [path.name]
