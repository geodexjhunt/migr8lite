
#### File Service Module
#### Provides functionality for handling file operations within the application.
from dataclasses import fields
import gc
import hashlib
import os
from pathlib import Path
import re
import time
from datetime import datetime, date
from tkinter.font import names
from typing import Any, Dict, Callable, List, Optional
from arrow import ParserError
import pandas as pd 
from app.models.system_model import DataFile, DataFileObject, DataFileObjectField,DataFileObjectFieldHeader,DataFileObjectHeaderRow, ObjectExtraction, TableExtractRequest
from app.services.db_service import DatabaseService
import pyodbc
from app.constants import DEFAULT_SETTINGS, SQLSERVER_MAX_IDENTIFIER_LEN

## File Scanning and counting helpers
def get_file_counts(initial_folders: list[Path]) -> tuple[dict[str, int], list[str]]:
    outstring: list[str] = []
    grand_totals_by_ext: dict[str, int] = {}
    all_files_by_folder: dict[Path, dict[str, list[Path]]] = {}
    files_by_ext: dict[str, list[Path]] = {}

    for folder in initial_folders:
        p = Path(folder)
        if not p.exists() or not p.is_dir():
            raise ValueError(f"Invalid folder: {folder}")
            continue
        else:
            files_by_ext = collect_all_files(p)

        all_files_by_folder[p] = files_by_ext

        outstring.extend(log_extension_summary(p, files_by_ext))
        merge_counts(grand_totals_by_ext, files_by_ext)

    outstring.extend(log_extension_grand_totals(grand_totals_by_ext))
    
    return grand_totals_by_ext, outstring

def collect_all_files(source: Path, recursive: bool = True) -> dict[str, list[Path]]:
    """
    Returns files grouped by suffix ('.csv', '.xlsx', '' for no extension).
    """
    paths = source.rglob("*") if recursive else source.glob("*")
    out: dict[str, list[Path]] = {}

    for p in paths:
        if not p.is_file():
            continue
        ext = p.suffix.lower()  # '' if no extension
        out.setdefault(ext, []).append(p)

    for ext in out:
        out[ext].sort()

    return out
    
def collect_files_by_extension(source: Path, extensions: list[str], recursive: bool = True) -> dict[str, list[Path]]:
    out = {}
    for ext in extensions:
        e = ext.lower().strip()
        if not e.startswith("."):
            e = "." + e
        out[e] = sorted(source.rglob(f"*{e}") if recursive else source.glob(f"*{e}"))
    return out
    
def merge_counts(aggregate: dict[str, int], files_by_ext: dict[str, list[Path]]):
    for ext, files in files_by_ext.items():
        aggregate[ext] = aggregate.get(ext, 0) + len(files)

def log_extension_summary(folder: Path, files_by_ext: dict[str, list[Path]]) -> list[str]:
        outstring = []
        outstring.append(f"File counts by extension for folder: {folder}")
        for ext, files in files_by_ext.items():
            outstring.append(f"  {ext}: {len(files)} file(s)")
        return outstring

def log_extension_grand_totals(totals_by_ext: dict[str, int]) -> list[str]:
        outstring = []
        outstring.append("Grand totals across all initial folders:")
        for ext, count in totals_by_ext.items():
            outstring.append(f"  {ext}: {count} file(s)")
        outstring.append(f"  ALL: {sum(totals_by_ext.values())} file(s)")
        return outstring

def scan_subfolders(root_folders: list[str]) -> list[tuple[str, str]]:
        
        """
        Returns list of (foldername, folderpath) for all discovered subfolders.
        """
        out = []
        seen = set()
        for root in root_folders:
            rp = Path(root)
            if not rp.exists() or not rp.is_dir():
                continue
            for dirpath, dirnames, _ in os.walk(rp):
                for d in dirnames:
                    full = str(Path(dirpath) / d)
                    key = full.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append((d, full))
        return out

## File hashing helper 
def sha256_file(fp: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with fp.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

## Access Connection Helper for all Access file readin
def _open_access_connection(fp: Path):
    ext = fp.suffix.lower()

    candidates = []
    if ext == ".accdb":
        candidates = [
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};",
            r"DRIVER={Microsoft Access Driver (*.mdb)};",  # fallback if odd install
        ]
    elif ext == ".mdb":
        candidates = [
            r"DRIVER={Microsoft Access Driver (*.mdb)};",
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};",
        ]
    else:
        candidates = [r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"]

    last_err = None
    for drv in candidates:
        try:
            conn_str = f"{drv}DBQ={str(fp)};"
            return pyodbc.connect(conn_str)
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Unable to open Access file '{fp}': {last_err}")

####################################
####################################
## Main datafile processing function
## for reading objects and fields and header rows

def process_datafile(db_service: DatabaseService,fp: Path,datafileid: int,ftype: str,subtype: str,read_fileobjectfields: bool = True,datafileobjecttemplate: DataFileObject | None = None,) -> tuple[list[DataFileObject], list[DataFileObjectField]]:
    """
    Read all objects and optionally all fields from a datafile.
    Opens the file once and delegates to shared orchestration logic.
    """
    if datafileobjecttemplate is not None:
        stagingtableschema = datafileobjecttemplate.stagingtableschema
        stagingtablename = datafileobjecttemplate.stagingtablename
    else:
        stagingtableschema = ""
        stagingtablename = ""

    try:
        if ftype == "excel":
            ext = fp.suffix.lower()
            engine_map = {
                ".xls": "xlrd",
                ".xlsx": "openpyxl", ".xlsm": "openpyxl",
                ".xltx": "openpyxl", ".xltm": "openpyxl",
                ".xlsb": "pyxlsb",
            }
            engine = engine_map.get(ext)
            if engine is None:
                print(f"⚠️ Unsupported Excel extension for {fp.name}: {ext}")
                return [], []

            with pd.ExcelFile(fp, engine=engine) as excel_file:
                return _process_objects_common(
                    db_service=db_service,
                    datafileid=datafileid,
                    stagingtableschema=stagingtableschema,
                    stagingtablename=stagingtablename,
                    read_fileobjectfields=read_fileobjectfields,
                    read_objects_fn=lambda: _read_excel_objects(
                        excel_file=excel_file, datafileid=datafileid
                    ),
                    read_fields_fn=lambda sheet_name, dfoid: _read_excel_fields(
                        excel_file=excel_file, sheet_name=sheet_name, datafileobjectid=dfoid
                    ),
                    read_header_fn=lambda sheet_name, dfoid: _read_excel_header_row(
                        excel_file=excel_file, sheet_name=sheet_name,
                        datafileobjectid=dfoid, db_service=db_service,
                    ),
                    defaultrownumber=1,
                )

        elif ftype == "database" and subtype == "access":
            with _open_access_connection(fp) as acc_conn:
                acc_conn.autocommit = True
                return _process_objects_common(
                    db_service=db_service,
                    datafileid=datafileid,
                    stagingtableschema=stagingtableschema,
                    stagingtablename=stagingtablename,
                    read_fileobjectfields=read_fileobjectfields,
                    read_objects_fn=lambda: _read_access_objects(
                        connection=acc_conn, datafileid=datafileid
                    ),
                    read_fields_fn=lambda table_name, dfoid: _read_access_fields(
                        connection=acc_conn, table_name=table_name, datafileobjectid=dfoid
                    ),
                    read_header_fn=lambda table_name, dfoid: _read_access_header_row(
                        connection=acc_conn, table_name=table_name, datafileobjectid=dfoid
                    ),
                    defaultrownumber=0,    
                )

        elif ftype == "text":
            return _process_objects_common(
                db_service=db_service,
                datafileid=datafileid,
                stagingtableschema=stagingtableschema,
                stagingtablename=stagingtablename,
                read_fileobjectfields=read_fileobjectfields,
                read_objects_fn=lambda: _read_text_objects(fp=fp, datafileid=datafileid),
            read_fields_fn=lambda _object_name, dfoid: _read_text_fields(
                    fp=fp, datafileobjectid=dfoid
                ),
                read_header_fn=lambda _object_name, dfoid: _read_text_header_row(
                        fp=fp, datafileobjectid=dfoid, db_service=db_service,
                    ),
                defaultrownumber=1,
            )

        else:
            raise ValueError(f"Unsupported file type: {ftype}")

    except Exception as e:
        print(f"Error processing datafile {fp}: {e}")
        return [], []

## Common orchestration logic for processing datafile objects, fields, and headers
def _process_objects_common(db_service: DatabaseService,datafileid: int,stagingtableschema: str,stagingtablename: str,read_fileobjectfields: bool,read_objects_fn: Callable[[], list[DataFileObject]]
                            ,read_fields_fn: Optional[Callable[[str, int], list[DataFileObjectField]]],read_header_fn: Optional[Callable[[str, int], list[DataFileObjectFieldHeader]]],defaultrownumber: int) -> tuple[list[DataFileObject], list[DataFileObjectField]]:
    """
    Shared orchestration logic for processing datafile objects/fields/headers.

    read_objects_fn() -> list[DataFileObject]
    read_fields_fn(object_name, datafileobjectid) -> list[DataFileObjectField]
    read_header_fn(object_name, datafileobjectid) -> list[DataFileObjectFieldHeader]
    """
    saved_objects: list[DataFileObject] = []
    saved_fields: list[DataFileObjectField] = []
    saved_headers: list[DataFileObjectFieldHeader] = []

    datafileobjects = read_objects_fn()

    for obj in datafileobjects:
        obj.stagingtableschema = stagingtableschema
        obj.stagingtablename = stagingtablename

        saved_obj, inserted = db_service.upsert_datafileobject_row(obj)
        if saved_obj is None:
            continue

        saved_objects.append(saved_obj)

        if not read_fileobjectfields or read_fields_fn is None:
            continue

        fieldobjects = read_fields_fn(obj.objectname, saved_obj.datafileobjectid)
        for field in fieldobjects:
            saved_field = db_service.upsert_datafileobjectfield_row(field)
            if saved_field is not None:
                saved_fields.append(saved_field)

        # If new object was inserted, write a default headerrow record
        if inserted:
            newdatafileobjectheaderrow = DataFileObjectHeaderRow(
                datafileobjectheaderrowid=-1,
                datafileobjectid=saved_obj.datafileobjectid,
                headernum=1,
                rownumber=defaultrownumber,
                timestamp=datetime.now(),
            )
            db_service.upsert_datafileobjectheader_row(newdatafileobjectheaderrow)

        # Read and persist header row mapping AFTER fields are saved
        if read_header_fn is not None:
            header_row_mapping = read_header_fn(obj.objectname, saved_obj.datafileobjectid)
            for mapping in header_row_mapping:
                saved_mapping = db_service.upsert_datafileobjectfieldheader_row(mapping)
                if saved_mapping is not None:
                    saved_headers.append(saved_mapping)

    return saved_objects, saved_fields

def _read_excel_objects(excel_file: pd.ExcelFile,datafileid: int) -> list[DataFileObject]:
    """Read sheet names from an already-open Excel file."""
    objects = []    

    for sheet_name in excel_file.sheet_names:
        objects.append(
            DataFileObject(
                datafileobjectid=-1,
                datafileid=datafileid,
                objecttype="sheet",
                objectname=sheet_name,
                stagingtableschema=None,
                stagingtablename=None,
                skipobject=None,
                skipmessage=None,
            )
        )

    return objects

def _read_excel_fields(excel_file: pd.ExcelFile,sheet_name: str, datafileobjectid: int) -> list[DataFileObjectField]:
    """Read column headers from an already-open Excel file."""
    fields = []

    try:
        df = excel_file.parse(sheet_name = sheet_name, header=None, dtype =str)  # Just read header
        if df is not None:
            fields = get_fields_from_dataframe(df, datafileobjectid=datafileobjectid)
    except Exception as e:
        print(
            f"Error reading fields from sheet '{sheet_name}': {e}"
        )

    return fields

def _read_excel_header_row(excel_file: pd.ExcelFile,sheet_name: str,datafileobjectid: int,db_service: "DatabaseService") -> list[DataFileObjectFieldHeader]:
    """
    Read the header row for a sheet and map column ordinals to field names.
    
    - Queries DB to get the current header_row_number (defaults to 1 if not set)
    - Reads that row from the sheet
    - Generates sanitized names and de-duplication
    - Returns list of DataFileObjectFieldHeader objects ready to persist
    """
    header_row_number = _get_or_set_header_row_number(datafileobjectid, db_service)
    
    # Read the sheet with no header assumption
    df = excel_file.parse(sheet_name=sheet_name, header=None, dtype=str)
    
    # Extract the header row (convert 1-indexed to 0-indexed)
    header_row_values = _get_header_row_from_dataframe(df, header_row_number)
    return  _generate_sanitised_field_mapping(datafileobjectid, header_row_values, db_service)
                
def _read_access_objects(connection: pyodbc.Connection,datafileid: int) -> list[DataFileObject]:
    """Read table names from an already-open Access connection."""
    objects = []

    try:
        with connection.cursor() as cursor:
            table_names = [
                r.table_name
                for r in cursor.tables(tableType="TABLE")
            ]

            for table_name in table_names:
                objects.append(
                    DataFileObject(
                        datafileobjectid=-1,
                        datafileid=datafileid,
                        objecttype="table",
                        objectname=table_name,
                        stagingtableschema=None,
                        stagingtablename=None,
                        skipobject=None,
                        skipmessage=None,
                    )
                )

    except Exception as e:
        print(f"Error reading Access objects: {e}")

    return objects

def _read_access_fields(connection: pyodbc.Connection,table_name: str,datafileobjectid: int) -> list[DataFileObjectField]:
    """Read column names from tables in an already-open Access connection."""
    fields: list[DataFileObjectField] = []

    try:
        with connection.cursor() as cursor:
            table_names = [
                r.table_name
                for r in cursor.tables(tableType="TABLE")
            ]

            for table_name in table_names:
                # Fetch just the columns without reading data
                #cursor.execute(f"SELECT * FROM [{table_name}] WHERE 1=0")
                df = pd.read_sql(f"SELECT * FROM [{table_name}] WHERE 1=0", connection)
                if df is not None:
                    fields = get_fields_from_dataframe(df, datafileobjectid=datafileobjectid)
 
    except Exception as e:
        print(f"Error reading Access fields: {e}")

    return fields

def _read_access_header_row(connection: pyodbc.Connection, table_name: str, datafileobjectid: int) -> list[DataFileObjectFieldHeader]:
    """
    Read the header row for a table in an Access database without fetching any data.
    Technically there is no such thing as a header row in an Access table, but we can infer it from the column names.
    This keeps this function consistent with how we handle header rows for other types of data sources.
    """
    header_row: list[DataFileObjectFieldHeader] = []

    try:
           
        df = pd.read_sql(f"SELECT * FROM [{table_name}] WHERE 1=0", connection)
        ## the data frame will inherit the column names from the Access table, which we can use as the header row.
        ## so we don't need to use our _get_header_row_from_dataframe function for Access tables.
        if df is not None:
            header_row = _generate_sanitised_field_mapping(datafileobjectid, df.columns.tolist(), None)
    except Exception as e:
        print(f"Error reading Access header row: {e}")

    return header_row

def _read_text_objects( fp: Path, datafileid: int) -> list[DataFileObject]:
    #for this method we don't physically need to read the file, but we can add a row to DataFileObject for the CSV file itself as a "file object".

    ## object name is the file name with extension removed 
    objname = fp.stem

    return [
        DataFileObject(
        datafileobjectid=-1,  # Placeholder, should be set appropriately
        datafileid=datafileid,
        objecttype="sheet",
        objectname=objname,
        stagingtableschema=None,
        stagingtablename=None,
        skipobject=None,
        skipmessage=None,
    )]

def _read_text_fields(fp: Path, datafileobjectid: int) -> list[DataFileObjectField]:
    fields: list[DataFileObjectField] = []

    try:
        df = load_text_file_to_dataframe(fp, drop_all_null_columns=True, log_fn = None)
        if df is not None:
            fields = get_fields_from_dataframe(df, datafileobjectid=datafileobjectid)
    except Exception as e:
        print(f"Error loading text file to dataframe: {e}")
        return []

    return fields

def _read_text_header_row(fp: Path,datafileobjectid: int,db_service: "DatabaseService") -> list[DataFileObjectFieldHeader]:
    """
    Read the header row for a text file and map column ordinals to field names.
    
    - Queries DB to get the current header_row_number (defaults to 1 if not set)
    - Reads that row from the text file
    - Generates sanitized names and de-duplication
    - Returns list of DataFileObjectFieldHeader objects ready to persist
    """
    header_row_number = _get_or_set_header_row_number(datafileobjectid, db_service)
    
    # Read the text file with no header assumption
    df = load_text_file_to_dataframe(fp, drop_all_null_columns=True, log_fn = None)
    
    # Extract the header row (convert 1-indexed to 0-indexed)
    header_row_values = _get_header_row_from_dataframe(df, header_row_number)
    return  _generate_sanitised_field_mapping(datafileobjectid, header_row_values, db_service)

## Helper functions for handling header rows in text files
def _get_or_set_header_row_number(datafileobjectid: int, db_service: "DatabaseService") -> int:
    """
    Get or set the header row number for a given datafile object.
    If no header row is defined, a default header row with number 1 is created.
    Returns the header row number.  
    All files types can use this helper function.
    """
    # Get the header row number (default 1, or user-overridden value)
    header_row_objects = db_service.get_datafileheaderrow_objects_by_datafileobjectid(datafileobjectid)

    # If no header row objects are found, create a default one & upsert it to DB & cache
    if not header_row_objects:
        newheaderrowobject = DataFileObjectHeaderRow(
            datafileobjectheaderrowid=-1,
            datafileobjectid=datafileobjectid,
            headernum=1,
            rownumber=1,
            timestamp=datetime.now(),
        )
        db_service.upsert_datafileobjectheaderrow_row(newheaderrowobject)
        header_row_objects.insert(0, newheaderrowobject)
    else:
        # iterate list of objects to find where headernum = 1   
        for obj in header_row_objects:
            if obj.headernum == 1:
                header_row_objects.insert(0, header_row_objects.pop(header_row_objects.index(obj)))
                break

    header_row_number = header_row_objects[0].headernum if header_row_objects else 1
    return header_row_number

def _get_header_row_from_dataframe(df: pd.DataFrame, header_row_number: int) -> list:
    """
    Extract the header row from a DataFrame given the header row number.
    
    - Converts 1-indexed header_row_number to 0-indexed for DataFrame access
    - Returns the header row as a list of values
    """
    return df.iloc[header_row_number - 1].tolist()

def _generate_sanitised_field_mapping(datafileobjectid: int,header_row_values: list, db_service: "DatabaseService") -> list[DataFileObjectFieldHeader]:
    """
    Sanitise and de-duplicate column names in the header dictionary.
    
    - header_row_values: List of original header row values
    - Returns a dict with updated "SanitisedFieldName" ensuring uniqueness for each column ordinal
    """
    # Convert to ordinal-keyed dict for generate_column_names
    header_dict: Dict[int, Dict] = {
        i: {"OrigFieldName": val}
        for i, val in enumerate(header_row_values, start=1)
    }
    
    # Generate sanitized + de-duped names
    header_dict = generate_column_names(header_dict)
    
    # Build DataFileObjectFieldHeader objects for persistence
    mappings = []

    for ordinal, field_info in header_dict.items():

        field = db_service.get_datafileobjectfield_by_objectid_and_ordinal(datafileobjectid, ordinal)
        fieldid = field.datafileobjectfieldid
        orig = field_info["OrigFieldName"]
        new = field_info["SanitizedFieldName"]
        sanit = False if orig == new else True
        mapping = DataFileObjectFieldHeader(
            datafileobjectfieldheaderid=-1,
            datafileobjectfieldid=fieldid,
            headernum=1,
            headervalue=orig,
            sanitisedheadervalue=new,
            valuesanitised=sanit,
            timestamp=datetime.now(),
        )
        mappings.append(mapping)
    
    return mappings

def generate_column_names(header_values: Dict[int, Dict]) -> Dict[int, Dict]:
    """
    Shared logic: turn a raw header row into clean column names.
    - Pass 1: Sanitize all values (fill nulls, remove special chars)
    - Pass 2: De-duplicate by appending _occurrence_number, ensuring no collisions

    header_values is keyed by ordinal column position, each value a dict containing
    at least "OrigFieldName". This function adds "SanitizedFieldName" to each dict.
    """
    # Pass 1: Sanitize all values
    unknown_counter = 0

    for i, fieldnames in header_values.items():
        val = fieldnames.get("OrigFieldName")
        if not val or (isinstance(val, str) and val.strip() == ""):
            unknown_counter += 1

        sanitized = sanitize_column_name(val, unknown_counter)
        header_values[i]["SanitizedFieldName"] = sanitized  # preserve OrigFieldName

    # Pass 2: De-duplicate with occurrence numbering
    occurrence_count: dict[str, int] = {}
    all_sanitized_lower: set[str] = {
        v["SanitizedFieldName"].lower() for v in header_values.values()
    }  # snapshot from pass 1 — computed once, not rebuilt every iteration
    assigned_names_lower: set[str] = set()

    for i, fieldnames in header_values.items():
        sanitized = fieldnames["SanitizedFieldName"]
        sanitized_lower = sanitized.lower()

        occurrence_count[sanitized_lower] = occurrence_count.get(sanitized_lower, 0) + 1
        occurrence_num = occurrence_count[sanitized_lower]

        if occurrence_num > 1:
            candidate = f"{sanitized}_{occurrence_num}"
            while candidate.lower() in all_sanitized_lower or candidate.lower() in assigned_names_lower:
                occurrence_num += 1
                candidate = f"{sanitized}_{occurrence_num}"
            final_name = candidate
        else:
            final_name = sanitized

        header_values[i]["SanitizedFieldName"] = final_name
        assigned_names_lower.add(final_name.lower())

    return header_values

def sanitize_column_name(col: str, fallback_idx: int) -> str:
    c = str(col).strip()
    if not c:
        c = f"UnkCol_{fallback_idx}"
    c = c.replace(" ", "_")
    c = re.sub(r"[^A-Za-z0-9_]", "_", c)
    c = re.sub(r"_+", "_", c).strip("_")
    if not c:
        c = f"UnkCol_{fallback_idx}"
    return c

## End of helper functions for handling header rows in text files

def get_fields_from_dataframe(df: pd.DataFrame, datafileobjectid: int) -> list[DataFileObjectField]:
    
    inferred = infer_dataframe_sql_types_from_pandas(df, date_format_label="Auto")
    colnames = list(df.columns)
    fields: list[DataFileObjectField] = []

    for ord_ in range(1, len(df.columns) + 1):
        meta = (inferred or {}).get(ord_, {})
        newdatafield = DataFileObjectField(
        datafileobjectfieldid=-1,
        datafileobjectid=datafileobjectid,
        fieldordinal=ord_,
        fielddatatype = meta.get("sql_type"),
        fieldlength = meta.get("length"),
        fieldprecision = meta.get("precision"),
        skipfield = 1 if meta.get("skip_content", False) else 0,
        )
        fields.append(newdatafield)
    return fields

def infer_dataframe_sql_types_from_pandas(df: pd.DataFrame, date_format_label: str = "Auto") -> dict:
    out: Dict[int, Dict[str, Any]] = {}

    for i in range(1, len(df.columns) + 1):
        s = df.iloc[:, i - 1]

        # detect likely binary / OLE payloads in object columns
        if pd.api.types.is_object_dtype(s):
            non_null = s.dropna()
            sample = non_null.head(25)
            if not sample.empty and sample.map(lambda v: isinstance(v, (bytes, bytearray, memoryview))).any():
                out[i] = {
                    "sql_type": "VARBINARY(MAX)",
                    "length": 0,
                    "precision": None,
                    "skip_content": True,   # key flag
                    "reason": "binary_or_ole"
                }
                continue

        if pd.api.types.is_integer_dtype(s):
            out[i] = {"sql_type": "BIGINT", "length": 0, "precision": None, "skip_content": False}
        elif pd.api.types.is_float_dtype(s):
            out[i] = {"sql_type": "FLOAT", "length": 0, "precision": None, "skip_content": False}
        elif pd.api.types.is_bool_dtype(s):
            out[i] = {"sql_type": "BIT", "length": 0, "precision": None, "skip_content": False}
        elif pd.api.types.is_datetime64_any_dtype(s):
            out[i] = {"sql_type": "DATETIME2", "length": 0, "precision": None, "skip_content": False}
        else:
            x = infer_series_type(s, date_format_label=date_format_label)
            x["skip_content"] = False
            out[i] = x

    return out

def infer_series_type(series: pd.Series, date_format_label: str = "Auto") -> Dict[str, Any]:
    """
    Infer SQL type for a pandas Series.
    Returns:
      {"sql_type": str, "length": int|None, "precision": int|None}
    """
    # Convert to string for length checks, but keep null awareness
    non_null = series.dropna()

    # If all nulls, default to VARCHAR(10)
    if non_null.empty:
        return {"sql_type": "VARCHAR(10)", "length": 10, "precision": None}  
    
    as_raw = non_null.astype(str)

    # Try integer detection
    as_str = non_null.astype(str).str.strip()
    int_mask = as_str.str.fullmatch(r"[+-]?\d+")
    if int_mask.all():
        return {"sql_type": "BIGINT", "length": 0, "precision": None}  


    # Try float/decimal detection
    float_mask = as_str.str.fullmatch(r"[+-]?(\d+(\.\d+)?|\.\d+)")
    if float_mask.all():
        return {"sql_type": "FLOAT", "length": 0, "precision": None}

    fmt = selected_date_format_to_strptime(date_format_label)
    #print (fmt)

    # Try datetime detection
    if fmt is None:
        # Auto mode (less strict)
        #print ("Auto date parsing")
        dt_try = pd.to_datetime(non_null, errors="coerce", format="mixed")
    else:
        # Strict selected format
        #print ("Fromatted date parsing")
        dt_try = parse_dates_with_order(non_null, fmt)
        #print (dt_try)

    if dt_try.notna().all():
        #print("All values parsed as dates")
        return {"sql_type": "DATE", "length": 0, "precision": None} if date_format_label in {"YYYY-MM-DD", "DD-MM-YYYY", "MM-DD-YYYY"} else {"sql_type": "DATETIME2", "length": 0, "precision": None}

    # Fallback: VARCHAR(max observed length)
    max_len = int(as_raw.map(len).max())
    if max_len <= 0:
        max_len = 10
    # SQL Server VARCHAR max is 8000 unless VARCHAR(MAX)
    elif max_len > 8000:
        return {"sql_type": "VARCHAR(MAX)", "length": max_len, "precision": None}
    else:
        max_len = int(max_len * 1.1)  # 10% buffer
    return {"sql_type": f"VARCHAR({max_len})", "length": max_len, "precision": None}

def selected_date_format_to_strptime(label: str):
    mapping = {
        "YYYY-MM-DD": "%Y-%m-%d",
        "DD-MM-YYYY": "%d-%m-%Y",
        "MM-DD-YYYY": "%m-%d-%Y",
        "YYYY-MM-DD HH:MM:SS": "%Y-%m-%d %H:%M:%S",
    }
    return mapping.get(label)  # None for Auto

def parse_dates_with_order(non_null: pd.Series, fmt: str):
    s = normalize_date_separators(non_null)
    
    if fmt:
        return pd.to_datetime(s, format=fmt, errors="coerce")

    # Auto mode fallback
    return pd.to_datetime(s, errors="coerce", format="mixed")

def normalize_date_separators(s: pd.Series) -> pd.Series:
    # convert / or . to -, collapse repeats, trim
    out = s.astype(str).str.strip()
    out = out.str.replace(r"[/.]", "-", regex=True)
    out = out.str.replace(r"-{2,}", "-", regex=True)
    return out

####################################
####################################
## Main datafile processing function
## for reading objects and fields and header rows

def process_datafile_for_extraction(db_service: DatabaseService,fp: Path,ftype: str,subtype: str, requests: List[TableExtractRequest] ) -> Dict[int,ObjectExtraction]:
    """
    Opens a file and orchestrates the extraction of requested tables/objects into DataFrames.
    """

    try:
        if ftype == "excel":
            ext = fp.suffix.lower()
            engine_map = {
                ".xls": "xlrd",
                ".xlsx": "openpyxl", ".xlsm": "openpyxl",
                ".xltx": "openpyxl", ".xltm": "openpyxl",
                ".xlsb": "pyxlsb",
            }
            engine = engine_map.get(ext)
            if engine is None:
                print(f"⚠️ Unsupported Excel extension for {fp.name}: {ext}")
                return {}

            with pd.ExcelFile(fp, engine=engine) as excel_file:
                return _extract_objects_common(
                    db_service=db_service,
                       requests=requests,
                    extract_objects_fn=lambda sheet_name, header_row_number: _extract_excel_to_df(
                        excel_file=excel_file, sheet_name=sheet_name,
                        header_row_number=header_row_number
                    ),
                    
                )

        elif ftype == "database" and subtype == "access":
            with _open_access_connection(fp) as acc_conn:
                acc_conn.autocommit = True
                return _extract_objects_common(
                    db_service=db_service,
                    requests=requests,
                    extract_objects_fn=lambda table_name, _nothing : _extract_access_to_df(
                        connection=acc_conn, table_name=table_name
                    ),
                        
                )

        elif ftype == "text":
            return _extract_objects_common(
                db_service=db_service,
                requests=requests,
                extract_objects_fn=lambda _object_name, header_row_number: _extract_text_to_df(
                        file_path=fp, header_row_number=header_row_number
                    ),
                
            )

        else:
            raise ValueError(f"Unsupported file type: {ftype}")

    except Exception as e:
        print(f"Error processing datafile {fp}: {e}")
        return {}

## Common orchestration logic for extract datafile objects
def _extract_objects_common(db_service: DatabaseService, requests: List[TableExtractRequest] ,extract_objects_fn: Callable[[str, int], pd.DataFrame]
                            ) -> Dict[int,ObjectExtraction]:
    """
    Shared orchestration logic for extracting datafile objects/

    """
    results: Dict[int, ObjectExtraction] = {}

    for request in requests:
        datafileobjectid = request.datafileobjectid
        try:
            datafileobject = db_service.get_datafileobject_by_id(datafileobjectid)  
            header_rows = db_service.get_datafileheaderrow_objects_by_datafileobjectid(datafileobjectid)
            header_row_number = (header_rows[0].rownumber - 1) if header_rows else 0

            sheet_name = datafileobject.objectname

            df=extract_objects_fn(sheet_name, header_row_number)
            results[datafileobjectid] = ObjectExtraction(df=df)
            
        except Exception as e:
            print(f"Error extracting datafile object {datafileobjectid}: {e}")
            results[request.datafileobjectid] = ObjectExtraction(df=None,error=str(e))

    return results

def _extract_excel_to_df(excel_file: pd.ExcelFile,sheet_name: str, header_row_number: int ) -> pd.DataFrame:
    """
    Read the header row for a sheet and return the dataframe.
    
    - Queries DB to get the current header_row_number (defaults to 1 if not set)
    - Reads that row from the sheet
    - Generates sanitized names and de-duplication
    - Returns the dataframe with the correct header row applied
    """
    
    return excel_file.parse(sheet_name=sheet_name, header=header_row_number, dtype=str)

def _extract_access_to_df(connection: pyodbc.Connection,table_name: str) -> pd.DataFrame:
    """Read column names from tables in an already-open Access connection."""
    fields: list[DataFileObjectField] = []

    try:
        df = pd.read_sql(f"SELECT * FROM [{table_name}] ", connection)
 
    except Exception as e:
        print(f"Error reading Access table {table_name}: {e}")

    return df

def _extract_text_to_df(file_path: Path, header_row_number: int ) -> pd.DataFrame:
    """Read a text file into a single-column dataframe."""
    df = load_text_file_to_dataframe(file_path, drop_all_null_columns=True,  log_fn = None, header=header_row_number)
    return df

####################################
## File to dataframe loadersrs
####################################

def load_text_file_to_dataframe(file_path: Path, drop_all_null_columns: bool = True, log_fn=None, header=None) -> pd.DataFrame:
    """
    Basic parser:
    - .csv => read_csv
    - .tsv/.txt => read_csv with inferred sep (python engine, sep=None)
    - .xlsx/.xls => read_excel ## we don't do this anymore in this method
    """
    ftype, subtype  = get_ftype_subtype_from_path(file_path)

    try:
        if ftype == "text" and subtype == "csv":
            df, used_enc = read_csv_with_fallback(file_path, dtype=str, keep_default_na=True, header=header)
        elif ftype == "text":
            df, used_enc = read_csv_with_fallback(file_path, dtype=str, sep=None, engine="python", keep_default_na=True, header=header)
        else:
            raise ValueError(f"Unsupported extension for parser: {file_path.suffix.lower().lstrip('.')}")
    except ParserError:
        df, used_enc = read_text_lines_fallback(file_path)
        if log_fn:
            log_fn(f"⚠️ CSV parse failed; loaded as single-column text lines: {file_path.name}")


    if ftype == "text" and df is not None:
        if log_fn:
            log_fn(f"ℹ️ Text read using encoding={used_enc}: {file_path.name}")


    # normalize blank strings -> NA (so whitespace-only cells count as null)
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    # Sanitize/uniquify columns
    # We don't need to do this as we aren't detecting headers at this point anymore.  
    # header = None in the above read_csv calls
    """
    seen = {}
    new_cols = []
    for i, c in enumerate(df.columns, start=1):
        base = sanitize_column_name(c, i)
        if base in seen:
            seen[base] += 1
            name = f"{base}_{seen[base]}"
        else:
            seen[base] = 1
            name = base
        new_cols.append(name)
    df.columns = new_cols
    """

    if drop_all_null_columns:
        # drop columns that are entirely null
        all_null_cols = [c for c in df.columns if df[c].isna().all()]
        if all_null_cols:
            df = df.drop(columns=all_null_cols)


    return df

def load_excel_sheet_to_dataframe(file_path: Path, sheet_name: str, dtype: dict | None = None) -> pd.DataFrame:
    """
    Stand alone method for loading an Excel sheet into a pandas DataFrame with no header - i.e. raw.
    """
    ext = file_path.suffix.lower()
    engine_map = {
        ".xls": "xlrd",
        ".xlsx": "openpyxl", ".xlsm": "openpyxl",
        ".xltx": "openpyxl", ".xltm": "openpyxl",
        ".xlsb": "pyxlsb",
    }
    engine = engine_map.get(ext)
    if engine is None:
        print(f"⚠️ Unsupported Excel extension for {file_path.name}: {ext}")
        
    return pd.read_excel(file_path, sheet_name=sheet_name, dtype=dtype, keep_default_na=True, header=None)

def load_access_table_to_dataframe(file_path: Path, table_name: str, dtype: dict | None = None) -> pd.DataFrame:
    """
    Stand alone method for loading an Access table into a pandas DataFrame with no header - i.e. raw.
    """
    with _open_access_connection(file_path) as conn:
        query = f"SELECT * FROM [{table_name}]"
        df = pd.read_sql(query, conn)
    return df

####################################
## Text file loading helpers
####################################

def read_csv_with_fallback(path, **kwargs):
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    last_err = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs), enc
        except UnicodeDecodeError as e:
            last_err = e
    raise last_err

def read_text_lines_fallback(path):
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                lines = [ln.rstrip("\n\r") for ln in f]
            df = pd.DataFrame({"LineText": lines})
            return df, enc
        except UnicodeDecodeError as e:
            last_err = e
    raise last_err

def get_operable_filetypes() -> Dict[str, dict]:
    settings = DEFAULT_SETTINGS

    raw = settings.get("operable_filetypes", {})
    if not isinstance(raw, dict):
        return {}

    # normalize keys to extension without dot, lowercase
    out: dict[str, dict] = {}
    for ext, meta in raw.items():
        if not isinstance(ext, str) or not isinstance(meta, dict):
            continue
        k = ext.lower().lstrip(".")
        out[k] = {
            "type": meta.get("type"),
            "subtype": meta.get("subtype"),
        }
    return out

def get_ftype_subtype_from_path(file_path: Path) -> tuple[str | None, str | None]:
    ext = file_path.suffix.lower().lstrip(".")
    operable = get_operable_filetypes()
    meta = operable.get(ext)
    if not meta:
        return None, None
    return (meta.get("type") or "").lower(), (meta.get("subtype") or "").lower()

############# Methods below this line added for extraction

def prepare_dataframe_for_insert(df: pd.DataFrame, col_types: Dict[str, str], date_format_label: str = "Auto") -> pd.DataFrame:
    out = df.copy()
    fmt = selected_date_format_to_strptime(date_format_label)

    for col, sql_type in col_types.items():
        if col not in out.columns:
            continue

        s = out[col]

        if sql_type == "DATE":
            dt = parse_dates_with_order(s.dropna(), fmt)
            # re-align to full index
            parsed = pd.Series(index=s.index, dtype="object")
            parsed.loc[s.dropna().index] = dt.dt.date
            out[col] = parsed.where(parsed.notna(), None)

        elif sql_type == "DATETIME2":
            dt = parse_dates_with_order(s.dropna(), fmt)
            parsed = pd.Series(index=s.index, dtype="object")
            parsed.loc[s.dropna().index] = dt.dt.to_pydatetime()
            out[col] = parsed.where(parsed.notna(), None)

        elif sql_type in ("BIGINT",):
            out[col] = pd.to_numeric(s, errors="coerce").astype("Int64").where(lambda x: x.notna(), None)

        elif sql_type in ("FLOAT",):
            out[col] = pd.to_numeric(s, errors="coerce").where(lambda x: x.notna(), None)

        else:
            # VARCHAR etc.
            out[col] = s.where(pd.notna(s), None)

    return out

def sql_safe_header(name: str, max_len: int = 128) -> str:
    # example policy; adjust to your rules
    s = (name or "").strip()
    if not s:
        s = "Column"
    s = s.replace("\x00", "")
    s = s.replace("[", "(").replace("]", ")")
    s = s[:max_len]
    return s

def json_default(self,o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)  # safe fallback

def safe_text(self, v):
    if v is None:
        return None
    if isinstance(v, bytes):
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return v.decode(enc)
            except UnicodeDecodeError:
                pass
        return v.decode("utf-8", errors="replace")
    try:
        return str(v)
    except Exception:
        return repr(v)