## Import Workflow logic here
## The service should not import QWidget, QMessageBox, QFileDialog, or update labels.
import re
from datetime import date, datetime
from typing import Dict, Tuple, Any
from collections import defaultdict
from pathlib import Path
import pandas as pd
from pandas.errors import ParserError
from time import perf_counter

from app.models.migration_context import MigrationContext
from app.services.db_service import DatabaseService
from config.config import Config
from app.constants import SQLSERVER_MAX_IDENTIFIER_LEN


class ImportService:
    """Runs import operations using shared application services."""

    def __init__(
        self,
        config: Config,
        context: MigrationContext,
        db_service: DatabaseService,
    ) -> None:
        self.config = config
        self.context = context
        self.db_service = db_service

    def run_import(self, import_config: dict[str, Any]) -> None:
        """Run an import using settings collected by ImportTab."""
        task_id = self.context.current_task_id

        if task_id is None:
            raise ValueError("A migration task must be selected before importing.")

        print(f"Running import for task: {task_id}")
        print(f"Import configuration: {import_config}")

        # Call the migrated import steps here:
        #
        # source_file = import_config["source_file"]
        # rows = self._read_source_file(source_file)
        # self._validate_rows(rows, import_config)
        # self._create_staging_table(import_config)
        # self._save_rows(rows, task_id, import_config)


    

## Functions and methods below this line have been copied from app.py of the easycsvimporter.  
## leading underscores have been removed from names if they existed before.

def json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)  # safe fallback

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

def normalize_date_separators(s: pd.Series) -> pd.Series:
    # convert / or . to -, collapse repeats, trim
    out = s.astype(str).str.strip()
    out = out.str.replace(r"[/.]", "-", regex=True)
    out = out.str.replace(r"-{2,}", "-", regex=True)
    return out

def parse_dates_with_order(non_null: pd.Series, fmt: str):
    s = normalize_date_separators(non_null)
    
    if fmt:
        return pd.to_datetime(s, format=fmt, errors="coerce")

    # Auto mode fallback
    return pd.to_datetime(s, errors="coerce")

def infer_dataframe_sql_types(df: pd.DataFrame, date_format_label: str = "Auto") -> Dict[str, str]:
    out: Dict[int, Dict[str, Any]] = {}
    for i, col in enumerate(df.columns, start=1):
        out[i] = infer_series_type(df.iloc[:, i - 1], date_format_label=date_format_label)
    return out

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

def load_file_to_dataframe(file_path: Path, drop_all_null_columns: bool = True, log_fn=None) -> pd.DataFrame:
    """
    Basic parser:
    - .csv => read_csv
    - .tsv/.txt => read_csv with inferred sep (python engine, sep=None)
    - .xlsx/.xls => read_excel ## we don't do this anymore in this method
    """
    operable = get_operable_filetypes()
    ext_path = file_path.suffix.lower().lstrip(".")
    meta = operable.get(ext_path)
    if not meta:
        raise ValueError(f"Unsupported extension for parser: {ext_path}")
        return
    
    ftype = (meta.get("type") or "").lower()
    subtype = (meta.get("subtype") or "").lower()

    try:
        if ftype == "text" and subtype == "csv":
            df, used_enc = read_csv_with_fallback(file_path, dtype=str, keep_default_na=True)
        elif ftype == "text" and subtype is None:
            df, used_enc = read_csv_with_fallback(file_path, dtype=str, sep=None, engine="python", keep_default_na=True)
        elif ftype == "excel":
            df = pd.read_excel(file_path, dtype=str)
            used_enc = None
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

def get_incremented_table_name(base_name: str, schema: str, max_len: int = SQLSERVER_MAX_IDENTIFIER_LEN ) -> str:
    """
    If base exists, find next free: base_1, base_2, ...
    """
    i = 1
    while True:
        suffix = f"_{i}"
        candidate = f"{base_name[:max_len-len(suffix)]}{suffix}"
        if not self.db_service.table_exists(schema, candidate):
            return candidate
        i += 1

def get_operable_filetypes() -> Dict[str, dict]:
    settings = load_settings()
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

def get_object_exceptions() -> set[str]:
    s = load_settings()
    raw = s.get("object_exceptions", [])
    if not isinstance(raw, list):
        return set()
    return {str(x).strip().lower() for x in raw if str(x).strip()}

def normalize_path_key(pathlike) -> str:
    return str(Path(pathlike).resolve()).replace("\\", "/").rstrip("/").lower()

def parse_extensions(value) -> list[str]:
    """
    Accepts:
    - '.csv'
    - '.csv,.xlsx,.accdb'
    - 'csv, xlsx, accdb'
    - list input
    Returns normalized list like ['.csv', '.xlsx', '.accdb'].
    """
    if value is None:
        return []

    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value).split(",")

    out = []
    seen = set()
    for item in raw_items:
        ext = str(item).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        if ext not in seen:
            seen.add(ext)
            out.append(ext)

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

def safe_text(v):
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