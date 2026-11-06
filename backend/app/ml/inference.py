"""Loads a saved artifact and serves predictions. This module does not touch the database."""

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from threading import Lock
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch

from app.ml.features import ALL_FEATURES, FACTOR_GROUPS
from app.ml.network import ValuationMLP


MAX_ESTIMATE = 1e15


class ModelArtifactError(RuntimeError):
    pass


class EstimateOutOfRangeError(ValueError):
    pass


@dataclass(frozen=True)
class Prediction:
    value: Decimal
    lower: Decimal
    upper: Decimal
    coverage: float
    factors: list[dict[str, str]]


def to_money(value: float) -> Decimal:
    """The single point where a model float becomes a Decimal. Estimates are rounded to whole units."""
    # Far outside its training range a log-price model can extrapolate to absurd or infinite values.
    if not math.isfinite(value) or abs(value) >= MAX_ESTIMATE:
        raise EstimateOutOfRangeError(f"Estimate {value} is outside the representable range.")
    return Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(Decimal("0.01"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_manifest(directory: Path) -> dict:
    path = directory / "manifest.json"
    if not path.is_file():
        raise ModelArtifactError(f"No manifest in {directory.name}.")
    return json.loads(path.read_text(encoding="utf-8"))


class LoadedModel:
    def __init__(self, directory: Path, expected_manifest_sha256: str):
        manifest_bytes = (directory / "manifest.json").read_bytes()
        if sha256_bytes(manifest_bytes) != expected_manifest_sha256:
            raise ModelArtifactError(f"Manifest of {directory.name} does not match its registered digest.")
        self.manifest = json.loads(manifest_bytes)
        # joblib unpickles code, so every file is checked against the digests before anything is loaded.
        for name, digest in self.manifest["files"].items():
            if sha256_bytes((directory / name).read_bytes()) != digest:
                raise ModelArtifactError(f"{name} in {directory.name} failed its integrity check.")
        self.version: str = self.manifest["version"]
        self.preprocessor = joblib.load(directory / "preprocessor.joblib")
        spec = self.manifest["model"]
        self.network = ValuationMLP(spec["input_dim"], spec["hidden_layers"], spec["dropout"])
        self.network.load_state_dict(torch.load(directory / "model.pt", weights_only=True))
        self.network.eval()
        self.reference = self.manifest["reference_features"]
        self.log_radius = float(self.manifest["interval"]["log_radius"])
        self.coverage = float(self.manifest["interval"]["nominal_coverage"])

    def _predict_values(self, rows: list[dict[str, Any]]) -> np.ndarray:
        frame = pd.DataFrame(rows, columns=ALL_FEATURES)
        for column in frame.columns:
            if column in ("property_type", "condition", "locality", "city"):
                frame[column] = frame[column].astype(object).where(frame[column].notna(), None)
            else:
                frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
        matrix = np.asarray(self.preprocessor.transform(frame), dtype=np.float32)
        with torch.no_grad():
            standardized = self.network(torch.from_numpy(matrix)).numpy().astype(float)
        target = self.manifest["target"]
        return np.exp(standardized * target["std"] + target["mean"])

    def predict(self, row: dict[str, Any]) -> Prediction:
        # One row per factor group, each with that group moved to the training reference, plus the row itself.
        # A group with no provided input is left out: its "effect" would only measure the model's reaction to a blank.
        variants = [row]
        groups = [(name, columns) for name, columns in FACTOR_GROUPS.items() if any(row.get(column) is not None for column in columns)]
        for _, columns in groups:
            variants.append({**row, **{column: self.reference.get(column) for column in columns}})
        values = self._predict_values(variants)
        base = float(values[0])
        factors = [
            {"factor": name, "effect": str(to_money(abs(base - float(values[index + 1])))), "direction": "raises" if base >= float(values[index + 1]) else "lowers"}
            for index, (name, _) in enumerate(groups)
        ]
        factors.sort(key=lambda item: Decimal(item["effect"]), reverse=True)
        return Prediction(
            value=to_money(base),
            lower=to_money(base * math.exp(-self.log_radius)),
            upper=to_money(base * math.exp(self.log_radius)),
            coverage=self.coverage,
            factors=factors,
        )


_cache: dict[tuple[str, str], LoadedModel] = {}
_lock = Lock()


def load_cached(directory: Path, manifest_sha256: str) -> LoadedModel:
    key = (str(directory), manifest_sha256)
    with _lock:
        if key not in _cache:
            _cache[key] = LoadedModel(directory, manifest_sha256)
        return _cache[key]


def population_stability_index(reference: np.ndarray, observed: np.ndarray, bins: int = 10) -> float:
    """Common drift score: under 0.1 is usually read as stable and above 0.25 as a large shift."""
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    expected = np.histogram(reference, edges)[0] / len(reference)
    actual = np.histogram(observed, edges)[0] / len(observed)
    expected, actual = np.clip(expected, 1e-4, None), np.clip(actual, 1e-4, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))
