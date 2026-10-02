"""System data model and registry definitions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional
import pandas as pd

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
class Job:
    jobid: int
    jobname: str
    schemaname: str
    jobprefix: str
    description: str
    status: str
    purpose: str
    createdby: str
    createddate: Optional[datetime] = None
    jobstartdate: Optional[datetime] = None
    jobcompletedate: Optional[datetime] = None
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "Job":
        """Construct a Job from a database result row."""
        return cls(
            jobid=row["jobid"],
            jobname=row["jobname"],
            schemaname=row["schemaname"],
            jobprefix=row["jobprefix"],
            description=row["description"],
            status=row["status"],
            purpose=row["purpose"],
            createdby=row["createdby"],
            createddate=row.get("createddate"),
            jobstartdate=row.get("jobstartdate"),
            jobcompletedate=row.get("jobcompletedate"),
        )

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
    def has_same_content(self, other: "DataFileObject") -> bool:
        """
        Compare only the fields that matter for upsert logic.
        """
        return (

            self.datafileid == other.datafileid
            and self.objecttype == other.objecttype
            and self.objectname == other.objectname
            and self.stagingtableschema == other.stagingtableschema
            and self.stagingtablename == other.stagingtablename
            and self.skipobject == other.skipobject
            and self.skipmessage == other.skipmessage
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
class DataFileObjectFieldHeader:
    datafileobjectfieldheaderid: int
    datafileobjectfieldid: int
    headernum: int
    headervalue: str
    sanitisedheadervalue: str
    valuesanitised: bool
    timestamp: datetime
    @classmethod
    def from_db_row(cls,row: dict[str, Any]) -> "DataFileObjectFieldHeader":
        """Construct a DataFileObjectFieldHeader from a database result row."""
        return cls(
            datafileobjectfieldheaderid=row["datafileobjectfieldheaderid"],
            datafileobjectfieldid=row["datafileobjectfieldid"],
            headernum=row["headernum"],
            headervalue=row["headervalue"],
            sanitisedheadervalue=row["sanitisedheadervalue"],
            valuesanitised=row["valuesanitised"],
            timestamp=row["timestamp"],
        )
    def has_same_content(self, other: "DataFileObjectFieldHeader") -> bool:
        """Check if another DataFileObjectFieldHeader has the same content (excluding the ID)."""
        return (
            self.datafileobjectfieldid == other.datafileobjectfieldid and
            self.headernum == other.headernum and
            self.headervalue == other.headervalue and
            self.sanitisedheadervalue == other.sanitisedheadervalue and
            self.valuesanitised == other.valuesanitised 
        )

@dataclass
class DataFileObjectHeaderRow:
    datafileobjectheaderrowid: int
    datafileobjectid: int
    headernum: int
    rownumber: int
    timestamp: datetime
    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "DataFileObjectHeaderRow":
        """Construct a DataFileObjectHeaderRow from a database result row."""
        return cls(
            datafileobjectheaderrowid=row["datafileobjectheaderrowid"],
            datafileobjectid=row["datafileobjectid"],
            headernum=row["headernum"],
            rownumber=row["rownumber"],
            timestamp=row["timestamp"],
        )
    def has_same_content(self, other: "DataFileObjectHeaderRow") -> bool:
        """Check if another DataFileObjectHeaderRow has the same content (excluding the ID)."""
        return (
            self.datafileobjectid == other.datafileobjectid and
            self.headernum == other.headernum and
            self.rownumber == other.rownumber
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


####### ExtractService required these classes below:

class ExistingTablePolicy(Enum):
    NOT_SET = auto()
    ABORT = auto()      # default: do nothing if the table exists
    SKIP = auto()
    APPEND = auto()
    REPLACE = auto()    # drop and recreate


class IssueType(Enum):
    TABLE_EXISTS = auto()
    # add others as they appear (e.g. NO_HEADER_ROW, DUPLICATE_COLUMNS)


@dataclass
class PreflightResult:
    issues: List[IssueType] = field(default_factory=list)
    detail: str = ""

    @property
    def ok(self) -> bool:
        return not self.issues


class ExtractStatus(Enum):
    SUCCESS = auto()
    SKIPPED = auto()
    FAILED = auto()


@dataclass
class ExtractResult:
    status: ExtractStatus
    message: str = ""
    rows_loaded: int = 0

@dataclass
class TableExtractRequest:
    datafileobjectid: int
    stagingtablename: str
    stagingtableschema: str
    existing_policy: ExistingTablePolicy = ExistingTablePolicy.NOT_SET



@dataclass
class ObjectExtraction:
    df: pd.DataFrame | None = None
    error: str | None = None