"""Research-only exhibition video measurement and ranking contract.

Nothing in this package may change Android BUY/SKIP or Model A predictions.
"""

from .scoring import evaluate_race

__all__ = ["evaluate_race"]
