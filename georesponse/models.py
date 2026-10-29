"""A small, auditable damage classifier.

The demo ranking is rule-based, but a pilot needs a model with a reproducible
fit and pinned weights.  This module trains a logistic model on observable
features (change extent, confidence, cloud, SAR agreement, value, population)
and writes the coefficients with the model card.

It is deliberately small: the point is that the customer can audit the numbers,
not that this is a production CNN.  Production swaps in a fine-tuned vision
backbone behind the same ``predict`` interface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FEATURES = ["extent", "confidence", "cloud", "sar", "value", "population", "access"]
DEFAULT_WEIGHTS = np.array([2.7, 2.1, -1.4, 0.9, 0.6, 0.5, 0.8])
DEFAULT_BIAS = -3.2


@dataclass
class DamageClassifier:
    weights: np.ndarray
    bias: float
    feature_names: list[str]
    trained_rows: int = 0
    metrics: dict | None = None

    def _matrix(self, rows: list[dict]) -> np.ndarray:
        return np.array([[float(row.get(name, 0.0)) for name in self.feature_names] for row in rows], dtype=float)

    def predict_proba(self, rows: list[dict]) -> np.ndarray:
        z = self._matrix(rows) @ self.weights + self.bias
        return 1.0 / (1.0 + np.exp(-z))

    def predict(self, rows: list[dict], threshold: float = 0.5) -> list[int]:
        return (self.predict_proba(rows) >= threshold).astype(int).tolist()

    def fit(self, rows: list[dict], labels: list[int], *, epochs: int = 900, lr: float = 0.65, l2: float = 0.002) -> dict:
        X = self._matrix(rows)
        y = np.asarray(labels, dtype=float)
        w = np.zeros(X.shape[1])
        b = 0.0
        for _ in range(epochs):
            z = X @ w + b
            p = 1.0 / (1.0 + np.exp(-z))
            error = p - y
            w -= lr * (X.T @ error / len(y) + l2 * w)
            b -= lr * float(error.mean())
        self.weights = w
        self.bias = b
        self.trained_rows = len(y)
        self.metrics = self.evaluate(rows, labels)
        return self.metrics

    def evaluate(self, rows: list[dict], labels: list[int], threshold: float = 0.5) -> dict:
        p = self.predict_proba(rows)
        pred = (p >= threshold).astype(int)
        y = np.asarray(labels)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum())
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        return {
            "rows": len(y),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(2 * precision * recall / max(1e-9, precision + recall), 3),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "threshold": threshold,
        }

    def to_dict(self) -> dict:
        return {
            "features": self.feature_names,
            "weights": [round(float(v), 8) for v in self.weights],
            "bias": round(float(self.bias), 8),
            "trainedRows": self.trained_rows,
            "metrics": self.metrics,
            "note": "Logistic head over observable change features. Human review mandatory.",
        }

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "DamageClassifier":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            weights=np.array(data["weights"], dtype=float),
            bias=float(data["bias"]),
            feature_names=data["features"],
            trained_rows=data.get("trainedRows", 0),
            metrics=data.get("metrics"),
        )


def default_classifier() -> DamageClassifier:
    return DamageClassifier(weights=DEFAULT_WEIGHTS.copy(), bias=DEFAULT_BIAS, feature_names=list(FEATURES))


def synthetic_training_rows(seed: int = 17, rows: int = 600) -> tuple[list[dict], list[int]]:
    """Deterministic synthetic labels for the demo fit.

    Replace with adjuster-confirmed features in a pilot.  The label rule is a
    transparent combination of extent, confidence, access and SAR agreement so
    the fit can be checked by hand.
    """
    rng = np.random.default_rng(seed)
    X = np.column_stack(
        [
            rng.uniform(0, 1, rows),  # extent
            rng.uniform(0.45, 0.99, rows),  # confidence
            rng.uniform(0, 0.4, rows),  # cloud
            rng.uniform(0, 1, rows),  # sar agreement
            rng.uniform(0, 1, rows),  # value
            rng.uniform(0, 1, rows),  # population
            rng.uniform(0, 1, rows),  # access risk
        ]
    )
    logits = -3.2 + X @ DEFAULT_WEIGHTS + rng.normal(0, 0.45, rows)
    probability = 1 / (1 + np.exp(-logits))
    labels = (rng.uniform(0, 1, rows) < probability).astype(int)
    rows_payload = [{name: float(X[i, j]) for j, name in enumerate(FEATURES)} for i in range(rows)]
    return rows_payload, labels.tolist()


def train_demo_model() -> DamageClassifier:
    rows, labels = synthetic_training_rows()
    model = DamageClassifier(weights=np.zeros(len(FEATURES)), bias=0.0, feature_names=list(FEATURES))
    model.fit(rows, labels)
    return model


def score_site(site: dict, model: DamageClassifier) -> float:
    row = {
        "extent": min(1.0, float(site.get("changeExtentM2", 0)) / 12000),
        "confidence": float(site.get("confidence", 0.5)),
        "cloud": float(site.get("cloud", 0.0)),
        "sar": float(site.get("sarAgreement", 0.5)),
        "value": min(1.0, float(site.get("valueEur", 0)) / 10_000_000),
        "population": min(1.0, float(site.get("population", 0)) / 2500),
        "access": {
            "blocked": 1.0,
            "flooded": 0.9,
            "restricted": 0.7,
            "debris": 0.8,
            "slow": 0.55,
            "clear": 0.15,
        }.get(str(site.get("accessStatus", "clear")), 0.5),
    }
    return float(model.predict_proba([row])[0])


def model_card() -> dict:
    model = train_demo_model()
    return {
        "model": "gr-damage-head-1.0",
        "task": "Damage likelihood from observable change features",
        "features": FEATURES,
        "trainedRows": model.trained_rows,
        "metrics": model.metrics,
        "weights": model.to_dict()["weights"],
        "bias": model.to_dict()["bias"],
        "limitations": [
            "Synthetic training labels in the demo pack; pilot uses adjuster-confirmed labels.",
            "Features are observable, not a replacement for visual evidence.",
            "Never auto-approves a claim; the analyst signs.",
        ],
    }
