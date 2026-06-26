from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from crypto_quant.models.optional_dependencies import optional_dependency_status, require_optional_dependency
from crypto_quant.models.sequence_dataset import flatten_sequences


class FlattenedSequenceClassifier:
    """Adapter that lets standard sklearn estimators consume 3D windows.

    This is the default V2.8 sequence baseline. It is not a deep sequence model;
    it is a deliberately simple flattened-window benchmark that tells us whether
    explicit sequence windows add value before installing or training PyTorch
    LSTM/GRU/TCN models.
    """

    def __init__(self, estimator: Pipeline | None = None):
        self.estimator = estimator or Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", MLPClassifier(
                hidden_layer_sizes=(64, 32),
                activation="relu",
                alpha=1e-3,
                learning_rate_init=1e-3,
                max_iter=250,
                early_stopping=True,
                validation_fraction=0.15,
                n_iter_no_change=12,
                random_state=42,
            )),
        ])

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.estimator.fit(flatten_sequences(X), np.asarray(y, dtype=int))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.estimator.predict_proba(flatten_sequences(X))

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.estimator.predict(flatten_sequences(X))


class TorchSequenceClassifier:
    """Small optional PyTorch LSTM/GRU/TCN classifier.

    The class imports torch lazily, so the core framework remains installable
    without PyTorch.  Defaults are intentionally lightweight for research
    smoke-tests; serious experiments should adjust epochs/batch_size in config.
    """

    def __init__(
        self,
        architecture: str = "lstm",
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.1,
        learning_rate: float = 1e-3,
        epochs: int = 12,
        batch_size: int = 128,
        weight_decay: float = 1e-4,
        seed: int = 42,
        device: str = "auto",
    ):
        require_optional_dependency("torch")
        import torch  # noqa: F401

        self.architecture = architecture.lower()
        self.hidden_size = int(hidden_size)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)
        self.learning_rate = float(learning_rate)
        self.epochs = int(epochs)
        self.batch_size = int(batch_size)
        self.weight_decay = float(weight_decay)
        self.seed = int(seed)
        self.device_name = device
        self.model_ = None
        self.feature_mean_ = None
        self.feature_std_ = None
        self.classes_ = np.array([0, 1])

    def _device(self):
        import torch

        if self.device_name == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(self.device_name)

    def _standardize_fit(self, X: np.ndarray) -> np.ndarray:
        self.feature_mean_ = np.nanmean(X, axis=(0, 1), keepdims=True)
        self.feature_std_ = np.nanstd(X, axis=(0, 1), keepdims=True)
        self.feature_std_ = np.where(self.feature_std_ < 1e-8, 1.0, self.feature_std_)
        return self._standardize_transform(X)

    def _standardize_transform(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        if self.feature_mean_ is None or self.feature_std_ is None:
            return X
        return ((X - self.feature_mean_) / self.feature_std_).astype(np.float32)

    def _build_model(self, n_features: int):
        import torch
        import torch.nn as nn

        architecture = self.architecture
        hidden_size = self.hidden_size
        num_layers = self.num_layers
        dropout = self.dropout if num_layers > 1 else 0.0

        class _RecurrentNet(nn.Module):
            def __init__(self, kind: str):
                super().__init__()
                rnn_cls = nn.GRU if kind == "gru" else nn.LSTM
                self.rnn = rnn_cls(
                    input_size=n_features,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    batch_first=True,
                    dropout=dropout,
                )
                self.head = nn.Sequential(nn.LayerNorm(hidden_size), nn.Dropout(dropout), nn.Linear(hidden_size, 1))

            def forward(self, x):
                out, _ = self.rnn(x)
                return self.head(out[:, -1, :]).squeeze(-1)

        class _TCNNet(nn.Module):
            def __init__(self):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Conv1d(n_features, hidden_size, kernel_size=3, padding=2, dilation=2),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                    nn.Conv1d(hidden_size, hidden_size, kernel_size=3, padding=4, dilation=4),
                    nn.ReLU(),
                    nn.AdaptiveAvgPool1d(1),
                )
                self.head = nn.Sequential(nn.Flatten(), nn.LayerNorm(hidden_size), nn.Linear(hidden_size, 1))

            def forward(self, x):
                # input: batch, time, features -> batch, features, time
                z = self.net(x.transpose(1, 2))
                return self.head(z).squeeze(-1)

        if architecture == "tcn":
            return _TCNNet()
        if architecture in {"lstm", "gru"}:
            return _RecurrentNet(architecture)
        raise ValueError("architecture must be one of: lstm, gru, tcn")

    def fit(self, X: np.ndarray, y: np.ndarray):
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        torch.manual_seed(self.seed)
        np.random.seed(self.seed)
        Xs = self._standardize_fit(X)
        y_arr = np.asarray(y, dtype=np.float32)
        if len(np.unique(y_arr.astype(int))) < 2:
            raise ValueError("TorchSequenceClassifier needs both classes in training data.")
        device = self._device()
        model = self._build_model(Xs.shape[2]).to(device)
        pos = max(float(y_arr.sum()), 1.0)
        neg = max(float(len(y_arr) - y_arr.sum()), 1.0)
        criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([neg / pos], dtype=torch.float32, device=device))
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.learning_rate, weight_decay=self.weight_decay)
        ds = TensorDataset(torch.tensor(Xs, dtype=torch.float32), torch.tensor(y_arr, dtype=torch.float32))
        loader = DataLoader(ds, batch_size=max(1, self.batch_size), shuffle=True)
        model.train()
        for _ in range(max(1, self.epochs)):
            for xb, yb in loader:
                xb = xb.to(device)
                yb = yb.to(device)
                optimizer.zero_grad()
                loss = criterion(model(xb), yb)
                loss.backward()
                optimizer.step()
        self.model_ = model
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        import torch

        if self.model_ is None:
            raise RuntimeError("Model is not fit.")
        Xs = self._standardize_transform(X)
        device = self._device()
        self.model_.eval()
        probs: list[np.ndarray] = []
        with torch.no_grad():
            for start in range(0, len(Xs), max(1, self.batch_size)):
                xb = torch.tensor(Xs[start:start + self.batch_size], dtype=torch.float32, device=device)
                p = torch.sigmoid(self.model_(xb)).detach().cpu().numpy()
                probs.append(p)
        p1 = np.concatenate(probs) if probs else np.empty((0,), dtype=float)
        p1 = np.clip(p1, 1e-6, 1.0 - 1e-6)
        return np.column_stack([1.0 - p1, p1])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


@dataclass(frozen=True)
class SequenceModelSpec:
    name: str
    description: str
    factory: Callable[..., object]
    optional_package: str | None = None
    default_enabled: bool = True

    @property
    def is_available(self) -> bool:
        if self.optional_package is None:
            return True
        return optional_dependency_status(self.optional_package).installed

    @property
    def install_hint(self) -> str:
        if self.optional_package is None:
            return "built-in"
        return optional_dependency_status(self.optional_package).install_hint


def _sequence_mlp(**_: object) -> FlattenedSequenceClassifier:
    return FlattenedSequenceClassifier()


def _lstm(**kwargs: object) -> TorchSequenceClassifier:
    return TorchSequenceClassifier(architecture="lstm", **kwargs)


def _gru(**kwargs: object) -> TorchSequenceClassifier:
    return TorchSequenceClassifier(architecture="gru", **kwargs)


def _tcn(**kwargs: object) -> TorchSequenceClassifier:
    return TorchSequenceClassifier(architecture="tcn", **kwargs)


SEQUENCE_MODEL_REGISTRY: dict[str, SequenceModelSpec] = {
    "sequence_mlp": SequenceModelSpec(
        name="sequence_mlp",
        description="Built-in flattened-window MLP baseline. No PyTorch required.",
        factory=_sequence_mlp,
        default_enabled=True,
    ),
    "lstm": SequenceModelSpec(
        name="lstm",
        description="Optional PyTorch LSTM sequence classifier.",
        factory=_lstm,
        optional_package="torch",
        default_enabled=False,
    ),
    "gru": SequenceModelSpec(
        name="gru",
        description="Optional PyTorch GRU sequence classifier.",
        factory=_gru,
        optional_package="torch",
        default_enabled=False,
    ),
    "tcn": SequenceModelSpec(
        name="tcn",
        description="Optional PyTorch temporal convolution classifier.",
        factory=_tcn,
        optional_package="torch",
        default_enabled=False,
    ),
}


def canonical_sequence_model_name(name: str) -> str:
    key = name.strip().lower()
    aliases = {
        "mlp": "sequence_mlp",
        "flat_mlp": "sequence_mlp",
        "flattened_mlp": "sequence_mlp",
        "rnn_lstm": "lstm",
        "rnn_gru": "gru",
        "temporal_cnn": "tcn",
    }
    return aliases.get(key, key)


def sequence_model_availability_rows() -> list[dict[str, object]]:
    rows = []
    for name, spec in SEQUENCE_MODEL_REGISTRY.items():
        rows.append({
            "model": name,
            "description": spec.description,
            "optional_package": spec.optional_package or "",
            "available": spec.is_available,
            "default_enabled": spec.default_enabled,
            "install_hint": spec.install_hint,
        })
    return rows


def default_sequence_models(include_torch_if_installed: bool = False) -> list[str]:
    names = []
    for name, spec in SEQUENCE_MODEL_REGISTRY.items():
        if spec.default_enabled:
            names.append(name)
        elif include_torch_if_installed and spec.optional_package and spec.is_available:
            names.append(name)
    return names


def make_sequence_model_by_name(name: str = "sequence_mlp", **kwargs: object):
    key = canonical_sequence_model_name(name)
    if key not in SEQUENCE_MODEL_REGISTRY:
        raise KeyError(f"Unknown sequence model '{name}'. Available: {sorted(SEQUENCE_MODEL_REGISTRY)}")
    spec = SEQUENCE_MODEL_REGISTRY[key]
    if spec.optional_package and not spec.is_available:
        require_optional_dependency(spec.optional_package)
    return spec.factory(**kwargs)
