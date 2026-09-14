"""System data model and registry definitions."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

class WorkflowPhase(str, Enum):
    DEFINE = "a_define"
    IMPORT = "b_import"
    EXTRACT = "c_extract"
    VIEW_SOURCE = "d_view_source"
    GENERATE_MAPPINGS = "e_generate_mappings"
    APPROVE_MAPPINGS = "f_approve_mappings"
    VIEW_TRANSFORMED = "g_view_transformed"
    EXTRACT_DISTINCT = "h_extract_distinct"
    VALUE_MAPPINGS = "i_value_mappings"
    VALIDATIONS = "j_validations"
    UPDATE_DATA = "k_update_data"
    REVIEW_ITERATE = "l_review_iterate"

@dataclass
class SystemTableRegistry:
    sql_table: str
    label: str
    phase: WorkflowPhase
    editable: bool
    icon: Optional[str] = None

SYSTEM_TABLES: Dict[str, SystemTableRegistry] = {
    "migrations": SystemTableRegistry(
        sql_table="dbo.migrations", label="Migrations",
        phase=WorkflowPhase.DEFINE, editable=True, icon="folder"
    ),
    "field_mappings": SystemTableRegistry(
        sql_table="dbo.field_mappings", label="Field Mappings",
        phase=WorkflowPhase.APPROVE_MAPPINGS, editable=True, icon="link"
    ),
    "validation_rules": SystemTableRegistry(
        sql_table="dbo.validation_rules", label="Validation Rules",
        phase=WorkflowPhase.VALIDATIONS, editable=True, icon="check"
    ),
    "value_mappings": SystemTableRegistry(
        sql_table="dbo.value_mappings", label="Value Mappings",
        phase=WorkflowPhase.VALUE_MAPPINGS, editable=True, icon="list"
    ),
    "audit_log": SystemTableRegistry(
        sql_table="dbo.audit_log", label="Audit Log",
        phase=WorkflowPhase.REVIEW_ITERATE, editable=False, icon="history"
    ),
    "data_updates": SystemTableRegistry(
        sql_table="dbo.data_updates", label="Data Updates",
        phase=WorkflowPhase.UPDATE_DATA, editable=False, icon="pencil"
    ),
}

class RegistryManager:
    @staticmethod
    def get_system_tables() -> Dict[str, SystemTableRegistry]:
        return SYSTEM_TABLES.copy()
    
    @staticmethod
    def is_system_table(sql_table: str) -> bool:
        sql_table_lower = sql_table.lower()
        return any(reg.sql_table.lower() == sql_table_lower for reg in SYSTEM_TABLES.values())
