"""Configuration management for migr8lite."""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional

SYSTEM_ALIASES = {
    "BASE TABLE": "Tables",
    "VIEW": "Views",
    # Add more aliases as needed
}

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
    
    @staticmethod
    def _format_qualified_table_name(value: Any) -> Any:
        """Format schema.table as [schema].[table] without mutating config."""
        if not isinstance(value, str):
            return value

        parts = value.split(".")

        # Only format normal two-part schema.table values.
        if len(parts) != 2:
            return value

        schema, table = parts
        return f"[{schema}].[{table}]"

    def _get_formatted_section(self, section_name: str) -> Dict[str, Any]:
        """Return a formatted copy of a config section."""
        section = self.config.get(section_name, {})

        return {
            key: self._format_qualified_table_name(value)
            for key, value in section.items()
        }
    
    @property
    def database_config(self) -> Dict[str, Any]:
        return self.config.get("database", {})
    
    @property
    def app_config(self) -> Dict[str, Any]:
        return self.config.get("app", {})
    
    @property
    def logging_config(self) -> Dict[str, Any]:
        return self.config.get("logging", {})

    @property
    def system_schema_config(self) -> Dict[str, Any]:
        return self._get_formatted_section("systemschema")

    @property
    def system_management_config(self) -> Dict[str, Any]:
        return self._get_formatted_section("systemmanagementtables")

    @property
    def system_reference_config(self) -> Dict[str, Any]:
        return self._get_formatted_section("systemreferencetables")