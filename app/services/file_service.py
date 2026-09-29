
#### File Service Module
#### Provides functionality for handling file operations within the application.
from dataclasses import fields
import gc
import hashlib
import os
from pathlib import Path
import re
import time
from typing import Any, Dict
from arrow import ParserError
import pandas as pd 
from app.models.system_model import DataFile, DataFileObject, DataFileObjectField
from app.services.db_service import DatabaseService
import pyodbc
from app.constants import DEFAULT_SETTINGS


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

def sha256_file(fp: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with fp.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

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

def process_datafile(db_service: DatabaseService,fp: Path,datafileid: int, ftype: str,subtype: str, read_fileobjectfields: bool = True, datafileobjecttemplate: DataFileObject | None = None) -> tuple[list[DataFileObject], list[DataFileObjectField]]:
    """
    Read all objects and optionally all fields from a datafile.
    Opens the file once and passes it to read methods.
    """
    saved_objects: list[DataFileObject] = []
    saved_fields: list[DataFileObjectField] = []
    datafileobjects = []
    fieldobjects = []

    if datafileobjecttemplate is not None:
        stagingtableschema = datafileobjecttemplate.stagingtableschema
        stagingtablename = datafileobjecttemplate.stagingtablename
    else:
        stagingtableschema = ""
        stagingtablename = ""   
    
    try:
        if ftype == "excel":
            ext = fp.suffix.lower()
            if ext == ".xls":
                engine = "xlrd"
            elif ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
                engine = "openpyxl"
            elif ext == ".xlsb":
                engine = "pyxlsb"
            else:
                print(f"⚠️ Unsupported Excel extension for {fp.name}: {ext}")
                return [], []

            with pd.ExcelFile(fp, engine=engine) as excel_file:
                datafileobjects = _read_excel_objects(
                    excel_file=excel_file,
                    datafileid=datafileid, 
                )
                for obj in datafileobjects:
                    obj.stagingtableschema = stagingtableschema
                    obj.stagingtablename = stagingtablename

                    saved_obj = db_service.upsert_datafileobject_row(obj)
                    if saved_obj is not None:
                        saved_objects.append(saved_obj)

                        if read_fileobjectfields:
                            fieldobjects = _read_excel_fields(
                                excel_file=excel_file,
                                sheet_name=obj.objectname,
                                datafileobjectid=saved_obj.datafileobjectid,
                            )
                            for field in fieldobjects:
                                saved_field = db_service.upsert_datafileobjectfield_row(field)
                                if saved_field is not None:
                                    saved_fields.append(saved_field)

        elif ftype == "database" and subtype == "access":

            with _open_access_connection(fp) as acc_conn:
                acc_conn.autocommit = True
                datafileobjects = _read_access_objects(
                    connection=acc_conn,
                    datafileid=datafileid,
                    
                )
                for obj in datafileobjects:
                    obj.stagingtableschema = stagingtableschema
                    obj.stagingtablename = stagingtablename

                    saved_obj = db_service.upsert_datafileobject_row(obj)
                    if saved_obj is not None:
                        saved_objects.append(saved_obj)              
                        if read_fileobjectfields:
                            fieldobjects = _read_access_fields(
                                connection=acc_conn,
                                table_name= saved_obj.objectname,
                                datafileobjectid=saved_obj.datafileobjectid,
                            )
                            for field in fieldobjects:
                                saved_field = db_service.upsert_datafileobjectfield_row(field)
                                if saved_field is not None:
                                    saved_fields.append(saved_field)

        elif ftype == "text":
            datafileobjects = _read_text_objects(
                fp=fp,
                datafileid=datafileid,
                
            )
            for obj in datafileobjects:
                obj.stagingtableschema = stagingtableschema
                obj.stagingtablename = stagingtablename
                saved_obj = db_service.upsert_datafileobject_row(obj)
                if saved_obj is not None:
                    saved_objects.append(saved_obj)   
                    if read_fileobjectfields:
                        fieldobjects = _read_text_fields(
                            fp=fp,
                            datafileobjectid=saved_obj.datafileobjectid,
                        )
                        for field in fieldobjects:
                            saved_field = db_service.upsert_datafileobjectfield_row(field)
                            saved_fields.append(saved_field)
        else:
            raise ValueError(
                f"Unsupported file type: {ftype}"
            )

    except Exception as e:
        print(f"Error processing datafile {fp}: {e}")
        return [], []

    return saved_objects, fieldobjects

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
        df = excel_file.parse(sheet_name)  # Just read header
        if df is not None:
            fields = get_fields_from_dataframe(df, datafileobjectid=datafileobjectid)
    except Exception as e:
        print(
            f"Error reading fields from sheet '{sheet_name}': {e}"
        )

    return fields

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
        dt_try = pd.to_datetime(non_null, errors="coerce")
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
    return pd.to_datetime(s, errors="coerce")

def normalize_date_separators(s: pd.Series) -> pd.Series:
    # convert / or . to -, collapse repeats, trim
    out = s.astype(str).str.strip()
    out = out.str.replace(r"[/.]", "-", regex=True)
    out = out.str.replace(r"-{2,}", "-", regex=True)
    return out

def load_text_file_to_dataframe(file_path: Path, drop_all_null_columns: bool = True, log_fn=None) -> pd.DataFrame:
    """
    Basic parser:
    - .csv => read_csv
    - .tsv/.txt => read_csv with inferred sep (python engine, sep=None)
    - .xlsx/.xls => read_excel ## we don't do this anymore in this method
    """
    operable = get_operable_filetypes()
    ext_path = file_path.suffix.lower().lstrip(".").rstrip()
    meta = operable.get(ext_path)
    if meta is None:
        raise ValueError(f"Unsupported extension for parser: {ext_path}")
    
    ftype = (meta.get("type") or "").lower()
    subtype = (meta.get("subtype") or "").lower()

    try:
        if ftype == "text" and subtype == "csv":
            df, used_enc = read_csv_with_fallback(file_path, dtype=str, keep_default_na=True)
        elif ftype == "text":
            df, used_enc = read_csv_with_fallback(file_path, dtype=str, sep=None, engine="python", keep_default_na=True)
        else:
            raise ValueError(f"Unsupported extension for parser: {ext_path}")
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

    if drop_all_null_columns:
        # drop columns that are entirely null
        all_null_cols = [c for c in df.columns if df[c].isna().all()]
        if all_null_cols:
            df = df.drop(columns=all_null_cols)


    return df

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

def sanitize_column_name(col: str, fallback_idx: int) -> str:
    c = str(col).strip()
    if not c:
        c = f"column_{fallback_idx}"
    c = c.replace(" ", "_")
    c = re.sub(r"[^A-Za-z0-9_]", "_", c)
    c = re.sub(r"_+", "_", c).strip("_")
    if not c:
        c = f"column_{fallback_idx}"
    return c

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