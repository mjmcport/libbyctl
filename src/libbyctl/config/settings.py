from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir


@dataclass(slots=True)
class Settings:
    preferred_formats: list[str] = field(default_factory=lambda: ["audiobook", "ebook"])
    avoid_duplicate_holds: bool = True
    max_concurrency: int = 5
    timeout_seconds: float = 20.0
    libby_base_url: str = "https://sentry.libbyapp.com"
    thunder_base_url: str = "https://thunder.api.overdrive.com/v2"
    thunder_client_id: str = "dewey"

    @property
    def config_dir(self) -> Path:
        return Path(user_config_dir("libbyctl", appauthor=False))

    @property
    def config_path(self) -> Path:
        override = os.getenv("LIBBYCTL_CONFIG")
        return Path(override).expanduser() if override else self.config_dir / "config.toml"

    @property
    def data_dir(self) -> Path:
        override = os.getenv("LIBBYCTL_DATA_DIR")
        return Path(override).expanduser() if override else Path(user_data_dir("libbyctl", appauthor=False))

    @property
    def database_path(self) -> Path:
        return self.data_dir / "libbyctl.db"

    @classmethod
    def load(cls) -> "Settings":
        settings = cls()
        path = settings.config_path
        if not path.exists():
            return settings
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        general = raw.get("general", {})
        planner = raw.get("planner", {})
        network = raw.get("network", {})
        providers = raw.get("providers", {})
        settings.preferred_formats = list(planner.get("preferred_formats", settings.preferred_formats))
        settings.avoid_duplicate_holds = bool(
            planner.get("avoid_duplicate_holds", settings.avoid_duplicate_holds)
        )
        settings.max_concurrency = int(network.get("max_concurrency", settings.max_concurrency))
        settings.timeout_seconds = float(network.get("timeout_seconds", settings.timeout_seconds))
        settings.libby_base_url = str(providers.get("libby_base_url", settings.libby_base_url))
        settings.thunder_base_url = str(providers.get("thunder_base_url", settings.thunder_base_url))
        settings.thunder_client_id = str(providers.get("thunder_client_id", settings.thunder_client_id))
        _ = general
        return settings

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        formats = ", ".join(f'"{x}"' for x in self.preferred_formats)
        content = f'''[planner]\npreferred_formats = [{formats}]\navoid_duplicate_holds = {str(self.avoid_duplicate_holds).lower()}\n\n[network]\nmax_concurrency = {self.max_concurrency}\ntimeout_seconds = {self.timeout_seconds}\n\n[providers]\nlibby_base_url = "{self.libby_base_url}"\nthunder_base_url = "{self.thunder_base_url}"\nthunder_client_id = "{self.thunder_client_id}"\n'''
        self.config_path.write_text(content, encoding="utf-8")
