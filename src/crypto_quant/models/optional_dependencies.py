from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module, metadata, util
from typing import Iterable


@dataclass(frozen=True)
class OptionalDependencyStatus:
    """Status row for optional model backends.

    Optional packages are intentionally not required by requirements.txt so the
    core research framework remains easy to install.  These helpers let scripts
    report what is available and skip unavailable backends cleanly.
    """

    package: str
    import_name: str
    installed: bool
    version: str | None
    install_hint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "package": self.package,
            "import_name": self.import_name,
            "installed": self.installed,
            "version": self.version,
            "install_hint": self.install_hint,
        }


OPTIONAL_MODEL_PACKAGES: dict[str, tuple[str, str]] = {
    "lightgbm": ("lightgbm", "pip install lightgbm"),
    "xgboost": ("xgboost", "pip install xgboost"),
    "torch": ("torch", "pip install torch --index-url https://download.pytorch.org/whl/cu121"),
}


def optional_dependency_status(package: str) -> OptionalDependencyStatus:
    if package not in OPTIONAL_MODEL_PACKAGES:
        raise KeyError(f"Unknown optional package '{package}'. Known: {sorted(OPTIONAL_MODEL_PACKAGES)}")
    import_name, install_hint = OPTIONAL_MODEL_PACKAGES[package]
    installed = util.find_spec(import_name) is not None
    version = None
    if installed:
        try:
            version = metadata.version(package)
        except Exception:
            try:
                mod = import_module(import_name)
                version = getattr(mod, "__version__", None)
            except Exception:
                version = None
    return OptionalDependencyStatus(
        package=package,
        import_name=import_name,
        installed=installed,
        version=version,
        install_hint=install_hint,
    )


def optional_dependency_table(packages: Iterable[str] | None = None) -> list[dict[str, object]]:
    names = list(packages) if packages is not None else list(OPTIONAL_MODEL_PACKAGES)
    return [optional_dependency_status(name).to_dict() for name in names]


def require_optional_dependency(package: str) -> None:
    status = optional_dependency_status(package)
    if not status.installed:
        raise ImportError(
            f"Optional dependency '{package}' is not installed. "
            f"Install it with: {status.install_hint}. "
            "Core models still work without this package."
        )
