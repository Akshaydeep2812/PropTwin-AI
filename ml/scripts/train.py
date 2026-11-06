"""Trains, evaluates and saves a candidate model. Usage: python ml/scripts/train.py [--data PATH] [--synthetic | --real]

Output is an immutable directory under ml/artifacts/. Nothing here promotes a model; an admin does that after review.
"""

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "backend")]

from app.ml.features import ALL_FEATURES, SCHEMA_VERSION  # noqa: E402
from ml.evaluation.metrics import conformal_quantile, interval_coverage, regression_metrics  # noqa: E402
from ml.models.trainer import TrainConfig, locality_median_baseline, ridge_baseline, train_mlp  # noqa: E402
from ml.preprocessing.pipeline import build_preprocessor, clean, load_dataset, temporal_split, to_feature_frame, to_matrix  # noqa: E402

COVERAGE = 0.9


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=REPO_ROOT / "ml" / "data" / "synthetic_transactions.csv")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "ml" / "artifacts")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-epochs", type=int, default=200)
    parser.add_argument("--version", default=None, help="Defaults to a UTC timestamp plus the dataset hash.")
    data_kind = parser.add_mutually_exclusive_group()
    data_kind.add_argument("--synthetic", dest="synthetic", action="store_true", default=None)
    data_kind.add_argument("--real", dest="synthetic", action="store_false")
    args = parser.parse_args()

    raw = load_dataset(args.data)
    if args.synthetic is None:
        # Unlabelled data is treated as synthetic unless the operator explicitly vouches for it.
        args.synthetic = bool(raw["is_synthetic"].all()) if "is_synthetic" in raw else True
    cleaned, cleaning_report = clean(raw)
    split = temporal_split(cleaned)
    print(f"cleaning: {cleaning_report}")
    print(f"split ({split.strategy}): train={len(split.train)} validation={len(split.validation)} test={len(split.test)}")
    print(f"test period: {split.test['transaction_date'].min().date()} to {split.test['transaction_date'].max().date()}")

    train_features, val_features, test_features = map(to_feature_frame, (split.train, split.validation, split.test))
    preprocessor = build_preprocessor().fit(train_features)
    train_x, val_x, test_x = (to_matrix(preprocessor, frame) for frame in (train_features, val_features, test_features))

    train_log = np.log(split.train["sale_price"].to_numpy(dtype=float))
    val_log = np.log(split.validation["sale_price"].to_numpy(dtype=float))
    test_actual = split.test["sale_price"].to_numpy(dtype=float)
    target_mean, target_std = float(train_log.mean()), float(train_log.std())

    config = TrainConfig(seed=args.seed, max_epochs=args.max_epochs)
    model, training = train_mlp(
        train_x,
        ((train_log - target_mean) / target_std).astype(np.float32),
        val_x,
        ((val_log - target_mean) / target_std).astype(np.float32),
        config,
    )

    def mlp_log_prediction(matrix: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            return model(torch.from_numpy(matrix)).numpy().astype(float) * target_std + target_mean

    ridge = ridge_baseline(train_x, train_log, args.seed)
    test_prediction = np.exp(mlp_log_prediction(test_x))
    results = {
        "locality_median_baseline": regression_metrics(test_actual, locality_median_baseline(split.train, split.test)),
        "ridge_baseline": regression_metrics(test_actual, np.exp(ridge.predict(test_x))),
        "pytorch_mlp": regression_metrics(test_actual, test_prediction),
    }
    best_baseline = min(("locality_median_baseline", "ridge_baseline"), key=lambda name: results[name]["mae"])
    beats_baseline = results["pytorch_mlp"]["mae"] < results[best_baseline]["mae"]

    radius = conformal_quantile(val_log - mlp_log_prediction(val_x), COVERAGE)
    coverage_on_test = interval_coverage(test_actual, test_prediction, radius)

    print(json.dumps(results, indent=2))
    print(f"best baseline: {best_baseline}; MLP beats it on held-out MAE: {beats_baseline}")
    print(f"{COVERAGE:.0%} interval: radius={radius:.4f} (log), empirical test coverage={coverage_on_test:.3f}")

    data_hash = sha256_file(args.data)
    now = datetime.now(timezone.utc)
    version = args.version or f"{now:%Y%m%dT%H%M%SZ}-{data_hash[:8]}"
    directory = args.output / version
    if directory.exists():
        print(f"Refusing to overwrite existing artifact {directory}. Artifacts are immutable.", file=sys.stderr)
        return 1
    directory.mkdir(parents=True)

    joblib.dump(preprocessor, directory / "preprocessor.joblib")
    torch.save(model.state_dict(), directory / "model.pt")
    metrics = {
        "held_out_test": results,
        "best_baseline": best_baseline,
        "beats_baseline": bool(beats_baseline),
        "interval": {"nominal_coverage": COVERAGE, "empirical_test_coverage": coverage_on_test, "log_radius": radius, "method": "split_conformal"},
        "training": training,
        "cleaning": cleaning_report,
        "split": {
            "strategy": split.strategy,
            "train_rows": len(split.train),
            "validation_rows": len(split.validation),
            "test_rows": len(split.test),
            "test_start": str(split.test["transaction_date"].min().date()),
            "test_end": str(split.test["transaction_date"].max().date()),
        },
    }
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    # Medians and modes of the training rows are the reference point for valuation factors.
    reference = {column: _reference_value(train_features[column]) for column in ALL_FEATURES}
    manifest = {
        "version": version,
        "feature_schema_version": SCHEMA_VERSION,
        "trained_at": now.isoformat(),
        "trained_on_synthetic_data": bool(args.synthetic),
        "dataset": {"path": args.data.name, "sha256": data_hash},
        "model": {"input_dim": int(train_x.shape[1]), "hidden_layers": list(config.hidden_layers), "dropout": config.dropout},
        "target": {"transform": "log", "mean": target_mean, "std": target_std},
        "interval": {"nominal_coverage": COVERAGE, "log_radius": radius},
        "reference_features": reference,
        "supported_ranges": {
            "built_up_area_sqft": [float(train_features["built_up_area_sqft"].quantile(0.005)), float(train_features["built_up_area_sqft"].quantile(0.995))],
            "market_index": [float(train_features["market_index"].min()), float(train_features["market_index"].max())],
            "localities": sorted(str(item) for item in train_features["locality"].dropna().unique()),
        },
        "training_log_price_sample": [float(item) for item in np.quantile(train_log, np.linspace(0, 1, 201))],
        "config": asdict(config),
        "libraries": {"python": platform.python_version(), "torch": torch.__version__, "scikit-learn": sklearn.__version__, "numpy": np.__version__},
        "files": {name: sha256_file(directory / name) for name in ("model.pt", "preprocessor.joblib", "metrics.json")},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved candidate artifact: {directory}")
    if args.synthetic:
        print("NOTE: trained on SYNTHETIC data. These metrics do not describe real-market performance.")
    return 0


def _reference_value(series):
    values = series.dropna()
    if values.empty:
        return None
    if series.dtype == object:
        return str(values.mode().iloc[0])
    return float(values.median())


if __name__ == "__main__":
    raise SystemExit(main())
