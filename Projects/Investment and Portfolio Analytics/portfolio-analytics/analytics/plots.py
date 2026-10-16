"""Matplotlib charts. Colours follow a validated categorical order (blue, orange, aqua)
and a blue-orange diverging scale with a neutral midpoint for correlations."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e6e5e1"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
DIVERGING = LinearSegmentedColormap.from_list(
    "bo", ["#256abf", "#9ec5f4", "#f1f0ec", "#f4a882", "#c9501f"]
)

DISCLAIMER = "Historical results; not a guarantee of future performance."


def _style(ax, title, subtitle=None):
    fig = ax.figure
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", color=INK, fontsize=13, fontweight="bold", pad=22 if subtitle else 12)
    if subtitle:
        ax.text(0, 1.03, subtitle, transform=ax.transAxes, color=INK2, fontsize=9)


def _footer(fig, note=None):
    text = DISCLAIMER + (f"  {note}" if note else "")
    fig.text(0.01, 0.01, text, color=INK2, fontsize=7.5)


def growth_chart(series: dict[str, pd.Series], path, note=None):
    colors = [BLUE, ORANGE, AQUA]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    _style(ax, "Growth of 100 invested", "Portfolio vs equal weight vs benchmark, monthly rebalancing")
    for (name, s), c in zip(series.items(), colors):
        ax.plot(s.index, s.values, color=c, linewidth=2, label=name)
        ax.annotate(name, (s.index[-1], s.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    color=INK, fontsize=8.5, va="center")
    ax.legend(frameon=False, loc="upper left", fontsize=9, labelcolor=INK2)
    ax.margins(x=0.01)
    fig.subplots_adjust(right=0.82, bottom=0.12)
    _footer(fig, note)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def drawdown_chart(dd: pd.Series, path, label="Portfolio", note=None):
    fig, ax = plt.subplots(figsize=(9, 3.8))
    _style(ax, f"{label} drawdown", "Decline from the previous peak")
    ax.fill_between(dd.index, dd.values * 100, 0, color=BLUE, alpha=0.25, linewidth=0)
    ax.plot(dd.index, dd.values * 100, color=BLUE, linewidth=1.6)
    trough = dd.idxmin()
    ax.scatter([trough], [dd.min() * 100], s=40, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.annotate(f"Worst: {dd.min():.1%}", (trough, dd.min() * 100), xytext=(8, -4),
                textcoords="offset points", color=INK, fontsize=9)
    ax.set_ylabel("%", color=INK2, fontsize=9)
    fig.subplots_adjust(bottom=0.14, top=0.84)
    _footer(fig, note)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def correlation_heatmap(corr: pd.DataFrame, path, note=None):
    n = len(corr)
    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor(SURFACE)
    im = ax.imshow(corr.values, cmap=DIVERGING, vmin=-1, vmax=1)
    ax.set_xticks(range(n), corr.columns, color=INK2, fontsize=9)
    ax.set_yticks(range(n), corr.index, color=INK2, fontsize=9)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center",
                    fontsize=8, color=INK)
    ax.set_title("Correlation of daily returns", loc="left", color=INK, fontsize=13, fontweight="bold")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=INK2, labelsize=8, length=0)
    _footer(fig, note)
    fig.savefig(path, dpi=160, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def frontier_chart(cloud: pd.DataFrame, frontier: pd.DataFrame, marks: dict[str, tuple], path, note=None):
    fig, ax = plt.subplots(figsize=(9, 5))
    _style(ax, "Risk vs return, long-only portfolios", "Efficient frontier from historical estimates")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.scatter(cloud["volatility"] * 100, cloud["return"] * 100, s=6, color="#c8c7c1", alpha=0.6,
               linewidth=0, label="Random portfolios")
    ax.plot(frontier["volatility"] * 100, frontier["return"] * 100, color=BLUE, linewidth=2.2,
            label="Efficient frontier")
    for (name, (vol, ret)), c in zip(marks.items(), [ORANGE, AQUA, INK]):
        ax.scatter([vol * 100], [ret * 100], s=70, color=c, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.annotate(name, (vol * 100, ret * 100), xytext=(8, 6), textcoords="offset points",
                    color=INK, fontsize=9)
    ax.set_xlabel("Annualised volatility (%)", color=INK2, fontsize=9)
    ax.set_ylabel("Annualised return (%)", color=INK2, fontsize=9)
    ax.legend(frameon=False, loc="lower right", fontsize=9, labelcolor=INK2)
    fig.subplots_adjust(bottom=0.16)
    _footer(fig, note)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def weights_chart(weights: dict[str, pd.Series], path, note=None):
    """Grouped horizontal bars: one group per asset, one bar per strategy."""
    colors = [BLUE, ORANGE, AQUA]
    df = pd.DataFrame(weights).sort_index(ascending=False)
    fig, ax = plt.subplots(figsize=(8, 5))
    _style(ax, "Allocation by strategy", "Long-only, max 40% per asset")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    h = 0.8 / df.shape[1]
    y = np.arange(len(df))
    for k, (col, c) in enumerate(zip(df.columns, colors)):
        ax.barh(y + k * h, df[col] * 100, height=h - 0.04, color=c, label=col)
    ax.set_yticks(y + h * (df.shape[1] - 1) / 2, df.index)
    ax.set_xlabel("Weight (%)", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper right")
    fig.subplots_adjust(bottom=0.14)
    _footer(fig, note)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
