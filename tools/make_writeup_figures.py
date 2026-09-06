"""Figures for the Kaggle strategy writeup media gallery (light mode, PNG).

Palette/tokens follow the validated reference instance of the dataviz method:
slot-1 blue #2a78d6, slot-2 orange #eb6834 (adjacent-pair CVD-safe order),
ink/grid/axis tokens from the chrome table.
"""

from pathlib import Path

import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[1] / "reports" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"
ORANGE = "#eb6834"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "Arial"],
    "text.color": INK,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK2,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "figure.dpi": 200,
})


def style_ax(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(length=0)


def fig_trajectory():
    # (version, ladder mu, annotation or None); provisional = still converging
    pts = [
        ("V4", 650.2, None, False),
        ("V6", 683.7, "heuristic core", False),
        ("V12", 669.6, None, False),
        ("V17", 679.9, "C++ MCTS", False),
        ("V18", 506.0, "abort bug", False),
        ("V19", 674.0, "leader deck", False),
        ("V20", 691.0, "+ learned eval  691", False),
        ("V23", 595.0, "self-play circularity", False),
        ("V24", 666.0, "deep tree", False),
        ("V25", 610.0, None, True),
        ("V26", 613.0, "final pair*", True),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    fig.patch.set_facecolor(SURFACE)
    style_ax(ax)
    x = range(len(pts))
    y = [p[1] for p in pts]
    ax.plot(x, y, color=BLUE, linewidth=2, zorder=2)
    solid = [i for i, p in enumerate(pts) if not p[3]]
    prov = [i for i, p in enumerate(pts) if p[3]]
    ax.scatter([i for i in solid], [y[i] for i in solid], s=64, color=BLUE, zorder=3)
    ax.scatter([i for i in prov], [y[i] for i in prov], s=64, facecolor=SURFACE,
               edgecolor=BLUE, linewidth=2, zorder=3)
    for i, (v, mu, note, _) in enumerate(pts):
        if note:
            above = mu >= 660
            ax.annotate(note, (i, mu), textcoords="offset points",
                        xytext=(0, 12 if above else -18), ha="center",
                        fontsize=8.5, color=INK2,
                        fontweight="bold" if v == "V20" else "normal")
    ax.set_xticks(list(x), [p[0] for p in pts])
    ax.set_ylim(480, 730)
    ax.set_ylabel("ladder skill rating (μ)")
    ax.set_title("Five days, 27 agent versions: ladder trajectory of every rated submission",
                 fontsize=11, color=INK, loc="left", pad=14)
    ax.text(0, -0.16, "* V25/V26 still converging (final ratings ~Aug 31). "
            "Unlabeled failures V9–V11 (<600) omitted — no converged rating recorded.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "fig1_rating_trajectory.png", facecolor=SURFACE, bbox_inches="tight")


def fig_auc_dumbbell():
    tiers = ["weak", "mid", "strong", "ALL"]
    v4 = [0.7403, 0.7250, 0.7932, 0.7511]
    v1 = [0.7138, 0.7167, 0.7812, 0.7358]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    fig.patch.set_facecolor(SURFACE)
    style_ax(ax)
    ax.xaxis.grid(True)
    ax.yaxis.grid(False)
    ypos = list(range(len(tiers)))[::-1]
    for yy, a, b in zip(ypos, v4, v1):
        ax.plot([b, a], [yy, yy], color=AXIS, linewidth=1.5, zorder=2)
    ax.scatter(v1, ypos, s=80, color=ORANGE, zorder=3, label="B1v1 — leaders-only data")
    ax.scatter(v4, ypos, s=80, color=BLUE, zorder=3, label="B1v4 — tier-stratified data")
    for yy, a, b in zip(ypos, v4, v1):
        ax.annotate(f"{a:.3f}", (a, yy), textcoords="offset points", xytext=(8, -3),
                    fontsize=8.5, color=INK2)
        ax.annotate(f"{b:.3f}", (b, yy), textcoords="offset points", xytext=(-8, -3),
                    fontsize=8.5, color=INK2, ha="right")
    ax.set_yticks(ypos, tiers)
    ax.tick_params(axis="y", colors=INK2)
    ax.set_xlim(0.69, 0.82)
    ax.set_xlabel("P(win) AUC on held-out real-pool games (52,961 states)")
    ax.set_title("Stratified training data beats leaders-only on every opponent tier",
                 fontsize=11, color=INK, loc="left", pad=10)
    ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(OUT / "fig2_auc_by_tier.png", facecolor=SURFACE, bbox_inches="tight")


if __name__ == "__main__":
    fig_trajectory()
    fig_auc_dumbbell()
    print("wrote", *[p.name for p in sorted(OUT.glob("*.png"))])
