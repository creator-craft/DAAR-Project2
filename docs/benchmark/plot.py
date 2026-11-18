"""Charts of the performance benchmark, for the report.

Reads indexing.csv and queries.csv (produced by `python manage.py benchmark`) from the
input directory and writes one PDF (for LaTeX) and one PNG (for slides) per figure,
plus summary.md, the same numbers as tables.

    pip install matplotlib
    python docs/benchmark/plot.py [docs/benchmark]
"""

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK, INK_MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"

PHASES = {
    "parse_s": "Parsing",
    "postings_s": "Postings",
    "other_s": "Vocab. & other",
    "jaccard_s": "Jaccard",
    "neighbours_s": "Neighbours",
    "pagerank_s": "PageRank",
}
HALF_WIDTH = (3.2, 2.5)  # two figures side by side on an A4 page
MODES = {"keyword": "Keyword", "regex": "RegEx"}
RANKINGS = {"frequency": "Occurrences", "pagerank": "PageRank"}

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
THOUSANDS = FuncFormatter(lambda value, _: f"{value:,.0f}")


def legend_below(axis: plt.Axes, columns: int) -> None:
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=columns,
                fontsize=7.5, handlelength=1.5, columnspacing=1)


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as file:
        return list(csv.DictReader(file))


def save(figure: plt.Figure, output: Path, name: str) -> None:
    for extension in ("pdf", "png"):
        figure.savefig(output / f"{name}.{extension}", dpi=200)
    plt.close(figure)
    print(f"  {name}.pdf / .png")


def plot_indexing_phases(rows: list[dict[str, str]], output: Path) -> None:
    labels = [f"{int(row['books']):,}" for row in rows]
    figure, axis = plt.subplots(figsize=HALF_WIDTH)
    bottom = [0.0] * len(rows)
    for color, (column, label) in zip(SERIES, PHASES.items()):
        values = [float(row[column]) for row in rows]
        axis.bar(labels, values, 0.6, bottom=bottom, color=color, label=label,
                 edgecolor=SURFACE, linewidth=1)
        bottom = [b + v for b, v in zip(bottom, values)]
    for x, total in enumerate(bottom):
        axis.annotate(f"{total:.0f} s", (x, total), xytext=(0, 3),
                      textcoords="offset points", ha="center", color=INK)
    axis.set(title="Index build time by phase", xlabel="Books in the sample",
             ylabel="Seconds", ylim=(0, max(bottom) * 1.12))
    axis.grid(axis="x", visible=False)
    legend_below(axis, 3)
    save(figure, output, "indexing_phases")


def plot_graph_scaling(rows: list[dict[str, str]], output: Path) -> None:
    books = [int(row["books"]) for row in rows]
    figure, axis = plt.subplots(figsize=HALF_WIDTH)
    for color, column in zip(SERIES[3:], ("jaccard_s", "neighbours_s", "pagerank_s")):
        seconds = [max(float(row[column]), 1e-4) for row in rows]
        axis.plot(books, seconds, color=color, linewidth=2, marker="o",
                  markersize=5, label=PHASES[column])
    # Reference slope: quadratic growth through the last Jaccard measurement
    last = max(float(rows[-1]["jaccard_s"]), 1e-4)
    axis.plot(books, [last * (n / books[-1]) ** 2 for n in books], color=INK_MUTED,
              linewidth=1, linestyle="--", label="O(n²) reference")
    axis.set(xscale="log", yscale="log", title="Graph construction cost",
             xlabel="Books in the sample (log)", ylabel="Seconds (log)")
    axis.xaxis.set_major_formatter(THOUSANDS)
    legend_below(axis, 2)
    save(figure, output, "graph_scaling")


def plot_index_growth(rows: list[dict[str, str]], output: Path) -> None:
    labels = [f"{int(row['books']):,}" for row in rows]
    panels = [("terms", "Distinct terms"), ("postings", "Postings"), ("db_mb", "Database (MB)")]
    figure, axes = plt.subplots(1, 3, figsize=(6.4, 2.6))
    for axis, (column, title) in zip(axes, panels):
        axis.bar(labels, [float(row[column]) for row in rows], 0.6, color=SERIES[0])
        axis.set(title=title, xlabel="Books")
        axis.grid(axis="x", visible=False)
        axis.yaxis.set_major_formatter(THOUSANDS)
        axis.tick_params(axis="x", labelrotation=45)
    figure.suptitle("Index size", x=0.01, ha="left", fontweight="bold", color=INK)
    figure.tight_layout()
    save(figure, output, "index_growth")


def medians(rows: list[dict[str, str]], keys: tuple[str, ...]) -> dict[tuple[str, ...], float]:
    groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(float(row["ms"]))
    return {key: statistics.median(values) for key, values in groups.items()}


def plot_query_latency(rows: list[dict[str, str]], output: Path) -> None:
    largest = max((row["books"] for row in rows), key=int)
    rows = [row for row in rows if row["books"] == largest]
    queries = list(dict.fromkeys((row["mode"], row["query"]) for row in rows))
    latency = medians(rows, ("mode", "query", "ranking"))
    figure, axis = plt.subplots(figsize=(5.2, 3.2))
    height = 0.38
    for offset, (color, (ranking, label)) in enumerate(zip(SERIES, RANKINGS.items())):
        positions = [index + (offset - 0.5) * height for index in range(len(queries))]
        values = [latency.get((mode, query, ranking), 0) for mode, query in queries]
        axis.barh(positions, values, height, color=color, label=label,
                  edgecolor=SURFACE, linewidth=1)
    axis.set_yticks(range(len(queries)),
                    [f"{MODES[mode]}: {query}" for mode, query in queries])
    axis.invert_yaxis()
    axis.set(xscale="log", xlabel="Median latency (ms, log)",
             title=f"Search latency on {int(largest):,} books")
    axis.grid(axis="y", visible=False)
    axis.legend(title="Ranking", fontsize=8, title_fontsize=8, loc="upper right")
    save(figure, output, "query_latency")


def plot_query_scaling(rows: list[dict[str, str]], output: Path) -> None:
    latency = medians(rows, ("mode", "books"))
    figure, axis = plt.subplots(figsize=(4.8, 2.9))
    for color, (mode, label) in zip(SERIES, MODES.items()):
        points = sorted((int(books), ms) for (m, books), ms in latency.items() if m == mode)
        axis.plot([p[0] for p in points], [p[1] for p in points], color=color,
                  linewidth=2, marker="o", markersize=5, label=label)
        axis.annotate(f"{points[-1][1]:.0f} ms", points[-1], xytext=(6, 0),
                      textcoords="offset points", va="center", color=INK)
    axis.set(yscale="log", title="Median search latency vs corpus size",
             xlabel="Books in the sample", ylabel="Milliseconds (log)")
    axis.xaxis.set_major_formatter(THOUSANDS)
    axis.xaxis.set_major_locator(MultipleLocator(400))
    axis.legend(fontsize=8)
    save(figure, output, "query_scaling")


def plot_latency_histogram(rows: list[dict[str, str]], output: Path) -> None:
    largest = max((row["books"] for row in rows), key=int)
    rows = [row for row in rows if row["books"] == largest]
    values = [float(row["ms"]) for row in rows]
    low, high = min(values), max(values)
    bins = [low * (high / low) ** (step / 30) for step in range(31)]
    figure, axis = plt.subplots(figsize=(4.8, 2.6))
    for color, (mode, label) in zip(SERIES, MODES.items()):
        axis.hist([float(row["ms"]) for row in rows if row["mode"] == mode], bins=bins,
                  color=color, label=label, edgecolor=SURFACE, linewidth=1)
    axis.set(xscale="log", title=f"Distribution of search latencies on {int(largest):,} books",
             xlabel="Latency (ms, log)", ylabel="Requests")
    axis.grid(axis="x", visible=False)
    axis.legend(fontsize=8)
    save(figure, output, "latency_histogram")


def plot_stress(rows: list[dict[str, str]], output: Path) -> None:
    """Throughput and median latency against the number of concurrent clients, side by side"""
    panels = [("throughput", "Throughput", "Requests per second (log)", "stress_throughput"),
              ("p50_ms", "Median latency", "Milliseconds (log)", "stress_latency")]
    for column, title, ylabel, name in panels:
        figure, axis = plt.subplots(figsize=HALF_WIDTH)
        for color, (mode, label) in zip(SERIES, MODES.items()):
            points = [(int(r["clients"]), float(r[column])) for r in rows if r["mode"] == mode]
            axis.plot([p[0] for p in points], [p[1] for p in points], color=color, linewidth=2,
                      marker="o", markersize=5, label=label)
        clients = sorted({int(r["clients"]) for r in rows})
        axis.set(xscale="log", yscale="log", title=title, xlabel="Concurrent clients",
                 ylabel=ylabel)
        axis.set_xticks(clients, [str(c) for c in clients])
        axis.minorticks_off()
        legend_below(axis, 2)
        save(figure, output, name)


def write_summary(indexing: list[dict[str, str]], queries: list[dict[str, str]],
                  output: Path) -> None:
    lines = ["# Benchmark summary", "", "## Index build (seconds)", "",
             "| Books | Words | Terms | Postings | DB (MB) | " + " | ".join(PHASES.values()) + " | Total |",
             "|" + "---:|" * (6 + len(PHASES))]
    for row in indexing:
        lines.append(
            f"| {int(row['books']):,} | {int(row['words']):,} | {int(row['terms']):,} | "
            f"{int(row['postings']):,} | {row['db_mb']} | "
            + " | ".join(f"{float(row[column]):.3f}" for column in PHASES)
            + f" | {float(row['total_s']):.1f} |"
        )
    lines += ["", "## Search latency (median ms)", "",
              "| Books | Mode | Query | Matched terms | Results | " + " | ".join(RANKINGS.values()) + " |",
              "|---:|---|---|---:|---:|---:|---:|"]
    latency = medians(queries, ("books", "mode", "query", "ranking"))
    info = {(r["books"], r["mode"], r["query"]): (r["matched_terms"], r["results"]) for r in queries}
    for (books, mode, query), (matched, results) in info.items():
        cells = " | ".join(f"{latency[(books, mode, query, ranking)]:.1f}" for ranking in RANKINGS)
        escaped = query.replace("|", "\\|")
        lines.append(f"| {int(books):,} | {MODES[mode]} | `{escaped}` | {matched} | {results} | {cells} |")
    (output / "summary.md").write_text("\n".join(lines) + "\n")
    print("  summary.md")


def main() -> None:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    indexing = read_csv(directory / "indexing.csv")
    queries = read_csv(directory / "queries.csv")
    indexing.sort(key=lambda row: int(row["books"]))
    print(f"Writing figures to {directory}")
    plot_indexing_phases(indexing, directory)
    plot_graph_scaling(indexing, directory)
    plot_index_growth(indexing, directory)
    plot_query_latency(queries, directory)
    plot_query_scaling(queries, directory)
    plot_latency_histogram(queries, directory)
    if (directory / "stress.csv").exists():
        plot_stress(read_csv(directory / "stress.csv"), directory)
    write_summary(indexing, queries, directory)


if __name__ == "__main__":
    main()
