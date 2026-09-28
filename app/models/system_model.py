"""System data model and registry definitions."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

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
class DataFile:
    datafileid: int
    filetype: str
    hashsha256: str
    filesizebytes: int
    skipfile: Optional[bool] = None
    skipmessage: Optional[str] = None
    
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "DataFile":
        """Construct a DataFile from a database result row."""
        return cls(
            datafileid=row["datafileid"],
            filetype=row["filetype"],
            hashsha256=row["hashsha256"],
            filesizebytes=row["filesizebytes"],
            skipfile=row["skipfile"],
            skipmessage=row["skipmessage"],
        )
    
@dataclass
class JobFile:
    jobfileid: int
    datafileid: int
    jobrunversionid: int
    newfile: bool
    folderid: int
    filename: str
    filecreateddate: Optional[datetime] = None
    filemodifieddate: Optional[datetime] = None
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "JobFile":
        """Construct a JobFile from a database result row."""
        return cls(
            jobfileid=row["jobfileid"],
            datafileid=row["datafileid"],
            jobrunversionid=row["jobrunversionid"],
            newfile=row["newfile"],
            folderid=row.get("folderid"),
            filename=row["filename"],
            filecreateddate=row["filecreateddate"],
            filemodifieddate=row["filemodifieddate"],
        )
    def has_same_content(self, other: "JobFile") -> bool:
        """
        Compare only the fields that matter for upsert logic.
        Ignore jobfileid (PK), datafileid/jobrunversionid (FK lookup keys),
        and timestamps (may differ naturally).
        """
        return (

            self.datafileid == other.datafileid
            and self.filecreateddate == other.filecreateddate
            and self.filemodifieddate == other.filemodifieddate
        )
    
@dataclass
class JobFolder:
    folderid: int
    jobrunversionid: int
    foldertype: str
    foldername: str
    folderpath: str
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "JobFolder":   
        """Construct a JobFolder from a database result row."""
        return cls(
            folderid=row["folderid"],
            jobrunversionid=row["jobrunversionid"],
            foldertype=row["foldertype"],
            foldername=row["foldername"],
            folderpath=row["folderpath"],
        )

@dataclass
class JobRunVersion:
    jobrunversionid: int
    jobid: int
    runversion: str
    rundatetime: Optional[datetime] = None
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "JobRunVersion":   
        """Construct a JobRunVersion from a database result row."""
        return cls(
            jobrunversionid=row["jobrunversionid"],
            jobid=row["jobid"],
            runversion=row["runversion"],
            rundatetime=row["rundatetime"],
        )
    
@dataclass
class DataFileObject:
    datafileobjectid: int
    datafileid: int
    objecttype: str
    objectname: str
    stagingtableschema: Optional[str] = None
    stagingtablename: Optional[str] = None
    skipobject: Optional[bool] = None
    skipmessage: Optional[str] = None
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "DataFileObject":
        """Construct a DataFileObject from a database result row."""
        return cls(
            datafileobjectid=row["datafileobjectid"],
            datafileid=row["datafileid"],
            objecttype=row.get("objecttype", "sheet"),
            objectname=row["objectname"],
            stagingtableschema=row.get("stagingtableschema"),
            stagingtablename=row.get("stagingtablename"),
            skipobject=row.get("skipobject"),
            skipmessage=row.get("skipmessagge"),
        )
    
@dataclass
class DataFileObjectField:
    datafileobjectfieldid: int
    datafileobjectid: int
    fieldordinal: int
    fielddatatype: str
    fieldlength: Optional[int] = None
    fieldprecision: Optional[int] = None
    skipfield: Optional[bool] = None
    skipmessage: Optional[str] = None   
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "DataFileObjectField":
        """Construct a DataFileObjectField from a database result row."""
        return cls(
            datafileobjectfieldid=row["datafileobjectfieldid"],
            datafileobjectid=row["datafileobjectid"],
            fieldordinal=row["fieldordinal"],
            fielddatatype=row["fielddatatype"],
            fieldlength=row.get("fieldlength"),
            fieldprecision=row.get("fieldprecision"),
            skipfield=row.get("skipfield"),
            skipmessage=row.get("skipmessage"),
        )   

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
