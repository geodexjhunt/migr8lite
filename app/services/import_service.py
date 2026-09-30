## Import Workflow logic here
## The service should not import QWidget, QMessageBox, QFileDialog, or update labels.
import re
from PyQt6.QtCore import QObject, pyqtSignal
from datetime import date, datetime
from typing import Dict, Tuple, Any
from collections import defaultdict
from pathlib import Path
import pandas as pd
from pandas.errors import ParserError
from time import perf_counter

from app.models.migration_context import MigrationContext
from app.models.system_model import DataFile, DataFileObject, DataFileObjectField, JobFile, JobRunVersion, Job
from app.services.db_service import DatabaseService
from app.services.file_service import process_datafile, scan_subfolders, collect_all_files, sha256_file
from config.config import Config
from app.constants import SQLSERVER_MAX_IDENTIFIER_LEN, DEFAULT_SETTINGS


class ImportService(QObject):
    """Runs import operations using shared application services."""
    log_appended = pyqtSignal(str)
    def __init__(
        self,
        config: Config,
        context: MigrationContext,
        db_service: DatabaseService,
    ) -> None:
        super().__init__()
        self.config = config # config contains database connection settings and other configuration options including system schema & table name mapping
        self.context = context # contains current task and current selected table
        self.db_service = db_service # contains all database related operations and connections - anything sql related should be called from here

        self.settings: dict[str, Any] = DEFAULT_SETTINGS
    ## Import service will achieve two main objectives:
    ## 1. Scan files in folders and attempt to read their headers.
    ## 2. Import  file data into staging tables for further processing.

    def append_log(self, message: str) -> None:
        """Append a message to the import log by emitting to the import_tab."""
        self.log_appended.emit(message)

    def run_file_scan(self, jobrunversionid) -> None:
        """
        Run step 1 which is to scan and import all files names & object names into the System DB
        """
        ## All pre-run validation is conducted within the import_tab
        ## File counting is handeled by file service.

        # 2) scan/write found folders
                    
        initial_folders = self.db_service.get_initial_folders(jobrunversionid)
        found = scan_subfolders(initial_folders)
        ## we should only return the folders that were actually inserted!
        inserted_folders = self.db_service.upsert_found_folders(jobrunversionid, found)
        self.append_log(f"📁 Found folders scanned={len(found)}, inserted={len(inserted_folders)}")

        # optional: map found folder path -> folderid for JobFile FK
        folderid_map = self.db_service.get_found_folderid_map(jobrunversionid)
        self.append_log(f"📁 Folder ID Map Completed")

        # 3) write DataFile + JobFile inventory rows
        inventoried = 0
        for folder in initial_folders:
            p = Path(folder)
            if not p.exists() or not p.is_dir():
                raise ValueError(f"Initial folder does not exist: {folder}")
                # return is no longer needed as the exception will halt execution

            files_by_ext = collect_all_files(p)

            for ext, files in files_by_ext.items():
                for fp in files:
                    file_hash = sha256_file(fp)
                    file_size = fp.stat().st_size
                    newdatafile = DataFile(
                        datafileid=-1,
                        filetype=ext.lstrip(".").lower(),
                        hashsha256=file_hash,
                        filesizebytes=file_size
                    )

                    datafileid, is_new = self.db_service.upsert_datafile_row(newdatafile)

                    if is_new == False:
                        self.append_log(f"ℹ️ DataFile for {fp.name} already exists with hash {newdatafile.hashsha256}.")

                    st = fp.stat()
                    created_ts = getattr(st, "st_birthtime", None)
                    if created_ts is None:
                        created_ts = st.st_ctime

                    created_dt = datetime.fromtimestamp(created_ts)
                    modified_dt = datetime.fromtimestamp(st.st_mtime)

                    # best effort folderid lookup from parent path
                    folderid = folderid_map.get(self.normalize_path_key(fp.parent))

                    if folderid is None:
                        self.append_log(f"⚠️ No folderid for parent path: {fp.parent}")

                    newjobfile = JobFile(
                        jobfileid=-1,
                        datafileid=datafileid,
                        jobrunversionid=jobrunversionid,
                        newfile=is_new,
                        folderid=folderid,
                        filename=fp.name,
                        filecreateddate=created_dt,
                        filemodifieddate=modified_dt
                    )
                    file_status: str = ""
                    newjobfile, file_status = self.db_service.upsert_jobfile_row(newjobfile)
                         
                    if file_status == "error":
                        self.append_log(f"⚠️ Failed to insert job file row for: {fp.name}") 
                        continue
                    elif file_status == "no update":
                        self.append_log(f"ℹ️ No update - Job file row already exists for: {fp.name} and jobrunversionid: {jobrunversionid}")
                        inventoried += 1
                        continue          
                    elif file_status == "updated":
                        self.append_log(f"ℹ️ Updated - Job file row already exists for: {fp.name} and jobrunversionid: {jobrunversionid}")
                        inventoried += 1
                        continue       
                    elif file_status == "inserted":
                        self.append_log(f"ℹ️ Inserted - Job file: {fp.name} and jobrunversionid: {jobrunversionid}")
                        inventoried += 1
                        continue              
      

        self.append_log(f"🧾 File inventory written: {inventoried} row(s) to JobFile")

        ## end of step one

    def run_file_object_scan(self, jobrunversionid: int, read_fileobjectfields: bool) -> None:
            self.process_file_objects(jobrunversionid,read_fileobjectfields)
                
            self.append_log("✅ Read mode complete (metadata/catalog written, no data imported).")
            return

    def process_file_objects(self,  jobrunversionid: int,read_fileobjectfields:bool):
        ## Process Excel and Access files to read their sheets/tables and store metadata in JobFile.
        ## For CSV files, we don't have sub-objects, but we add them to the file object table none the less.
        # 1) Get all distinct datafileids within the JobFile rows for this runversionid
        ### Because the same datafile may be used in multiple JobFile rows (e.g., same file in different folders), we want to avoid duplicates.
        ### but we do need to select at least one file path to use for reading the file object (sheet/table) names. We'll just use the first one we find.
        ### Added a left join to datafileobjects to only get datafileids that don't already have a file object row.
        self.append_log("📖 Reading file objects (Excel sheets, Access tables)..."  )
        operable = self.get_operable_filetypes()
        exts = sorted(operable.keys())  # e.g. ['accdb','csv','mdb','txt','xls','xlsx']
        if not exts:
            self.append_log("⚠️ No operable filetypes configured.")
            return

        jobrunversion: JobRunVersion = self.db_service.get_jobrunversion_by_id(jobrunversionid) 
        job: Job = self.db_service.get_job_by_id(jobrunversion.jobid)

        stagingschema = job.schemaname
        stagingprefix = job.jobprefix


        rows = self.db_service.get_datafiles_by_jobrunversionid_and_ext(jobrunversionid, exts)
      

        if rows is None or len(rows) == 0:
            self.append_log("⚠️ No JobFile rows found for this runversionid, skipping file object read.")
            return
        else:   
            self.append_log(f"📖 Found {len(rows)} distinct datafileid(s) to read file objects for.")

        total_dfos = []
        total_dfofs = []

        for row in rows:    
            
            datafileid = row["datafileid"]
            df = self.db_service.get_datafile_by_id(datafileid)
            first_file_path = self.normalize_path_key(row["firstfilepath"])

            if not first_file_path:
                self.append_log(f"⚠️ No file path found for DataFileID {datafileid}, skipping.")
                continue

            fp = Path(first_file_path)
            if not fp.exists():
                self.append_log(f"⚠️ File does not exist: {fp}, skipping.")
                continue

            ext = fp.suffix.lower().lstrip(".")
            meta = operable.get(ext)

            if not meta:
                self.append_log(f"⏭️ Unsupported extension for file object read: .{ext} ({fp.name})")
                return  # or continue

            ftype = (meta.get("type") or "").lower()
            subtype = (meta.get("subtype") or "").lower()

            fieldobjects: list[DataFileObjectField] = [] 
            dfos: list[DataFileObject] = []

            datafileobjecttemplate: DataFileObject = DataFileObject(
                datafileid=datafileid,
                stagingtableschema=stagingschema,
                stagingtablename=stagingprefix,
                datafileobjectid=-1,
                objecttype=ftype,
                objectname="unknown",
            )
             

            dfos, fieldobjects = process_datafile(self.db_service, fp, datafileid, ftype, subtype, read_fileobjectfields, datafileobjecttemplate)

            total_dfos.extend(dfos)
            total_dfofs.extend(fieldobjects)

        self.append_log(f"📖 Added {len(total_dfos)} datafileobjects to cache.")
        self.append_log(f"📖 Added {len(total_dfofs)} datafileobjectfields to cache.")
     
    def get_operable_filetypes(self) -> Dict[str, dict]:
        settings = self.settings
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

    def normalize_path_key(self, pathlike) -> str:
        return str(Path(pathlike).resolve()).replace("\\", "/").rstrip("/").lower()


###### Above this line are confirmed to be used in this class
  
  
