"""Stages 1-10 of the pipeline: load, validate, clean, encode, scale, split without leakage."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.ml.features import ALL_FEATURES, AMENITY_FLAGS, BOOLEAN_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES

TARGET = "sale_price"
DATE_COLUMN = "transaction_date"
REQUIRED_COLUMNS = {
    DATE_COLUMN, TARGET, "property_type", "locality", "city", "built_up_area_sqft", "land_area_sqft", "bedrooms", "bathrooms",
    "construction_year", "floor_number", "total_floors", "condition", "parking_spaces", "amenities", "latitude", "longitude",
    "market_index",
}
NUMERIC_INPUT_COLUMNS = [
    TARGET, "built_up_area_sqft", "land_area_sqft", "bedrooms", "bathrooms", "construction_year", "floor_number", "total_floors",
    "parking_spaces", "latitude", "longitude", "market_index",
]
MIN_PLAUSIBLE_PRICE = 10_000.0
AREA_RANGE = (50.0, 200_000.0)


class DataValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Split:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    strategy: str


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise DataValidationError(f"Dataset not found: {path}")
    return pd.read_csv(path)


def validate_schema(frame: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise DataValidationError(f"Dataset is missing required columns: {sorted(missing)}")
    if frame.empty:
        raise DataValidationError("Dataset has no rows.")


def clean(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Returns the cleaned rows and a count of everything removed, which is stored with the model."""
    validate_schema(frame)
    report = {"rows_in": int(len(frame))}
    out = frame.copy()
    for column in NUMERIC_INPUT_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out[DATE_COLUMN] = pd.to_datetime(out[DATE_COLUMN], errors="coerce")

    before = len(out)
    out = out.drop_duplicates()
    report["duplicates_removed"] = before - len(out)

    before = len(out)
    out = out[out[DATE_COLUMN].notna()]
    report["invalid_dates_removed"] = before - len(out)

    before = len(out)
    out = out[out[TARGET].notna() & (out[TARGET] >= MIN_PLAUSIBLE_PRICE)]
    report["invalid_prices_removed"] = before - len(out)

    before = len(out)
    out = out[out["built_up_area_sqft"].between(*AREA_RANGE)]
    report["invalid_areas_removed"] = before - len(out)

    report["rows_out"] = int(len(out))
    report["missing_values_retained_for_imputation"] = {
        column: int(out[column].isna().sum()) for column in ("condition", "construction_year", "market_index") if out[column].isna().any()
    }
    if out.empty:
        raise DataValidationError("No valid rows remain after cleaning.")
    return out.reset_index(drop=True), report


def to_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Derives model inputs. Age uses the sale year, so a row never sees information from after its own sale."""
    features = pd.DataFrame(index=frame.index)
    for column in ("built_up_area_sqft", "land_area_sqft", "bedrooms", "bathrooms", "floor_number", "total_floors", "parking_spaces", "latitude", "longitude", "market_index"):
        features[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    features["property_age"] = (frame[DATE_COLUMN].dt.year - frame["construction_year"]).clip(lower=0)
    amenity_sets = frame["amenities"].fillna("").astype(str).map(lambda text: {item for item in text.split("|") if item})
    features["amenity_count"] = amenity_sets.map(len).astype(float)
    for name in AMENITY_FLAGS:
        features[f"has_{name}"] = amenity_sets.map(lambda items, name=name: float(name in items))
    for column in CATEGORICAL_FEATURES:
        features[column] = frame[column].astype(object).where(frame[column].notna(), None)
    return features[ALL_FEATURES]


def temporal_split(frame: pd.DataFrame, validation_share: float = 0.15, test_share: float = 0.15) -> Split:
    """Trains on the past and tests on the future. A random split would leak later market conditions into training."""
    ordered = frame.sort_values(DATE_COLUMN, kind="mergesort").reset_index(drop=True)
    size = len(ordered)
    train_end = int(size * (1 - validation_share - test_share))
    validation_end = int(size * (1 - test_share))
    return Split(ordered.iloc[:train_end], ordered.iloc[train_end:validation_end], ordered.iloc[validation_end:], "temporal")


def build_preprocessor() -> ColumnTransformer:
    """Fit on training rows only, so scaling and imputation statistics cannot leak from held-out data."""
    numeric = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler())])
    categorical = Pipeline(
        [
            ("impute", SimpleImputer(strategy="constant", fill_value="unknown", missing_values=None)),
            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        [("numeric", numeric, NUMERIC_FEATURES), ("boolean", "passthrough", BOOLEAN_FEATURES), ("categorical", categorical, CATEGORICAL_FEATURES)],
        sparse_threshold=0.0,
    )


def to_matrix(preprocessor: ColumnTransformer, features: pd.DataFrame) -> np.ndarray:
    return np.asarray(preprocessor.transform(features), dtype=np.float32)
