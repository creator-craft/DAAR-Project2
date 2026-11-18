"""Chart of the relevance test, for the report.

Reads summary.csv and cases.csv (produced by `python manage.py relevance`) from the input
directory and writes precision.pdf / .png, cases.pdf / .png, plus summary.md, the same numbers
as a table. When manual.csv (the team's judgments of the first 5 results of the case studies)
is present, it also writes manual.pdf / .png, and recommendations.pdf / .png from
recommendations_manual.csv (the team's judgments of the first 3 recommendations).

    pip install matplotlib
    python docs/relevance/plot.py [docs/relevance]
"""

import csv
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

SERIES = ["#2a78d6", "#eb6834"]
INK, INK_MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
RANKINGS = {"precision_frequency": "Occurrences", "precision_pagerank": "PageRank"}
GROUPS = {"popular": "Popular topics", "niche": "Niche topics"}

plt.rcParams.update(
    {
        "font.size": 9,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_MUTED,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlecolor": INK,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "legend.frameon": False,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.bbox": "tight",
    }
)


def mean_row(rows: list[dict[str, str]], label: str) -> dict[str, str]:
    columns = [*RANKINGS, "baseline"]
    return {"query": label, **{c: str(statistics.mean(float(r[c]) for r in rows)) for c in columns}}


def plot_precision(rows: list[dict[str, str]], output: Path) -> None:
    lines: list[dict[str, str] | None] = []
    for group, label in GROUPS.items():
        members = [row for row in rows if row["group"] == group]
        lines += [*members, mean_row(members, f"Mean, {label.lower()}"), None]
    lines.pop()

    figure, axis = plt.subplots(figsize=(4.8, 5.2))
    height = 0.36
    positions = range(len(lines))
    for offset, (color, (column, label)) in enumerate(zip(SERIES, RANKINGS.items())):
        axis.barh([p + (offset - 0.5) * height for p in positions],
                  [float(line[column]) if line else 0 for line in lines], height,
                  color=color, label=label, edgecolor=SURFACE, linewidth=1)
    baseline = [(p, float(line["baseline"])) for p, line in zip(positions, lines) if line]
    axis.scatter([b for _, b in baseline], [p for p, _ in baseline], marker="|", s=140,
                 linewidths=2, color=INK, label="Random order", zorder=3)
    axis.set_yticks(list(positions), [line["query"] if line else "" for line in lines])
    for tick, line in zip(axis.get_yticklabels(), lines):
        if line and line["query"].startswith("Mean"):
            tick.set_fontweight("bold")
            tick.set_color(INK)
    axis.tick_params(axis="y", length=0)
    axis.invert_yaxis()
    axis.set(xlim=(0, 1), xlabel="Precision of the first 10 results",
             title="Relevance of the rankings")
    axis.xaxis.set_major_formatter(PercentFormatter(1.0))
    axis.grid(axis="y", visible=False)
    handles, labels = axis.get_legend_handles_labels()
    order = [labels.index(label) for label in (*RANKINGS.values(), "Random order")]
    axis.legend([handles[i] for i in order], [labels[i] for i in order], loc="upper center",
                bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=8)
    for extension in ("pdf", "png"):
        figure.savefig(output / f"precision.{extension}", dpi=200)
    plt.close(figure)
    print("  precision.pdf / .png")


def plot_cases(rows: list[dict[str, str]], output: Path) -> None:
    queries = list(dict.fromkeys(row["query"] for row in rows))
    rankings = {"frequency": ("Occurrences", SERIES[0]), "pagerank": ("PageRank", SERIES[1])}
    top = max(int(row["rank"]) for row in rows)
    figure, axis = plt.subplots(figsize=(4.8, 3.9))
    ticks: list[tuple[float, str]] = []
    for index, query in enumerate(queries):
        for offset, (ranking, (label, color)) in enumerate(rankings.items()):
            y = index * 3 + offset
            ticks.append((y, label))
            line = [row for row in rows if row["query"] == query and row["ranking"] == ranking]
            hits = [int(row["rank"]) for row in line if row["relevant"] == "1"]
            misses = [int(row["rank"]) for row in line if row["relevant"] == "0"]
            axis.scatter(hits, [y] * len(hits), s=55, color=color, zorder=3)
            axis.scatter(misses, [y] * len(misses), s=55, facecolor=SURFACE,
                         edgecolor=INK_MUTED, linewidth=1, zorder=3)
            axis.annotate(f"{len(hits)}/{len(line)}", (top + 0.6, y), va="center", color=INK)
        axis.annotate(query, (0, index * 3 + 0.5), xycoords=("axes fraction", "data"),
                      xytext=(-72, 0), textcoords="offset points", ha="right", va="center",
                      fontweight="bold", color=INK)
    axis.set_yticks([y for y, _ in ticks], [label for _, label in ticks])
    axis.tick_params(axis="y", length=0)
    axis.invert_yaxis()
    axis.set_xticks(range(1, top + 1))
    axis.set(xlim=(0.4, top + 0.6), xlabel="Rank in the results",
             title="Relevant books among the first 10 results")
    axis.grid(axis="y", visible=False)
    legend = [Line2D([], [], marker="o", linestyle="", markersize=7, color=color, label=label)
              for label, color in rankings.values()]
    legend.append(Line2D([], [], marker="o", linestyle="", markersize=7, markerfacecolor=SURFACE,
                         markeredgecolor=INK_MUTED, label="Not relevant"))
    axis.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3,
                fontsize=8)
    for extension in ("pdf", "png"):
        figure.savefig(output / f"cases.{extension}", dpi=200)
    plt.close(figure)
    print("  cases.pdf / .png")


def plot_manual(rows: list[dict[str, str]], output: Path, name: str, title: str,
                ylabel: str, with_labels: bool = False) -> None:
    """Share of relevant books per query, judged by the team and, optionally, by the labels"""
    queries = list(dict.fromkeys(row["query"] for row in rows))
    rankings = {"frequency": "Occurrences", "pagerank": "PageRank"}
    judges = {"manual": "team", "label": "labels"} if with_labels else {"manual": ""}
    groups = [*queries, "overall"]
    figure, axis = plt.subplots(figsize=(6.4, 3.0) if with_labels else (4.8, 2.9))
    bars = [(ranking, color, judge) for ranking, color in zip(rankings, SERIES) for judge in judges]
    width = 0.8 / len(bars)
    for offset, (ranking, color, judge) in enumerate(bars):
        hatched = judge == "label"
        label = f"{rankings[ranking]}, {judges[judge]}" if with_labels else rankings[ranking]
        for index, group in enumerate(groups):
            judged = [row for row in rows if row["ranking"] == ranking
                      and (group == "overall" or row["query"] == group)]
            hits = sum(int(row[judge]) for row in judged)
            x = index + (offset - (len(bars) - 1) / 2) * width
            axis.bar(x, hits / len(judged), width, color=SURFACE if hatched else color,
                     edgecolor=color if hatched else SURFACE, hatch="////" if hatched else None,
                     linewidth=1, label=label if index == 0 else None)
            text = f"{hits / len(judged):.0%}" if group == "overall" else f"{hits}/{len(judged)}"
            axis.annotate(text, (x, hits / len(judged)), xytext=(0, 2),
                          textcoords="offset points", ha="center",
                          fontsize=(6 if group == "overall" else 6.5) if with_labels else 7.5,
                          color=INK)
    axis.set_xticks(range(len(groups)), groups)
    axis.get_xticklabels()[-1].set_fontweight("bold")
    axis.set(ylim=(0, 1.1), ylabel=ylabel, title=title)
    axis.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    axis.yaxis.set_major_formatter(PercentFormatter(1.0))
    axis.grid(axis="x", visible=False)
    if with_labels:
        axis.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4)
    else:
        axis.legend(fontsize=8, loc="upper right")
    for extension in ("pdf", "png"):
        figure.savefig(output / f"{name}.{extension}", dpi=200)
    plt.close(figure)
    print(f"  {name}.pdf / .png")


def write_summary(rows: list[dict[str, str]], output: Path) -> None:
    def pct(value: str) -> str:
        return f"{float(value) * 100:.0f}%"

    lines = [
        "# Relevance summary", "",
        "| Group | Query | Labelled | Matched | Relevant & matched | Random | Occurrences | PageRank "
        "| Recommendations (occurrences) | Recommendations (PageRank) | Recommendations (random) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['group']} | {row['query']} | {row['labelled']} | {row['matched']} | "
            f"{row['relevant_matched']} | {pct(row['baseline'])} | {pct(row['precision_frequency'])} | "
            f"{pct(row['precision_pagerank'])} | {pct(row['recommendations_frequency'])} | "
            f"{pct(row['recommendations_pagerank'])} | {pct(row['recommendations_baseline'])} |"
        )
    (output / "summary.md").write_text("\n".join(lines) + "\n")
    print("  summary.md")


def main() -> None:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    with open(directory / "summary.csv", newline="") as file:
        rows = list(csv.DictReader(file))
    print(f"Writing figures to {directory}")
    plot_precision(rows, directory)
    with open(directory / "cases.csv", newline="") as file:
        plot_cases(list(csv.DictReader(file)), directory)
    manual = [
        ("manual.csv", "manual", "First 5 results", "Relevant among the first 5", True),
        ("recommendations_manual.csv", "recommendations", "First 3 recommendations",
         "Same topic among the first 3", False),
    ]
    for source, name, title, ylabel, with_labels in manual:
        if (directory / source).exists():
            with open(directory / source, newline="") as file:
                plot_manual(list(csv.DictReader(file)), directory, name, title, ylabel, with_labels)
    write_summary(rows, directory)


if __name__ == "__main__":
    main()
