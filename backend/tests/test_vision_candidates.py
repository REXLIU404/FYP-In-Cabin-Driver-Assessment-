"""Task 10A: manifest-driven vision candidates (plan docs/plans/2026-10-25-task-10a-candidate-integration.md,
corrections C-1..C-8 in docs/plans/2026-10-26-task-10a-analysis-and-collaboration.zh.md).

The stable MobileNetV3 stays the default; a candidate is selected by DRA_ACTIVE_VISION at process
start. Synthetic packages (tmp_path) test the loader's contract and always run; tests that need the
real copied packages under ml/outputs/candidates/ carry the ``candidates`` marker (deselected unless
``-m candidates``, see conftest)."""
from app.config import Settings


def test_default_active_vision_is_stable():
    # The class defaults: no instance is built, no environment variable is read.
    assert Settings.model_fields["active_vision"].default == "stable"
    assert Settings.model_fields["vision_candidates_root"].default.name == "candidates"
    assert Settings.model_fields["vision_candidates_root"].default.parent == Settings.model_fields["model_root"].default
