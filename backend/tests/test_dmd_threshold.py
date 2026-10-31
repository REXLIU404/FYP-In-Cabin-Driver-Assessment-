"""scripts/dmd_threshold.py: pick the working point on val under an FPR budget."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
THRESHOLD = REPO / "scripts" / "dmd_threshold.py"


def _load():
    spec = importlib.util.spec_from_file_location("dmd_threshold", THRESHOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_picks_the_lowest_threshold_meeting_the_fpr_budget():
    t = _load()
    # 4 safe (label 0) and 4 distracted (label 1)
    probs = [0.05, 0.20, 0.35, 0.45, 0.55, 0.70, 0.85, 0.95]
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    # threshold 0.55 -> FPR 0/4, recall 4/4
    result = t.select_threshold(probs, labels, max_fpr=0.0)
    assert result["threshold"] == 0.55
    assert result["fpr"] == 0.0
    assert result["recall"] == 1.0
    assert result["feasible"] is True


def test_zero_budget_costs_recall_when_scores_are_inverted():
    t = _load()
    # safe frames score HIGHER than distracted ones: no useful separation exists
    probs = [0.70, 0.80, 0.30, 0.40]
    labels = [0, 0, 1, 1]
    result = t.select_threshold(probs, labels, max_fpr=0.0)
    assert result["feasible"] is True
    assert result["threshold"] == 1.0     # the only way to keep FPR at 0
    assert result["recall"] == 0.0        # and it costs every distracted frame


def test_reports_the_balanced_accuracy_of_the_chosen_point():
    t = _load()
    probs = [0.1, 0.2, 0.8, 0.9]
    labels = [0, 0, 1, 1]
    result = t.select_threshold(probs, labels, max_fpr=0.0)
    assert result["balanced_accuracy"] == 1.0


EVAL = REPO / "scripts" / "dmd_evaluate.py"


def _load_eval():
    spec = importlib.util.spec_from_file_location("dmd_evaluate", EVAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_multiclass_metrics_on_a_perfect_predictor():
    e = _load_eval()
    logits = [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]]
    y = [0, 1, 2]
    result = e.multiclass_metrics(y, logits)
    assert result["accuracy"] == 1.0
    assert result["macro_f1"] == 1.0
    assert result["confusion_matrix"][0][0] == 1


def test_binary_metrics_reports_fpr_recall_and_auc():
    e = _load_eval()
    y = [0, 0, 1, 1]
    distraction = [0.1, 0.2, 0.8, 0.9]
    result = e.binary_metrics(y, distraction, threshold=0.5)
    assert result["recall"] == 1.0
    assert result["fpr"] == 0.0
    assert result["roc_auc"] == 1.0
    assert result["balanced_accuracy"] == 1.0


def test_ece_is_zero_for_a_perfectly_calibrated_binary_set():
    e = _load_eval()
    probs = [0.0, 0.0, 1.0, 1.0]
    labels = [0, 0, 1, 1]
    assert e.ece(probs, labels, bins=2) == 0.0
