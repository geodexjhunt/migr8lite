"""Configuration management for migr8lite."""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional

class Config:
    def __init__(self, config_file: Optional[str] = None):
        if config_file is None:
            config_file = Path(__file__).parent.parent / "config.yaml"
        self.config_path = Path(config_file)
        self.config: Dict[str, Any] = {}
        if self.config_path.exists():
            self._load_yaml()
        else:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
    
    def _load_yaml(self) -> None:
        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f) or {}
    
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
    
    @property
    def database_config(self) -> Dict[str, Any]:
        return self.config.get("database", {})
    
    @property
    def app_config(self) -> Dict[str, Any]:
        return self.config.get("app", {})
    
    @property
    def logging_config(self) -> Dict[str, Any]:
        return self.config.get("logging", {})
