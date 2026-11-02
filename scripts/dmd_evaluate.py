"""Metrics shared by the zero-shot baseline and the adapted model.

Same definitions the zero-shot report used, so the two tables are comparable:
10-class accuracy / macro-F1 / per-class P-R-F1 / confusion matrix, and the binary
``P_distraction = 1 - P(c0)`` view with recall, FPR, rocAUC, prAUC, balanced accuracy,
Brier and 10-bin ECE.
"""
from __future__ import annotations


def multiclass_metrics(y_true: list[int], logits: list[list[float]],
                       num_classes: int = 10) -> dict:
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                 precision_recall_fscore_support)

    preds = [max(range(len(row)), key=lambda i: row[i]) for row in logits]
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, preds, labels=list(range(num_classes)), zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_true, preds)),
        "macro_f1": float(f1_score(y_true, preds, average="macro", zero_division=0)),
        "per_class": {
            f"c{i}": {"precision": float(precision[i]), "recall": float(recall[i]),
                      "f1": float(f1[i]), "support": int(support[i])}
            for i in range(num_classes)
        },
        "confusion_matrix": confusion_matrix(y_true, preds,
                                             labels=list(range(num_classes))).tolist(),
    }


def binary_metrics(y_true: list[int], distraction: list[float],
                   threshold: float) -> dict:
    from sklearn.metrics import (average_precision_score, brier_score_loss,
                                 roc_auc_score)

    positives = [p >= threshold for p in distraction]
    tp = sum(1 for p, y in zip(positives, y_true) if p and y == 1)
    fp = sum(1 for p, y in zip(positives, y_true) if p and y == 0)
    fn = sum(1 for p, y in zip(positives, y_true) if not p and y == 1)
    tn = sum(1 for p, y in zip(positives, y_true) if not p and y == 0)
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    return {
        "threshold": threshold,
        "recall": recall,
        "fpr": fpr,
        "precision": precision,
        "balanced_accuracy": (recall + (1 - fpr)) / 2,
        "roc_auc": float(roc_auc_score(y_true, distraction)),
        "pr_auc": float(average_precision_score(y_true, distraction)),
        "brier": float(brier_score_loss(y_true, distraction)),
        "ece": ece(distraction, y_true),
    }


def ece(probs: list[float], labels: list[int], bins: int = 10) -> float:
    """Expected calibration error of a probability against binary labels."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in zip(probs, labels):
        index = min(bins - 1, int(p * bins))
        buckets[index].append((p, y))
    total = len(probs)
    error = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        confidence = sum(p for p, _ in bucket) / len(bucket)
        accuracy = sum(y for _, y in bucket) / len(bucket)
        error += abs(confidence - accuracy) * len(bucket) / total
    return float(error)
