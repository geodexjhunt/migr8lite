"""Database service for MSSQL operations."""

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
import pyodbc
from pathlib import Path


from app.models.system_model import DataFileObject, DataFile, DataFileObjectField, JobFile, JobFolder, JobRunVersion 
from config.config import Config
from PyQt6.QtCore import pyqtSignal, QObject

class DatabaseConnectionError(Exception):
    pass

class DatabaseService(QObject):
    table_cache_changed = pyqtSignal()
    datafile_cache_changed = pyqtSignal()
    jobfile_cache_changed = pyqtSignal()
    datafileobject_cache_changed = pyqtSignal()
    datafileobjectfield_cache_changed = pyqtSignal()
    jobfolder_cache_changed = pyqtSignal()
    importtab_log_append = pyqtSignal(str)    
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._connection = None


        self._user_defined_schemas: List[Dict] = []
        self._all_tables_info: List[Dict] = []
        self._table_lookup: set[tuple[str, str]] = set()
        # Datafile caching
        self._datafiles_by_hash: dict[str, DataFile] = {}
        self._datafiles_by_id: dict[int, DataFile] = {}

        # JobFile caching: keyed by (jobrunversionid, folderid, filename) tuple
        self._jobfiles_by_composite_key: dict[tuple[int, int, str], JobFile] = {}

        # Secondary index: keyed by jobfileid for direct lookup
        self._jobfiles_by_id: dict[int, JobFile] = {}

        # Job Folder Caching
        self._jobfolders_by_id: dict[int, JobFolder] = {}
        self._jobfolders_by_path: dict[str, JobFolder] = {}
    
        # Datafile object caching
        self._datafileobjects_by_id: dict[int, DataFileObject] = {}

        # Datafile object field caching
        self._datafileobjectfields_by_id: dict[int, DataFileObjectField] = {}



        ## tables are stored as schema.tablename 
        ## to be able to wrap them in square brackets we need to insert square brackets around the period
        ## that logic has been moved to the get function of the config property
        self.jobtable = config.system_management_config.get("job_table")
        self.jobfiletable = config.system_management_config.get("jobfile_table")
        self.datafileobjecttable = config.system_management_config.get("datafileobject_table")
        self.datafiletable = config.system_management_config.get("datafile_table")
        self.jobrunversiontable = config.system_management_config.get("jobrunversion_table")
        self.jobfolderstable = config.system_management_config.get("jobfolders_table")
        self.datafileobjectfieldtable = config.system_management_config.get("datafileobjectfield_table")

    def build_connection_string(self) -> str:
        db_config = self.config.database_config
        server = db_config.get("server", "localhost")
        database = db_config.get("database")
        driver = db_config.get("driver", "ODBC Driver 17 for SQL Server")
        trusted = db_config.get("trusted_connection", True)
        
        if not database:
            raise DatabaseConnectionError("Database name not configured")
        
        parts = [f"DRIVER={{{driver}}}", f"SERVER={server}", f"DATABASE={database}"]
        if trusted:
            parts.append("Trusted_Connection=yes")
        else:
            username = db_config.get("username")
            password = db_config.get("password")
            if username and password:
                parts.extend([f"UID={username}", f"PWD={password}"])
        return ";".join(parts)
    
    def connect(self) -> None:
        try:
            self._connection = pyodbc.connect(self.build_connection_string())
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to connect: {e}") from e
    
    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
            
    def test_connected(self) -> bool:
        if self._connection:
            return True
        else:
            return False

    @contextmanager
    def get_cursor(self):
        if not self._connection:
            self.connect()
        cursor = self._connection.cursor()
        try:
            yield cursor
            self._connection.commit()
        except:
            self._connection.rollback()
            raise
        finally:
            cursor.close()
    
    def execute_query(self, query: str, params: Optional[tuple] = None, fetchone: bool = False) -> List[Dict]:
        with self.get_cursor() as cursor:
            #print(f"DEBUG: Pre-Execute query: {query} with params: {params or ()}")
            cursor.execute(query, params or ())
            columns = [desc[0] for desc in cursor.description]
            if fetchone:
                row = cursor.fetchone()
                return [dict(zip(columns, row))] if row else []
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        
    def execute_returning_one(self,query: str,params: Optional [tuple] = None) -> dict[str, Any] | None:
        """Execute a statement with OUTPUT and return one result row."""
        with self.get_cursor() as cursor:
            #print(f"DEBUG: Pre-Execute DML with OUTPUT : {query} with params: {params or ()}")
            cursor.execute(query, params or ())

            columns = [description[0] for description in cursor.description]
            row = cursor.fetchone()

            return dict(zip(columns, row)) if row else None

    def execute_dml(self,query: str,params: Optional[tuple] = None ) -> int:
        """Execute INSERT, UPDATE, or DELETE and return the affected row count."""
        try:
            with self.get_cursor() as cursor:
                #print(f"DEBUG: Pre-Execute DML: {query} with params: {params or ()}")
                cursor.execute(query, params or ())
                return cursor.rowcount       
        except pyodbc.Error as e:
            print(f"DEBUG: DML execution failed with error:{e}")

    def get_schemas_info(self) -> List[Dict]:
        query = "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA"
        return self.execute_query(query)

    def get_user_defined_schemas_info(self) -> List[Dict]:
        query = "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME NOT IN ('INFORMATION_SCHEMA', 'sys') AND SCHEMA_NAME NOT LIKE 'db[_]%'"
        return self.execute_query(query)

    def get_all_tables_info_for_schemas(self, schemas: List[str]) -> List[Dict]:
        query = "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA IN ({})".format(
            ",".join("?" for _ in schemas)
        )
        return self.execute_query(query, tuple(schemas))

    def get_tables_info(self, schema: str) -> List[Dict]:
        query = "SELECT TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ?"
        return self.execute_query(query, (schema,))
    
    def get_columns_info(self, schema: str, table: str) -> List[Dict]:
        query = """
                SELECT COLUMN_NAME, DATA_TYPE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
                """
        return self.execute_query(query, (schema, table))

    def get_table_primary_keys(self, schema: str, table: str) -> List[str]:
        """Get primary key column names for a table."""
        query = """
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND CONSTRAINT_NAME LIKE 'PK%'
        ORDER BY ORDINAL_POSITION
        """
        results = self.execute_query(query, (schema, table))
        return [r['COLUMN_NAME'] for r in results]

    def get_dropdown_values(self, ref_schema: str, ref_table: str, 
                            ref_column_key: str, ref_column_desc: str) -> List[Dict]:
        """Fetch lookup values for a dropdown."""
        query = f"SELECT DISTINCT [{ref_column_key}] as refkey, [{ref_column_desc}] as refdesc FROM [{ref_schema}].[{ref_table}] ORDER BY [{ref_column_key}]"
        print(f"DEBUG: Dropdown query: {query}")
        return self.execute_query(query)

    def update_row(self, schema: str, table: str, primary_keys: Dict[str, Any], 
                updated_values: Dict[str, Any]) -> bool:
        """Update a single row using primary keys as WHERE clause."""
        print(f"DEBUG: update_row() called")
        print(f"DEBUG: Table: {schema}.{table}")
        print(f"DEBUG: Primary keys: {primary_keys}")
        print(f"DEBUG: Updated values: {updated_values}")
        
        try:
            # Build SET clause
            set_clause = ", ".join([f"[{col}] = ?" for col in updated_values.keys()])
            
            # Build WHERE clause from primary keys
            where_clause = " AND ".join([f"[{col}] = ?" for col in primary_keys.keys()])
            
            query = f"UPDATE [{schema}].[{table}] SET {set_clause} WHERE {where_clause}"
            params = tuple(updated_values.values()) + tuple(primary_keys.values())
            
            print(f"DEBUG: SQL Query: {query}")
            print(f"DEBUG: Parameters: {params}")
            
            cursor = self._connection.cursor()
            cursor.execute(query, params)
            self._connection.commit()
            rows_affected = cursor.rowcount
            
            print(f"DEBUG: Rows affected: {rows_affected}")
            if rows_affected == 0:
                print(f"DEBUG: WARNING - No rows matched the WHERE clause")
            
            cursor.close()
            return True
            
        except Exception as e:
            print(f"DEBUG: update_row() EXCEPTION: {str(e)}")
            print(f"DEBUG: Exception type: {type(e).__name__}")
            import traceback
            print(f"DEBUG: Traceback:\n{traceback.format_exc()}")
            self._connection.rollback()
            raise

    def get_migration_tasks(self) -> List[Dict]:
        """Fetch all migration tasks."""
        query = f"SELECT * FROM {self.jobtable} Order By jobid Asc"
        return self.execute_query(query)

    def get_tables_for_task(self, task_id: int) -> List[Dict]:
        """Fetch all tables associated with a specific migration task."""
        query = f"""
        SELECT jf.* FROM {self.jobfiletable} jf 
        INNER JOIN {self.jobrunversiontable} jrv 
        ON jf.[jobrunversionid] = jrv.[jobrunversionid] 
        WHERE jrv.[runversion] = 1 and jrv.[jobid] = ? Order By [jobfileid] Asc
        """
        return self.execute_query(query, (task_id,))    

    def get_jobfiles_for_task(self, task_id: int) -> List[Dict]:
        """Fetch all tables associated with a specific migration task."""
        query = f"""
        SELECT jf.* FROM {self.jobfiletable} jf 
        INNER JOIN {self.jobrunversiontable} jrv 
        ON jf.[jobrunversionid] = jrv.[jobrunversionid] 
        WHERE jrv.[runversion] = 1 and jrv.[jobid] = ? Order By [jobfileid] Asc
        """
        return self.execute_query(query, (task_id,))    

    def get_jobfolders_for_task(self, task_id: int) -> List[Dict]:
        """Fetch all folders associated with a specific migration task."""
        query = f"""
        SELECT jfo.* FROM {self.jobfolderstable} jfo
        INNER JOIN {self.jobrunversiontable} jrv 
        ON jfo.[jobrunversionid] = jrv.[jobrunversionid] 
        WHERE jrv.[runversion] = 1 and jrv.[jobid] = ? Order By jfo.[folderid] Asc
        """
        return self.execute_query(query, (task_id,))   

    def get_initial_jobfolders_for_task(self, task_id: int) -> List[Dict]:
        """Fetch all folders associated with a specific migration task."""
        query = f"""
        SELECT jfo.* FROM {self.jobfolderstable} jfo
        INNER JOIN {self.jobrunversiontable} jrv 
        ON jfo.[jobrunversionid] = jrv.[jobrunversionid] 
        WHERE jrv.[runversion] = 1 and jrv.[jobid] = ? 
        AND lower(jfo.foldertype) = 'initial'
        Order By jfo.[folderid] Asc
        """
        return self.execute_query(query, (task_id,))  

    def get_datafileobjects_for_task(self, task_id: int) -> List[Dict]:
        """Fetch all datafile objects associated with a specific migration task."""
        query = f"""
        SELECT jf.filename, jf.folderid, dfo.* 
        FROM {self.datafileobjecttable} dfo
        INNER JOIN {self.jobfiletable} jf
        ON dfo.[datafileid] = jf.[datafileid]
        INNER JOIN {self.jobrunversiontable} jrv 
        ON jf.[jobrunversionid] = jrv.[jobrunversionid] 
        WHERE jrv.[runversion] = 1 and jrv.[jobid] = ?
        ORDER BY jf.[filename], dfo.[datafileobjectid] Asc
        """
        return self.execute_query(query, (task_id,))    

    def save_migration_task(self, task_id: Optional[int], name: str, description: str, schemaname: str, jobprefix: str, status: str, purpose: str) -> int:
        """Save a migration task. If task_id is None, create a new task; otherwise, update the existing task."""
        try:
            cursor = self._connection.cursor()
            if task_id is None:
                query = f"INSERT INTO {self.jobtable} ([jobname], [description], [schemaname], [jobprefix], [status], [purpose]) VALUES (?, ?, ?, ?, ?, ?)"
                cursor.execute(query, (name, description, schemaname, jobprefix, status, purpose))
                self._connection.commit()
                new_task_id = cursor.lastrowid
                cursor.close()
                return new_task_id
            else:
                query = f"""
                UPDATE {self.jobtable} SET [jobname] = ?, [description] = ?, [schemaname]= ?,
                [jobprefix] = ?, [status] = ?, [purpose] = ?
                WHERE [JobId] = ?
                """
                cursor.execute(query, (name, description, schemaname, jobprefix, status, purpose, task_id))
                self._connection.commit()
                cursor.close()
                return task_id
        except Exception as e:
            print(f"DEBUG: save_migration_task() EXCEPTION: {str(e)}")
            print(f"DEBUG: Exception type: {type(e).__name__}")
            import traceback
            print(f"DEBUG: Traceback:\n{traceback.format_exc()}")
            self._connection.rollback()
            raise

    def delete_migration_task(self, task_id: int) -> bool:
        """Delete a specific migration task by its ID."""
        query = f"DELETE FROM {self.jobtable} WHERE [JobId] = ?"
        try:
            cursor = self._connection.cursor()
            cursor.execute(query, (task_id,))
            self._connection.commit()
            rows_affected = cursor.rowcount
            cursor.close()
            return rows_affected > 0
        except Exception as e:
            print(f"DEBUG: delete_migration_task() EXCEPTION: {str(e)}")
            print(f"DEBUG: Exception type: {type(e).__name__}")
            import traceback
            print(f"DEBUG: Traceback:\n{traceback.format_exc()}")
            self._connection.rollback()
            raise

    def refresh_table_cache(self) -> None:
        """Re-query schema/table metadata and refresh the internal cache."""
        if not self._connection:
            self._user_defined_schemas = []
            self._all_tables_info = []
            self._table_lookup = set()
            return

        self._user_defined_schemas = self.get_user_defined_schemas_info()

        schema_names = [
            schema["SCHEMA_NAME"] for schema in self._user_defined_schemas
        ]

        self._all_tables_info = self.get_all_tables_info_for_schemas(
            schema_names
        )

        self._table_lookup = {
            (row["TABLE_SCHEMA"], row["TABLE_NAME"])
            for row in self._all_tables_info
        }

        self.table_cache_changed.emit()
        
    def table_exists(self, schema: str, table_name: str) -> bool:
        """Check whether a table exists, using the cached metadata."""
        return (schema, table_name) in self._table_lookup

    def get_max_runversion(self, task_id: int) -> int | None:
        jobid = task_id
        sql = f"""
        SELECT MAX(runversion) as max_runversion
        FROM {self.jobrunversiontable}
        WHERE jobid = ?
        """

        rows = self.execute_query(sql,(jobid,),fetchone=True)
    
        if not rows:
                return None

        value = rows[0]["max_runversion"]
        return int(value) if value is not None else None

    def resolve_runversion(self, mode: str, task_id: int) -> int:
        jobid = task_id
        max_rv = self.get_max_runversion(task_id)

        if mode == "append":
            if max_rv is None:
                raise ValueError("Cannot append: no previous run exists for this job.")
            return max_rv

        # mode == 'new'
        next_rv = 1 if max_rv is None else max_rv + 1
        sql = f"""
        INSERT INTO {self.jobrunversiontable}
        (jobid, runversion, rundatetime)
        VALUES (?, ?, ?)
        """
        self.execute_dml(sql, (jobid, next_rv, datetime.now()))
        return next_rv
   
    def get_runversionid(self, runversion: int, task_id: int) -> int | None:
        jobid = task_id

        sql = f"""
        SELECT jobrunversionid
        FROM {self.jobrunversiontable}
        WHERE jobid = ? AND runversion = ?
        """
        rows = self.execute_query(sql, (jobid, runversion), fetchone=True)

        if not rows:
            return None

        value = rows[0]["jobrunversionid"]
        return int(value) if value is not None else None
    
    def upsert_found_folders(self, jobrunversionid: int, found_folders: list[tuple[str, str]]) -> list["JobFolder"]:
        """
        Insert foldertype='Found' where path does not already exist for same job/run/foldertype.
        Returns inserted count.
        """
        result = []

        for foldername, folderpath in found_folders:
            normalized_path = self.normalize_path_key(folderpath)
            print(f"Normalized path: {normalized_path} for folderpath: {folderpath}")
            existing = self.get_jobfolder_by_path(normalized_path)
            
            if existing is not None:
                print(f"Existing folder: {existing.folderpath}")
                # Update existing folder
                folderid = existing.folderid
                obj = JobFolder(jobrunversionid=jobrunversionid, folderid=folderid, foldertype='found', foldername=foldername, folderpath=self.normalize_path_key(folderpath))
                self._update_found_folder(obj)
                # I don't want to return the updated folders from this method
                #result.append(obj)
            else:
                # Insert new folder
                obj = JobFolder(jobrunversionid=jobrunversionid, folderid=None, foldertype='found', foldername=foldername, folderpath=self.normalize_path_key(folderpath))
                inserted_obj = self._insert_found_folder(obj)
                if inserted_obj is not None:
                    result.append(inserted_obj)


        # Update the cache
        self.add_jobfolders_to_cache(result)

        return result

    def _insert_found_folder(self, obj: "JobFolder") -> "JobFolder":

        ins_sql = f"""
        INSERT INTO {self.jobfolderstable}
        (jobrunversionid, foldertype, foldername, folderpath)
        OUTPUT INSERTED.folderid
        VALUES (?, ?, ?, ?)
        """
        rows = self.execute_returning_one(ins_sql, (obj.jobrunversionid, obj.foldertype, obj.foldername, obj.folderpath))
                
        if rows is not None and rows["folderid"] is not None:
            obj.folderid = rows["folderid"]
            obj.foldertype = 'found'
            return obj
        return None
    
    def _update_found_folder(self, obj: "JobFolder") -> "JobFolder":
        upd_sql = f"""
        UPDATE {self.jobfolderstable}
        SET foldername = ?, folderpath = ?, foldertype = ?
        WHERE folderid = ?
        """
        self.execute_dml(upd_sql, (obj.foldername, obj.folderpath, obj.foldertype, obj.folderid))
        return obj  

    def get_found_folderid_map(self, jobrunversionid: int) -> dict[str, int]:

        sql = f"""
        SELECT folderid, folderpath
        FROM {self.jobfolderstable}
        WHERE jobrunversionid = ?
        AND LOWER(foldertype) = 'found'
        """
        rows =self.execute_query(sql, (jobrunversionid,), fetchone=False)
        #return {str(r.folderpath).lower(): int(r.folderid) for r in rows if r.folderpath}
        if not rows:
            return None

        result = {}
        for r in rows:
            path = self.normalize_path_key(r["folderpath"])    
            id = r["folderid"]   
            if path is not None and id is not None:
                result[path] = int(id)
        return result

    def get_initial_folders(self, jobrunversionid: int) -> list[str]:
        sql = f"""
        SELECT folderpath
        FROM {self.jobfolderstable}
        WHERE LOWER(foldertype) = 'initial'
        AND jobrunversionid = ? 
        """
        rows = self.execute_query(sql, (jobrunversionid,),  fetchone=False)

        if not rows:
            return None

        result = []
        for r in rows:
            value = self.normalize_path_key(r["folderpath"])       
            if value is not None:
                result.append(value)
        return result

    def upsert_datafile_row(self, newdatafile: "DataFile") -> tuple[int, bool]:
        """
        Returns (datafileid, is_new).
        """

        df = self.get_datafile_by_hash(newdatafile.hashsha256)
        if df is not None:
            #self.importtab_log_append.emit(f"DataFile with hash {newdatafile.hashsha256} already exists.")
            return int(df.datafileid), False

        ins_sql = f"""
        INSERT INTO {self.datafiletable}
        (filetype, hashsha256, filesizebytes)
        OUTPUT INSERTED.datafileid
        VALUES (?, ?, ?)
        """
        row = self.execute_returning_one(ins_sql, (newdatafile.filetype.lower(), newdatafile.hashsha256, newdatafile.filesizebytes))

        if row is not None:
            new_id = row["datafileid"]
            newdatafile.datafileid = new_id
            self._datafiles_by_hash[newdatafile.hashsha256] = newdatafile
            self._datafiles_by_id[new_id] = newdatafile
            self.datafile_cache_changed.emit()
        else:
            new_id = None

        return int(new_id), True  
    
    def upsert_jobfile_row(self, jobfile: "JobFile") -> tuple["JobFile",str] :
        
        jf_existing = self.get_jobfile(jobfile.jobrunversionid, jobfile.folderid, jobfile.filename)
        try:
            if jf_existing is not None:
                #if jf_existing = jobfile: 
                #print(f"Existing jobfile: {jf_existing.jobfileid}")
                if jf_existing.has_same_content(jobfile):
                    #print(f"Jobfile has same content: {jf_existing.jobfileid} - NO UPDATE")
                    return jf_existing, "no update"
                else:
                    #print(f"Jobfile content differs: {jf_existing.jobfileid} - UPDATING ")
                    jobfileid = jf_existing.jobfileid
                    jobfile.jobfileid = jobfileid
                    return self._update_jobfile(jobfile), "updated"
            else:
                #print(f"Inserting new jobfile: {jobfile.filename} -- INSERTING")
                return self._insert_jobfile(jobfile), "inserted"
        except:
            #print(f"Error occurred while upserting jobfile: {jobfile.filename} -- error ")
            return None, "error"    
    
    def _insert_jobfile(self, jobfile: "JobFile") -> "JobFile":

        sql = f"""
        INSERT INTO {self.jobfiletable}
        (datafileid, jobrunversionid, newfile, folderid, filename, filecreateddate, filemodifieddate)
        OUTPUT INSERTED.jobfileid
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        row = self.execute_returning_one(sql, (
            jobfile.datafileid, jobfile.jobrunversionid, 1 if jobfile.newfile else 0,
            jobfile.folderid, jobfile.filename, jobfile.filecreateddate, jobfile.filemodifieddate
        ))

        if row is not None and row["jobfileid"] is not None:
            jobfile.jobfileid = row["jobfileid"]
            self._jobfiles_by_id[jobfile.jobfileid] = jobfile
            self._jobfiles_by_composite_key[(jobfile.datafileid, jobfile.jobrunversionid)] = jobfile
            self.jobfile_cache_changed.emit()
            return jobfile
        return jobfile

    def _update_jobfile(self, jobfile: "JobFile") -> "JobFile":

        sql = f"""
        UPDATE {self.jobfiletable}
        SET datafileid = ?, jobrunversionid = ?, newfile = ?, folderid = ?, filename = ?, filecreateddate = ?, filemodifieddate = ?
        WHERE jobfileid = ?
        """
        row = self.execute_dml(sql, (
            jobfile.datafileid, jobfile.jobrunversionid, 1 if jobfile.newfile else 0,
            jobfile.folderid, jobfile.filename, jobfile.filecreateddate, jobfile.filemodifieddate, jobfile.jobfileid
        ))  

        if row is not None:
            self._jobfiles_by_id[jobfile.jobfileid] = jobfile
            self._jobfiles_by_composite_key[(jobfile.jobrunversionid, jobfile.folderid, jobfile.filename)] = jobfile
            self.jobfile_cache_changed.emit()
            return jobfile
        return None

    def upsert_datafileobject_row(self,datafileobject: "DataFileObject") -> "DataFileObject":
        """Insert or update a DataFileObject record."""
        if datafileobject.datafileobjectid == -1:
            return self._insert_datafileobject(datafileobject)
        else:
            return self._update_datafileobject(datafileobject)

    def upsert_datafileobjectfield_row(self, datafileobjectfield: "DataFileObjectField") -> "DataFileObjectField":
        """Insert or update a DataFileObjectField record."""
        if datafileobjectfield.datafileobjectfieldid == -1:
            return self._insert_datafileobjectfield(datafileobjectfield)
        else:
            return self._update_datafileobjectfield(datafileobjectfield)

    def _insert_datafileobjectfield(self,obj: "DataFileObjectField") -> "DataFileObjectField":
        """Insert a new DataFileObjectField record."""
        sql = f"""
        INSERT INTO {self.datafileobjectfieldtable} 
        (datafileobjectid, fieldordinal, fielddatatype, fieldlength, fieldprecision, skipfield, skipmessage)
        OUTPUT INSERTED.datafileobjectfieldid
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            obj.datafileobjectid,
            obj.fieldordinal,
            obj.fielddatatype,
            obj.fieldlength,
            obj.fieldprecision,
            obj.skipfield,
            obj.skipmessage,
        )
        row = self.execute_returning_one(sql, params)
        if row is not None and row["datafileobjectfieldid"] is not None:
            obj.datafileobjectfieldid = row["datafileobjectfieldid"]
            self._datafileobjectfields_by_id[obj.datafileobjectfieldid] = obj
            self.datafileobjectfield_cache_changed.emit()
            return obj
        return None

    def _update_datafileobjectfield(self,obj: "DataFileObjectField") -> "DataFileObjectField":
        """Update an existing DataFileObjectField record."""
        sql = f"""
        UPDATE {self.datafileobjectfieldtable} 
        SET datafileobjectid = ?, fieldordinal = ?, fielddatatype = ?, fieldlength = ?, fieldprecision = ?, skipfield = ?, skipmessage = ?
        WHERE datafileobjectfieldid = ?
        """
        params = (
            obj.datafileobjectid,
            obj.fieldordinal,
            obj.fielddatatype,
            obj.fieldlength,
            obj.fieldprecision,
            obj.skipfield,
            obj.skipmessage,
            obj.datafileobjectfieldid   
        )
        row = self.execute_dml(sql, params)
        if row is not None and row > 0:
            self._datafileobjectfields_by_id[obj.datafileobjectfieldid] = obj
            self.datafileobjectfield_cache_changed.emit()
            return obj
        return None

    def _insert_datafileobject(self,obj: "DataFileObject") -> "DataFileObject":
        sql = f"""
        INSERT INTO {self.datafileobjecttable}
        (datafileid, objecttype, objectname, stagingtableschema, stagingtablename, skipobject)
        OUTPUT INSERTED.datafileobjectid
        VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            obj.datafileid,
            obj.objecttype,
            obj.objectname,
            obj.stagingtableschema,
            obj.stagingtablename,
            obj.skipobject,
        )
        row = self.execute_returning_one(sql, params)
        if row is not None and row["datafileobjectid"] is not None:
            obj.datafileobjectid = row["datafileobjectid"]
            self._datafileobjects_by_id[obj.datafileobjectid] = obj
            self.datafileobject_cache_changed.emit()
            return obj
        return None

    def _update_datafileobject(self,obj: "DataFileObject") -> "DataFileObject":
        sql = f"""
        UPDATE {self.datafileobjecttable}
        SET datafileid = ?,
            objecttype = ?,
            objectname = ?,
            stagingtableschema = ?,
            stagingtablename = ?,
            skipobject = ?
        WHERE datafileobjectid = ?
        """
        params = (
            obj.datafileid,
            obj.objecttype,
            obj.objectname,
            obj.stagingtableschema,
            obj.stagingtablename,
            obj.skipobject,
            obj.datafileobjectid,
        )
        row = self.execute_dml(sql, params)
        if row is not None and row > 0:
            self._datafileobjects_by_id[obj.datafileobjectid] = obj
            self.datafileobject_cache_changed.emit()
            return obj
        return None
    
    def get_datafiles_by_jobrunversionid_and_ext(self, jobrunversionid: int, exts: list[str]) -> list[Dict]:
        in_placeholders = ", ".join("?" for _ in exts)
        sql = f"""
        SELECT df.datafileid, MIN(jf2.folderpath + '\\' + jf.filename) AS firstfilepath
        FROM {self.jobfiletable} jf
        INNER JOIN {self.datafiletable} df ON jf.datafileid = df.datafileid
        INNER JOIN {self.jobfolderstable} jf2 ON jf.folderid = jf2.folderid
        LEFT JOIN {self.datafileobjecttable} dfo ON df.datafileid = dfo.datafileid
        WHERE jf.jobrunversionid = ?
        AND df.filetype IN ({in_placeholders}) 
        --AND dfo.datafileobjectid IS NULL
        GROUP BY df.datafileid
        """
        ###filetype list is hardcoded for now but should really lookup a list of readable file types. Then again they will only work if the switches are coded for the methods to handle them.
        ###As a first stepe we can construct the list and pass it in.

        ##print(f"DEBUG: SQL for file object read: {sql}")
        params =[jobrunversionid, *exts]
        rows = self.execute_query(sql, params, fetchone=False)
        return rows

    def refresh_datafile_cache(self) -> None:
        """Re-query datafiles and refresh the internal cache."""
        if not self._connection:
            self._datafiles_by_hash = {}
            return

        rows = self.execute_query(
            f"SELECT datafileid, filetype, hashsha256, filesizebytes, skipfile, skipmessage FROM {self.datafiletable}"
        )

        self._datafiles_by_hash = {
            row["hashsha256"]: DataFile.from_db_row(row)
            for row in rows
        }

        self.datafile_cache_changed.emit()

    def datafile_exists_by_hash(self, hash_value: str) -> bool:
        """Check if a datafile with the given hash already exists."""
        return hash_value in self._datafiles_by_hash

    def get_datafile_by_hash(self, hash_value: str) -> DataFile | None:
        """Retrieve a datafile record by its hash."""
        return self._datafiles_by_hash.get(hash_value)

    def get_datafile_by_id(self, datafile_id: int) -> DataFile | None:
        """Retrieve a datafile record by its ID."""
        return self._datafiles_by_id.get(datafile_id)
    
    def refresh_jobfile_cache(self, jobrunversionid: int) -> None:
        """Re-query jobfiles and refresh the internal cache."""
        if not self._connection:
            self._jobfiles_by_composite_key = {}
            self._jobfiles_by_id = {}
            return

        rows = self.execute_query(
            f"""
            SELECT jobfileid, datafileid, jobrunversionid, newfile,
                   folderid, filename, filecreateddate, filemodifieddate
            FROM {self.jobfiletable}
            WHERE jobrunversionid = {jobrunversionid}
            """
        )

        self._jobfiles_by_composite_key = {
            (row["jobrunversionid"], row["folderid"], row["filename"]): JobFile.from_db_row(
                row
            )
            for row in rows
        }

        self._jobfiles_by_id = {
            row["jobfileid"]: JobFile.from_db_row(row)
            for row in rows
        }

        self.jobfile_cache_changed.emit()

    def refresh_jobfolder_cache(self, jobrunversionid: int) -> None:
        """Re-query jobfolders and refresh the internal cache."""
        if not self._connection:
            self._jobfolders_by_id = {}
            self.jobfolder_cache_changed.emit()
            return  

  
        rows = self.execute_query(  
            f"""
            SELECT folderid, jobrunversionid, foldertype, foldername, folderpath
            FROM {self.jobfolderstable}
            WHERE jobrunversionid = {jobrunversionid}
            """
        )
        self._jobfolders_by_id = {
            row["folderid"]: JobFolder.from_db_row(row)
            for row in rows
        }

        # Reverse lookup, since folderpath is unique
        self._jobfolders_by_path = {
            folder.folderpath: folder 
            for folder in self._jobfolders_by_id.values()
        }

        self.jobfolder_cache_changed.emit()

    def jobfile_exists(self,datafile_id: int,jobrunversion_id: int) -> bool:
        """Check if a jobfile with the given composite key already exists."""
        return (datafile_id, jobrunversion_id) in self._jobfiles_by_composite_key

    def get_jobfile(self,jobrunversion_id: int,folderid: int, filename: str) -> JobFile | None:
        """Retrieve a jobfile by datafileid and jobrunversionid."""
        return self._jobfiles_by_composite_key.get(
            (jobrunversion_id, folderid, filename)
        )

    def get_jobfolder(self, folderid: int) -> JobFolder | None:
        """Retrieve a jobfolder by its ID."""
        return self._jobfolders_by_id.get(folderid)

    def get_jobfile_by_id(self, jobfile_id: int) -> JobFile | None:
        """Retrieve a jobfile by its ID."""
        return self._jobfiles_by_id.get(jobfile_id)
    
    def add_datafileobjects_to_cache(self,objects: list[DataFileObject] ) -> None:
        """Add or update datafileobjects in the cache."""
        for obj in objects:
            self._datafileobjects_by_id[obj.datafileobjectid] = obj

        self.datafileobject_cache_changed.emit()

    def add_datafileobjectfields_to_cache(self,fields: list[DataFileObjectField]) -> None:
        """Add or update datafileobjectfields in the cache."""
        for field in fields:
            self._datafileobjectfields_by_id[field.datafileobjectfieldid] = field

        self.datafileobjectfield_cache_changed.emit()

    def add_jobfolders_to_cache(self,folders: list[JobFolder]) -> None: 
        """ Add or update jobfolders in the cache. """
        for folder in folders:  
            self._jobfolders_by_id[folder.folderid] = folder
            self._jobfolders_by_path[folder.folderpath] = folder    
        self.jobfolder_cache_changed.emit()

    def get_jobfolder_by_path(self, folderpath: str) -> Optional["JobFolder"]:
        """O(1) lookup of a jobfolder by its unique folderpath."""
        return self._jobfolders_by_path.get(folderpath)

    def folderpath_exists(self, folderpath: str) -> bool:
        """O(1) check if a folderpath already exists."""
        return folderpath in self._jobfolders_by_path

    def get_jobrunversions(self, task_id: int) -> list[JobRunVersion]:
        """Retrieve all job run versions for a given task."""
        Result: list[JobRunVersion] = []
        
        sql = f"""
        SELECT jobrunversionid, jobid, runversion, rundatetime
        FROM {self.jobrunversiontable}
        WHERE jobid = ?
        """

        rows = self.execute_query(sql, (task_id,))
        for row in rows:
            newrunversion =  JobRunVersion.from_db_row(row)
            Result.append(newrunversion)

        return Result

    def normalize_path_key(self, pathlike) -> str:
        return str(Path(pathlike).resolve()).replace("\\", "/").rstrip("/").lower()
    @property
    def all_jobfiles(self) -> list[JobFile]:
        """Return all cached jobfile records."""
        return list(self._jobfiles_by_composite_key.values())
    
    @property
    def all_datafiles(self) -> list[DataFile]:
        """Return all cached datafile records (for UI listing, etc.)."""
        return list(self._datafiles_by_hash.values())

    @property
    def all_tables_info(self) -> List[Dict]:
        return self._all_tables_info

    @property
    def user_defined_schemas(self) -> List[Dict]:
        return self._user_defined_schemas

############# End of Class

