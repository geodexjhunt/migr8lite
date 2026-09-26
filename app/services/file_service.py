
#### File Service Module
#### Provides functionality for handling file operations within the application.
import gc
import hashlib
import os
from pathlib import Path
import time
import pandas as pd 
from app.models.system_model import DataFileObject, DataFileObjectField
import pyodbc

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

        outstring.extend(log_extension_summary(None, p, files_by_ext))
        merge_counts(grand_totals_by_ext, files_by_ext)

    outstring.extend(log_extension_grand_totals(None, grand_totals_by_ext))
    
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


def read_text_file_objects( fp: Path, datafileid: int, read_fileobjectfields: bool) -> DataFileObject:
    #for this method we don't physically need to read the file, but we can add a row to DataFileObject for the CSV file itself as a "file object".
    ##### Add logic here to scrape field names if read_fileobjectfields is True
    fieldobjects = []       
    if read_fileobjectfields:   
        ## do the scraping here - I need to migrate those callables.
        pass

    return DataFileObject(
        datafileobjectid=-1,  # Placeholder, should be set appropriately
        datafileid=datafileid,
        objecttype="sheet",
        objectname=fp.name,
        stagingtableschema=None,
        stagingtablename=None,
        skipobject=None,
        skipmessagge=None,
    )

def read_excel_file_objects( fp: Path, datafileid: int, read_fileobjectfields: bool) -> DataFileObject:
    fieldobjects = []  
    ext = fp.suffix.lower()
    if ext == ".xls":
        engine = "xlrd"
    elif ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        engine = "openpyxl"
    elif ext == ".xlsb":
        engine = "pyxlsb"
    else:
        print(f"⚠️ Unsupported Excel extension for {fp.name}: {ext}")
        return
    err = 0
    try:
        xls = pd.ExcelFile(fp, engine=engine)
        for sheet_name in xls.sheet_names:
            ##### Add logic here to scrape field names if read_fileobjectfields is True
            if read_fileobjectfields:   
                ## do the scraping here - I need to migrate those callables.
                pass

            return DataFileObject(
                datafileobjectid=-1,  # Placeholder, should be set appropriately
                datafileid=datafileid,
                objecttype="sheet",
                objectname=sheet_name,
                stagingtableschema=None,
                stagingtablename=None,
                skipobject=None,
                skipmessagge=None,
            )
    except ImportError as e:
        message = f"❌ Missing dependency for {fp.name} ({engine}): {e}"
        print(message)
        err = -1
    except Exception as e:
        message = f"❌ Excel read failed: {fp} | {e}"
        print(message)
        err = -1

    if err == -1:
        return DataFileObject(
                datafileobjectid=-1,  # Placeholder, should be set appropriately
                datafileid=datafileid,
                objecttype="sheet",
                objectname=sheet_name,
                stagingtableschema=None,
                stagingtablename=None,
                skipobject=1,
                skipmessagge=message
            )


def read_access_file_objects( fp: Path, datafileid: int, read_fileobjectfields: bool) -> list[DataFileObject]:

    fileobjects = []
    fieldobjects = []

    for attempt in (1,2):
        try:
            with _open_access_connection(fp)  as acc_conn:
                acc_conn.autocommit = True
                with acc_conn.cursor() as acc_cur:

                    table_names = [r.table_name for r in acc_cur.tables(tableType="TABLE")]

                for src_table in table_names:
                    fileobjects.append(DataFileObject(
                        datafileobjectid=-1,  # Placeholder, should be set appropriately    
                        datafileid=datafileid,
                        objecttype="table",
                        objectname=src_table,
                        stagingtableschema=None,
                        stagingtablename=None,
                        skipobject=None,
                        skipmessagge=None,
                    ))

                    ##### Add logic here to scrape field names if read_fileobjectfields is True
                    if read_fileobjectfields:   
                        ## do the scraping here - I need to migrate those callables.
                        pass

                    
                return fileobjects
            
        except Exception as e:
            msg = str(e)

            if "Too many client tasks" in msg and attempt == 1:
                print(f"⚠️ Access read failed for {fp.name} (attempt {attempt}): {e}. Retrying after cleanup...")
                gc.collect()
                time.sleep(2)
                continue
            else:
                print(f"⚠️ Error reading Access file objects for {fp.name}: {e}")
            return []

def _open_access_connection(self, fp: Path):
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
