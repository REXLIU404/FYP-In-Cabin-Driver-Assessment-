"""Choose the binary working point on the validation split.

The risk score is ``P_distraction = 1 - P(c0)``; the zero-shot protocol used a fixed
0.5, which on domain-shifted input flags almost every safe frame. Because the loss is
NOT class-weighted here, the threshold is the only lever - and it is fitted on val
(gB_10) only, never on the test subjects.
"""
from __future__ import annotations


def _rates(threshold: float, probs: list[float], labels: list[int]) -> tuple[float, float, float]:
    positives = [p >= threshold for p in probs]
    tp = sum(1 for p, y in zip(positives, labels) if p and y == 1)
    fp = sum(1 for p, y in zip(positives, labels) if p and y == 0)
    fn = sum(1 for p, y in zip(positives, labels) if not p and y == 1)
    tn = sum(1 for p, y in zip(positives, labels) if not p and y == 0)
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    return tpr, fpr, precision


def select_threshold(distraction: list[float], labels: list[int],
                     max_fpr: float = 0.10) -> dict:
    """Lowest threshold whose FPR <= ``max_fpr``, maximising recall.

    When no threshold meets the budget the function returns the point with the smallest
    FPR (ties broken by higher recall) and sets ``feasible=False`` - callers must report
    that rather than pretending the budget was met.
    """
    if len(distraction) != len(labels):
        raise ValueError("distraction and labels must be the same length")
    if not distraction:
        raise ValueError("no samples")
    candidates = sorted(set(distraction) | {1.0})
    rows = []
    for threshold in candidates:
        recall, fpr, precision = _rates(threshold, distraction, labels)
        rows.append({"threshold": threshold, "recall": recall, "fpr": fpr,
                     "precision": precision,
                     "balanced_accuracy": (recall + (1 - fpr)) / 2})
    feasible = [r for r in rows if r["fpr"] <= max_fpr]
    if feasible:
        chosen = min(feasible, key=lambda r: (r["threshold"], -r["recall"]))
    else:
        chosen = min(rows, key=lambda r: (r["fpr"], -r["recall"]))
    return {**chosen, "feasible": bool(feasible), "max_fpr": max_fpr}
