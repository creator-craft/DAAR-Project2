from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix, diags

from library.constants import PAGERANK_DAMPING


class Edge(NamedTuple):
    source: int
    target: int
    similarity: float


def jaccard_similarity(incidence: csr_matrix) -> NDArray[np.float64]:
    """Pairwise Jaccard similarity of the rows of a binary book x term matrix"""
    intersections = (incidence @ incidence.T).toarray().astype(np.float64)
    sizes = np.asarray(incidence.sum(axis=1), dtype=np.float64).ravel()
    unions = sizes[:, None] + sizes[None, :] - intersections
    similarity: NDArray[np.float64] = np.divide(
        intersections, unions, out=np.zeros_like(intersections), where=unions > 0
    )
    return similarity


def nearest_edges(similarity: NDArray[np.float64], neighbours: int) -> list[Edge]:
    """Link every book to its `neighbours` most similar books, ignoring disjoint ones"""
    size = similarity.shape[0]
    count = min(neighbours, size - 1)
    if count < 1:
        return []
    scores = similarity.copy()
    np.fill_diagonal(scores, -1.0)
    nearest = np.argpartition(-scores, count - 1, axis=1)[:, :count]
    return [
        Edge(source, int(target), float(similarity[source, target]))
        for source in range(size)
        for target in nearest[source]
        if similarity[source, target] > 0
    ]


def pagerank(
    size: int,
    edges: list[Edge],
    damping: float = PAGERANK_DAMPING,
    tolerance: float = 1e-10,
    max_iterations: int = 200,
) -> NDArray[np.float64]:
    """PageRank by power iteration on the similarity-weighted graph"""
    if size == 0:
        return np.zeros(0)
    weights = csr_matrix(
        (
            [edge.similarity for edge in edges],
            ([edge.source for edge in edges], [edge.target for edge in edges]),
        ),
        shape=(size, size),
    )
    out_weights = np.asarray(weights.sum(axis=1)).ravel()
    out_weights[out_weights == 0] = 1.0
    transition = (diags(1.0 / out_weights) @ weights).T.tocsr()  # type: ignore
    ranks = np.full(size, 1.0 / size)
    for _ in range(max_iterations):
        updated = damping * (transition @ ranks) + (1.0 - damping) / size
        updated /= updated.sum()
        converged = float(np.abs(updated - ranks).sum()) < tolerance
        ranks = updated
        if converged:
            break
    return ranks
