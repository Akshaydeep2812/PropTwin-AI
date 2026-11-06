import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """All metrics are in currency units on held-out data, except the unitless R² and MAPE."""
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(root_mean_squared_error(actual, predicted)),
        "r2": float(r2_score(actual, predicted)),
        "mape_pct": float(np.mean(np.abs((actual - predicted) / actual)) * 100),
    }


def conformal_quantile(validation_log_residuals: np.ndarray, coverage: float) -> float:
    """Split conformal radius with the finite-sample correction, in log-price space."""
    size = len(validation_log_residuals)
    level = min(1.0, np.ceil((size + 1) * coverage) / size)
    return float(np.quantile(np.abs(validation_log_residuals), level, method="higher"))


def interval_coverage(actual: np.ndarray, predicted: np.ndarray, radius: float) -> float:
    lower, upper = predicted * np.exp(-radius), predicted * np.exp(radius)
    return float(np.mean((actual >= lower) & (actual <= upper)))


