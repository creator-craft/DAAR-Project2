"""Stress test of the search API with an increasing number of concurrent clients.

Every request goes through Nginx, as from a browser. For each number of clients, a fixed batch
of requests is sent as fast as the clients can, and the throughput and latency are recorded
in stress.csv. Only the standard library is used.

    python3 docs/benchmark/stress.py [--url http://localhost:8080] [--output docs/benchmark]
"""

import argparse
import csv
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import cycle, islice
from pathlib import Path

# Numbers of concurrent clients, requests per level, and the queries cycled through
# (query, mode, ranking). Beyond 8 clients, RegEx requests exceed the 120 s timeout of Nginx.
WORKLOADS: dict[str, tuple[list[int], int, list[tuple[str, str, str]]]] = {
    "keyword": (
        [1, 2, 4, 8, 16, 32],
        200,
        [
            (query, "keyword", ranking)
            for query in ("the", "telescope", "sargon", "holmes", "detective", "love", "chemistry")
            for ranking in ("frequency", "pagerank")
        ],
    ),
    "regex": (
        [1, 2, 4, 8],
        40,
        [
            (query, "regex", ranking)
            for query in ("sarg.n", "theat(re|er)", "telescop(e|es|ic)", "[a-z]+ism")
            for ranking in ("frequency", "pagerank")
        ],
    ),
}

FIELDS = ["mode", "clients", "requests", "errors", "seconds", "throughput", "p50_ms", "p95_ms"]


def search_url(base: str, query: str, mode: str, ranking: str) -> str:
    parameters = urllib.parse.urlencode({"q": query, "mode": mode, "ranking": ranking})
    return f"{base}/api/search?{parameters}"


def timed_request(url: str) -> tuple[float, bool]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            response.read()
            ok = response.status == 200
    except OSError:
        ok = False
    return (time.perf_counter() - started) * 1000, ok


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(share * (len(ordered) - 1)))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    options = parser.parse_args()

    with open(options.output / "stress.csv", "w", newline="") as file:
        writer = csv.DictWriter(file, FIELDS)
        writer.writeheader()
        for mode, (levels, count, queries) in WORKLOADS.items():
            urls = [search_url(options.url, *query) for query in queries]
            for url in urls:  # warm-up, not recorded
                timed_request(url)
            for clients in levels:
                batch = list(islice(cycle(urls), count))
                started = time.perf_counter()
                with ThreadPoolExecutor(max_workers=clients) as pool:
                    results = list(pool.map(timed_request, batch))
                seconds = time.perf_counter() - started
                latencies = [ms for ms, ok in results if ok]
                row = {
                    "mode": mode,
                    "clients": clients,
                    "requests": count,
                    "errors": sum(not ok for _, ok in results),
                    "seconds": round(seconds, 3),
                    "throughput": round(len(latencies) / seconds, 2),
                    "p50_ms": round(percentile(latencies, 0.5), 1) if latencies else "",
                    "p95_ms": round(percentile(latencies, 0.95), 1) if latencies else "",
                }
                writer.writerow(row)
                file.flush()
                print(
                    f"{mode:7} {clients:2} clients: {row['throughput']:7} req/s, "
                    f"p50 {row['p50_ms']} ms, p95 {row['p95_ms']} ms, {row['errors']} errors"
                )


if __name__ == "__main__":
    main()
