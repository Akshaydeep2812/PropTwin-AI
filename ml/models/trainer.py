"""Stages 11-13: baselines and the PyTorch model, all judged on the same held-out rows."""

import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import Ridge
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from app.ml.network import ValuationMLP


@dataclass(frozen=True)
class TrainConfig:
    hidden_layers: tuple[int, ...] = (256, 128, 64)
    dropout: float = 0.05
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    batch_size: int = 128
    max_epochs: int = 200
    patience: int = 20
    seed: int = 42


def locality_median_baseline(train: pd.DataFrame, target: pd.DataFrame) -> np.ndarray:
    """Median price per square foot by locality, times area: what a simple comparables rule would give."""
    per_sqft = train["sale_price"] / train["built_up_area_sqft"]
    by_locality = per_sqft.groupby(train["locality"]).median()
    rates = target["locality"].map(by_locality).fillna(per_sqft.median())
    return (rates * target["built_up_area_sqft"]).to_numpy(dtype=float)


def ridge_baseline(train_x: np.ndarray, train_log_y: np.ndarray, seed: int) -> Ridge:
    model = Ridge(alpha=1.0, random_state=seed)
    model.fit(train_x, train_log_y)
    return model


def train_mlp(
    train_x: np.ndarray, train_y: np.ndarray, val_x: np.ndarray, val_y: np.ndarray, config: TrainConfig
) -> tuple[ValuationMLP, dict]:
    """Targets are standardized log prices. Early stopping uses validation only; the test set is never seen here."""
    torch.manual_seed(config.seed)
    generator = torch.Generator().manual_seed(config.seed)
    model = ValuationMLP(train_x.shape[1], list(config.hidden_layers), config.dropout)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=6)
    loss_fn = nn.MSELoss()
    loader = DataLoader(TensorDataset(torch.from_numpy(train_x), torch.from_numpy(train_y)), batch_size=config.batch_size, shuffle=True, generator=generator)
    val_inputs, val_targets = torch.from_numpy(val_x), torch.from_numpy(val_y)

    best_state, best_loss, best_epoch = copy.deepcopy(model.state_dict()), float("inf"), 0
    history: list[float] = []
    for epoch in range(1, config.max_epochs + 1):
        model.train()
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            loss_fn(model(batch_x), batch_y).backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_loss = float(loss_fn(model(val_inputs), val_targets))
        history.append(val_loss)
        scheduler.step(val_loss)
        if val_loss < best_loss - 1e-5:
            best_state, best_loss, best_epoch = copy.deepcopy(model.state_dict()), val_loss, epoch
        elif epoch - best_epoch >= config.patience:
            break
    model.load_state_dict(best_state)
    model.eval()
    return model, {"best_epoch": best_epoch, "epochs_run": len(history), "best_validation_mse": best_loss}
