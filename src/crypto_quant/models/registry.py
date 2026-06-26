from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, GradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from crypto_quant.models.optional_dependencies import optional_dependency_status, require_optional_dependency


@dataclass(frozen=True)
class ModelSpec:
    """Serializable description of a model candidate for BTC low-frequency research."""

    name: str
    description: str
    factory: Callable[[], Pipeline]
    optional_package: str | None = None
    default_enabled: bool = True

    @property
    def is_available(self) -> bool:
        if self.optional_package is None:
            return True
        return bool(optional_dependency_status(self.optional_package).installed)

    @property
    def install_hint(self) -> str:
        if self.optional_package is None:
            return "built-in"
        return optional_dependency_status(self.optional_package).install_hint


def _extra_trees() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", ExtraTreesClassifier(
            n_estimators=160,
            max_depth=8,
            min_samples_leaf=20,
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
            class_weight="balanced_subsample",
        )),
    ])


def _random_forest() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", RandomForestClassifier(
            n_estimators=180,
            max_depth=7,
            min_samples_leaf=25,
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
            class_weight="balanced_subsample",
        )),
    ])


def _logistic_l2() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(
            C=0.5,
            solver="lbfgs",
            max_iter=2000,
            class_weight="balanced",
            random_state=42,
        )),
    ])


def _hist_gradient_boosting() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingClassifier(
            max_iter=160,
            learning_rate=0.035,
            max_leaf_nodes=24,
            l2_regularization=0.01,
            random_state=42,
        )),
    ])


def _gradient_boosting() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", GradientBoostingClassifier(
            n_estimators=120,
            learning_rate=0.035,
            max_depth=3,
            min_samples_leaf=25,
            random_state=42,
        )),
    ])


def _lightgbm_classifier() -> Pipeline:
    require_optional_dependency("lightgbm")
    from lightgbm import LGBMClassifier

    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", LGBMClassifier(
            n_estimators=220,
            learning_rate=0.025,
            num_leaves=24,
            max_depth=-1,
            min_child_samples=40,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.05,
            reg_lambda=1.0,
            objective="binary",
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )),
    ])


def _xgboost_classifier() -> Pipeline:
    require_optional_dependency("xgboost")
    from xgboost import XGBClassifier

    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", XGBClassifier(
            n_estimators=220,
            max_depth=3,
            learning_rate=0.025,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=8,
            reg_alpha=0.05,
            reg_lambda=1.0,
            objective="binary:logistic",
            eval_metric="logloss",
            tree_method="hist",
            random_state=42,
            n_jobs=-1,
        )),
    ])


MODEL_REGISTRY: dict[str, ModelSpec] = {
    "extra_trees": ModelSpec(
        name="extra_trees",
        description="Fast nonlinear tree ensemble; robust baseline for repeated walk-forward fitting.",
        factory=_extra_trees,
    ),
    "random_forest": ModelSpec(
        name="random_forest",
        description="Bagged tree ensemble; lower variance than a single tree, useful as a conservative benchmark.",
        factory=_random_forest,
    ),
    "logistic_l2": ModelSpec(
        name="logistic_l2",
        description="Linear probabilistic baseline with scaling; useful for checking whether nonlinear models add value.",
        factory=_logistic_l2,
    ),
    "hist_gradient_boosting": ModelSpec(
        name="hist_gradient_boosting",
        description="Histogram gradient boosting classifier; compact nonlinear boosted baseline.",
        factory=_hist_gradient_boosting,
    ),
    "gradient_boosting": ModelSpec(
        name="gradient_boosting",
        description="Classic gradient boosting classifier; slower but interpretable baseline.",
        factory=_gradient_boosting,
    ),
    "lightgbm": ModelSpec(
        name="lightgbm",
        description="Optional LightGBM gradient boosting backend; usually fast and strong on tabular market features.",
        factory=_lightgbm_classifier,
        optional_package="lightgbm",
        default_enabled=False,
    ),
    "xgboost": ModelSpec(
        name="xgboost",
        description="Optional XGBoost gradient boosting backend; strong tabular baseline with explicit optional dependency.",
        factory=_xgboost_classifier,
        optional_package="xgboost",
        default_enabled=False,
    ),
}


def canonical_model_name(name: str) -> str:
    key = name.strip().lower()
    aliases = {
        "extra_trees_classifier": "extra_trees",
        "extratrees": "extra_trees",
        "et": "extra_trees",
        "rf": "random_forest",
        "random_forest_classifier": "random_forest",
        "logistic": "logistic_l2",
        "logreg": "logistic_l2",
        "hist_gbdt": "hist_gradient_boosting",
        "hgb": "hist_gradient_boosting",
        "gbdt": "gradient_boosting",
        "lgb": "lightgbm",
        "lgbm": "lightgbm",
        "lightgbm_classifier": "lightgbm",
        "xgb": "xgboost",
        "xgb_classifier": "xgboost",
        "xgboost_classifier": "xgboost",
    }
    return aliases.get(key, key)


def available_models(include_unavailable: bool = False, include_optional: bool = True) -> list[str]:
    names: list[str] = []
    for name, spec in MODEL_REGISTRY.items():
        if spec.optional_package and not include_optional:
            continue
        if include_unavailable or spec.is_available:
            names.append(name)
    return names


def default_enabled_models(include_optional_if_installed: bool = False) -> list[str]:
    names: list[str] = []
    for name, spec in MODEL_REGISTRY.items():
        if spec.default_enabled:
            names.append(name)
        elif include_optional_if_installed and spec.optional_package and spec.is_available:
            names.append(name)
    return names


def model_availability_rows() -> list[dict[str, object]]:
    rows = []
    for name, spec in MODEL_REGISTRY.items():
        rows.append({
            "model": name,
            "description": spec.description,
            "optional_package": spec.optional_package or "",
            "available": spec.is_available,
            "default_enabled": spec.default_enabled,
            "install_hint": spec.install_hint,
        })
    return rows


def make_model_by_name(name: str = "extra_trees") -> Pipeline:
    key = canonical_model_name(name)
    if key not in MODEL_REGISTRY:
        raise KeyError(f"Unknown model '{name}'. Available models: {available_models(include_unavailable=True)}")
    spec = MODEL_REGISTRY[key]
    if spec.optional_package and not spec.is_available:
        require_optional_dependency(spec.optional_package)
    return spec.factory()
