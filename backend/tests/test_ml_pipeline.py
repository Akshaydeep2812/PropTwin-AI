import json
import shutil
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
import torch

from app.ml.features import ALL_FEATURES, build_feature_row
from app.ml.inference import EstimateOutOfRangeError, LoadedModel, ModelArtifactError, population_stability_index, sha256_bytes, to_money
from ml.evaluation.metrics import conformal_quantile, interval_coverage, regression_metrics
from ml.models.trainer import TrainConfig, locality_median_baseline, train_mlp
from ml.preprocessing.pipeline import DataValidationError, build_preprocessor, clean, temporal_split, to_feature_frame, to_matrix, validate_schema


def _row(**overrides) -> dict:
    row = {
        "transaction_date": "2020-01-15", "sale_price": 5_000_000.0, "property_type": "apartment", "locality": "Riverside", "city": "Sample City",
        "state": "Demo", "built_up_area_sqft": 1000.0, "land_area_sqft": None, "bedrooms": 2, "bathrooms": 2, "construction_year": 2010, "floor_number": 3,
        "total_floors": 10, "condition": "good", "parking_spaces": 1, "amenities": "gym|lift", "latitude": 11.5, "longitude": 71.1, "market_index": 120.0,
    }
    return {**row, **overrides}


def _frame(rows: int = 60) -> pd.DataFrame:
    return pd.DataFrame(
        _row(
            transaction_date=(pd.Timestamp("2018-01-01") + pd.Timedelta(days=30 * index)).date().isoformat(),
            sale_price=3_000_000.0 + 40_000 * index,
            built_up_area_sqft=600.0 + 20 * index,
            locality=["Riverside", "Fort Road"][index % 2],
        )
        for index in range(rows)
    )


def test_schema_validation_names_missing_columns():
    with pytest.raises(DataValidationError, match="sale_price"):
        validate_schema(pd.DataFrame([{"transaction_date": "2020-01-01"}]))


def test_cleaning_removes_each_fault_and_reports_it():
    frame = pd.DataFrame(
        [_row(), _row(), _row(sale_price=-5.0), _row(sale_price=12.5), _row(sale_price="not a number"), _row(built_up_area_sqft=0), _row(transaction_date="garbage"), _row(condition=None, sale_price=4_000_000.0)]
    )
    cleaned, report = clean(frame)
    assert len(cleaned) == 2
    assert report["duplicates_removed"] == 1
    assert report["invalid_prices_removed"] == 3
    assert report["invalid_areas_removed"] == 1
    assert report["invalid_dates_removed"] == 1
    assert report["missing_values_retained_for_imputation"] == {"condition": 1}


def test_cleaning_everything_invalid_raises():
    with pytest.raises(DataValidationError):
        clean(pd.DataFrame([_row(sale_price=-1.0)]))


def test_temporal_split_never_trains_on_the_future():
    cleaned, _ = clean(_frame())
    split = temporal_split(cleaned)
    assert split.strategy == "temporal"
    assert split.train["transaction_date"].max() <= split.validation["transaction_date"].min()
    assert split.validation["transaction_date"].max() <= split.test["transaction_date"].min()
    assert len(split.train) + len(split.validation) + len(split.test) == len(cleaned)


def test_target_is_not_among_features():
    cleaned, _ = clean(_frame())
    columns = set(to_feature_frame(cleaned).columns)
    assert columns == set(ALL_FEATURES)
    assert "sale_price" not in columns and "transaction_date" not in columns


def test_preprocessor_handles_missing_and_unseen_values():
    cleaned, _ = clean(_frame())
    features = to_feature_frame(cleaned)
    preprocessor = build_preprocessor().fit(features)
    odd = features.iloc[[0]].copy()
    odd["locality"] = "Never Seen"
    odd["condition"] = None
    odd["built_up_area_sqft"] = np.nan
    matrix = to_matrix(preprocessor, odd)
    assert matrix.shape[1] == to_matrix(preprocessor, features).shape[1]
    assert np.isfinite(matrix).all()


def test_scaler_statistics_come_only_from_training_rows():
    cleaned, _ = clean(_frame())
    split = temporal_split(cleaned)
    preprocessor = build_preprocessor().fit(to_feature_frame(split.train))
    scaler = preprocessor.named_transformers_["numeric"].named_steps["scale"]
    # built_up_area_sqft is the first numeric column and grows with time in this frame.
    assert scaler.mean_[0] == pytest.approx(split.train["built_up_area_sqft"].mean())
    assert scaler.mean_[0] < cleaned["built_up_area_sqft"].mean()


def test_training_is_reproducible_and_learns():
    generator = np.random.default_rng(0)
    x = generator.normal(size=(400, 4)).astype(np.float32)
    y = (x[:, 0] * 0.8 - x[:, 1] * 0.5).astype(np.float32)
    config = TrainConfig(hidden_layers=(16,), max_epochs=40, patience=40, batch_size=32, dropout=0.0, seed=7)
    first, info = train_mlp(x[:300], y[:300], x[300:], y[300:], config)
    second, _ = train_mlp(x[:300], y[:300], x[300:], y[300:], config)
    assert info["best_validation_mse"] < float(np.var(y[300:])) * 0.3
    for left, right in zip(first.state_dict().values(), second.state_dict().values()):
        assert torch.equal(left, right)


def test_metrics_match_hand_computed_values():
    metrics = regression_metrics(np.array([100.0, 200.0]), np.array([110.0, 190.0]))
    assert metrics["mae"] == pytest.approx(10.0)
    assert metrics["rmse"] == pytest.approx(10.0)
    assert metrics["mape_pct"] == pytest.approx(7.5)
    assert metrics["r2"] == pytest.approx(1 - 200 / 5000)


def test_conformal_interval_reaches_target_on_exchangeable_data():
    generator = np.random.default_rng(1)
    residuals = generator.normal(0, 0.1, 2000)
    radius = conformal_quantile(residuals, 0.9)
    actual = np.exp(generator.normal(0, 0.1, 5000))
    assert interval_coverage(actual, np.ones(5000), radius) == pytest.approx(0.9, abs=0.03)


def test_median_baseline_uses_training_rates_only():
    train = pd.DataFrame({"sale_price": [100.0, 300.0], "built_up_area_sqft": [10.0, 10.0], "locality": ["A", "B"]})
    target = pd.DataFrame({"built_up_area_sqft": [2.0, 2.0], "locality": ["A", "Unknown"]})
    assert locality_median_baseline(train, target).tolist() == [20.0, 40.0]


def test_psi_detects_shift():
    generator = np.random.default_rng(2)
    reference = generator.normal(0, 1, 5000)
    assert population_stability_index(reference, generator.normal(0, 1, 2000)) < 0.1
    assert population_stability_index(reference, generator.normal(2, 1, 2000)) > 0.25


def test_money_conversion_is_decimal_and_rejects_nonfinite():
    assert to_money(1234567.5) == Decimal("1234568.00")
    assert isinstance(to_money(1.0), Decimal)
    for bad in (float("nan"), float("inf"), 1e300):
        with pytest.raises(EstimateOutOfRangeError):
            to_money(bad)


def test_feature_row_computes_age_and_flags():
    row = build_feature_row({"construction_year": 2000, "amenities": ["Gym", "custom"], "built_up_area_sqft": Decimal("900")}, date(2025, 6, 1), 130.0)
    assert row["property_age"] == 25
    assert row["has_gym"] == 1.0 and row["has_pool"] == 0.0 and row["amenity_count"] == 2.0
    assert row["built_up_area_sqft"] == 900.0 and set(ALL_FEATURES) <= set(row)


def _load(directory) -> LoadedModel:
    return LoadedModel(directory, sha256_bytes((directory / "manifest.json").read_bytes()))


def test_artifact_records_versioned_metrics_and_digests(trained_artifacts):
    directory = trained_artifacts / "test-model"
    manifest = json.loads((directory / "manifest.json").read_text())
    metrics = json.loads((directory / "metrics.json").read_text())
    assert manifest["version"] == "test-model" and manifest["trained_on_synthetic_data"] is True
    assert set(manifest["files"]) == {"model.pt", "preprocessor.joblib", "metrics.json"}
    for model_name in ("locality_median_baseline", "ridge_baseline", "pytorch_mlp"):
        assert {"mae", "rmse", "r2"} <= set(metrics["held_out_test"][model_name])
    assert metrics["split"]["strategy"] == "temporal"


def test_loaded_model_predicts_sensibly(trained_artifacts):
    model = _load(trained_artifacts / "test-model")
    raw = {"property_type": "apartment", "built_up_area_sqft": 1000, "locality": "Riverside", "city": "Sample City", "condition": "good", "construction_year": 2015, "bedrooms": 2, "bathrooms": 2, "amenities": ["gym"]}
    small = model.predict(build_feature_row(raw, date(2025, 1, 1), 150.0))
    large = model.predict(build_feature_row({**raw, "built_up_area_sqft": 3000}, date(2025, 1, 1), 150.0))
    assert small.lower < small.value < small.upper
    assert large.value > small.value
    assert small.factors[0]["factor"] and all(Decimal(item["effect"]) >= 0 for item in small.factors)
    assert model.predict(build_feature_row(raw, date(2025, 1, 1), 150.0)).value == small.value


def test_inference_tolerates_missing_inputs(trained_artifacts):
    model = _load(trained_artifacts / "test-model")
    result = model.predict(build_feature_row({"property_type": "plot", "built_up_area_sqft": 2000}, date(2025, 1, 1), None))
    assert result.value > 0


@pytest.mark.parametrize("tampered", ["model.pt", "preprocessor.joblib", "metrics.json"])
def test_tampered_artifact_is_refused_before_loading(trained_artifacts, tmp_path, tampered):
    copy = tmp_path / "copy"
    shutil.copytree(trained_artifacts / "test-model", copy)
    with open(copy / tampered, "ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ModelArtifactError, match="integrity"):
        _load(copy)


def test_tampered_manifest_is_refused(trained_artifacts, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(trained_artifacts / "test-model", copy)
    expected = sha256_bytes((copy / "manifest.json").read_bytes())
    manifest = json.loads((copy / "manifest.json").read_text())
    manifest["target"]["mean"] += 1
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelArtifactError, match="digest"):
        LoadedModel(copy, expected)
