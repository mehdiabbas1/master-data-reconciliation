"""Master data reconciliation for ERP migrations."""

__version__ = "0.1.0"

from .evaluate import evaluate, sweep
from .matching import classify, score_pair
from .pipeline import Result, reconcile

__all__ = ["reconcile", "Result", "score_pair", "classify", "evaluate", "sweep"]
