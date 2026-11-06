import torch
from torch import nn


class ValuationMLP(nn.Module):
    """Multilayer perceptron predicting standardized log price from preprocessed tabular features."""

    def __init__(self, input_dim: int, hidden_layers: list[int], dropout: float):
        super().__init__()
        layers: list[nn.Module] = []
        previous = input_dim
        for width in hidden_layers:
            layers += [nn.Linear(previous, width), nn.ReLU(), nn.Dropout(dropout)]
            previous = width
        layers.append(nn.Linear(previous, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.net(features).squeeze(-1)
