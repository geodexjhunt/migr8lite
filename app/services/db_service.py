"""Database service for MSSQL operations."""

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
import pyodbc
from pathlib import Path

from app.models.system_model import DataFileObject
from app.models.system_model import DataFileObject
from config.config import Config
from PyQt6.QtCore import pyqtSignal, QObject

class DatabaseConnectionError(Exception):
    pass

class DatabaseService(QObject):
    table_cache_changed = pyqtSignal()

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._connection = None

        self._user_defined_schemas: List[Dict] = []
        self._all_tables_info: List[Dict] = []
        self._table_lookup: set[tuple[str, str]] = set()

        ## tables are stored as schema.tablename 
        ## to be able to wrap them in square brackets we need to insert square brackets around the period
        ## that logic has been moved to the get function of the config property
        self.jobtable = config.system_management_config.get("job_table")
        self.jobfiletable = config.system_management_config.get("jobfile_table")
        self.datafileobjecttable = config.system_management_config.get("datafileobject_table")
        self.datafiletable = config.system_management_config.get("datafile_table")
        self.jobrunversiontable = config.system_management_config.get("jobrunversion_table")
        self.jobfolderstable = config.system_management_config.get("jobfolders_table")
    
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
            print(f"DEBUG: Pre-Execute query: {query} with params: {params or ()}")
            cursor.execute(query, params or ())
            columns = [desc[0] for desc in cursor.description]
            if fetchone:
                row = cursor.fetchone()
                return [dict(zip(columns, row))] if row else []
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        
    def execute_returning_one(self,query: str,params: Optional [tuple] = None) -> dict[str, Any] | None:
        """Execute a statement with OUTPUT and return one result row."""
        with self.get_cursor() as cursor:
            print(f"DEBUG: Pre-Execute DML with OUTPUT : {query} with params: {params or ()}")
            cursor.execute(query, params or ())

            columns = [description[0] for description in cursor.description]
            row = cursor.fetchone()

            return dict(zip(columns, row)) if row else None

    def execute_dml(self,query: str,params: Optional[tuple] = None ) -> int:
        """Execute INSERT, UPDATE, or DELETE and return the affected row count."""
        with self.get_cursor() as cursor:
            print(f"DEBUG: Pre-Execute DML: {query} with params: {params or ()}")
            cursor.execute(query, params or ())
            return cursor.rowcount       
        
    
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

    def get_datafileobjects_for_task(self, task_id: int) -> List[Dict]:
        """Fetch all datafile objects associated with a specific migration task."""
        query = f"""
        SELECT jf.filename, dfo.* FROM {self.datafileobjecttable} dfo
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

    def get_max_runversion(self) -> int | None:
        jobid = self.current_jobid
        sql = f"""
        SELECT MAX(runversion)
        FROM {self.jobrunversiontable}
        WHERE jobid = ?
        """
        row = self.execute_query(sql, (jobid,), fetchone=True)
        return int(row[0]) if row and row[0] is not None else None

    def resolve_runversion(self, mode: str) -> int:
        jobid = self.current_jobid
        max_rv = self.get_max_runversion()

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
   
    def get_runversionid(self, runversion: int) -> int | None:
        jobid = self.current_jobid

        sql = f"""
        SELECT jobrunversionid
        FROM {self.jobrunversiontable}
        WHERE jobid = ? AND runversion = ?
        """
        row = self.execute_query(sql, (jobid, runversion), fetchone=True)
        return int(row[0]) if row and row[0] is not None else None
    
    def upsert_found_folders(self, jobrunversionid: int, found_folders: list[tuple[str, str]]) -> int:
        """
        Insert foldertype='Found' where path does not already exist for same job/run/foldertype.
        Returns inserted count.
        """
        exists_sql = f"""
        SELECT 1
        FROM {self.jobfolderstable}
        WHERE jobrunversionid = ?
        AND LOWER(foldertype) = 'found'
        AND LOWER(folderpath) = LOWER(?)
        """
        ins_sql = f"""
        INSERT INTO {self.jobfolderstable}
        (jobrunversionid, foldertype, foldername, folderpath)
        VALUES (?, 'Found', ?, ?)
        """

        inserted = 0
        for foldername, folderpath in found_folders:
            exists = self.execute_query(exists_sql, (jobrunversionid, folderpath), fetchone=True)
            if exists:
                continue
            self.execute_dml(ins_sql, (jobrunversionid, foldername, folderpath))
            inserted += 1
        return inserted

    def get_found_folderid_map(self, jobrunversionid: int) -> dict[str, int]:

        sql = f"""
        SELECT folderid, folderpath
        FROM {self.jobfolderstable}
        WHERE jobrunversionid = ?
        AND LOWER(foldertype) = 'found'
        """
        rows =self.execute_query(sql, (jobrunversionid,), fetchone=False)
        #return {str(r.folderpath).lower(): int(r.folderid) for r in rows if r.folderpath}
        return {normalize_path_key(r.folderpath): int(r.folderid) for r in rows if r.folderpath}

    def get_initial_folders(self, jobrunversionid: int) -> list[str]:
        jobid = self.get_current_jobid()  # Assuming there's a method to get the current job ID
        sql = f"""
        SELECT folderpath
        FROM {self.jobfolderstable}
        WHERE LOWER(foldertype) = 'initial'
        AND jobrunversionid = ? 
        """
        rows = self.execute_query(sql, (jobrunversionid,),  fetchone=False)
        return [r.folderpath for r in rows if r.folderpath]

    def get_or_create_datafile(self, filetype: str, hashsha256: str, filesizebytes: int) -> tuple[int, bool]:
        """
        Returns (datafileid, is_new).
        """

        sel_sql = f"""
        SELECT datafileid
        FROM {self.datafiletable}
        WHERE hashsha256 = ?
        """
        row = self.execute_query(sel_sql, (hashsha256,), fetchone=True)
        if row:
            return int(row[0]), False

        ins_sql = f"""
        INSERT INTO {self.datafiletable}
        (filetype, hashsha256, filesizebytes)
        OUTPUT INSERTED.datafileid
        VALUES (?, ?, ?)
        """
        row = self.execute_returning_one(ins_sql, (filetype.lower(), hashsha256, filesizebytes))

        new_id = row[0] if row and row[0] is not None else None
        return int(new_id), True  
    
    def insert_jobfile_row(self, datafileid: int, jobrunversionid: int, newfile: bool,
        folderid: int | None, filename: str, filecreateddate, filemodifieddate) -> int:

        sql = f"""
        INSERT INTO {self.jobfiletable}
        (datafileid, jobrunversionid, newfile, folderid, filename, filecreateddate, filemodifieddate)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        rowcount = self.execute_dml(sql, (
            datafileid, jobrunversionid, 1 if newfile else 0,
            folderid, filename, filecreateddate, filemodifieddate
        ))
        return rowcount
    
    def upsert_datafileobject_row(
            self, datafileobject: DataFileObject
        ):
            if datafileobject.datafileobjectid == -1:
                sql = f"""
                INSERT INTO {self.datafileobjecttable}
                (datafileid, objecttype, objectname, stagingtableschema, stagingtablename, skipobject)
                VALUES (?, ?, ?, ?, ?, ?)
                """
                params = (
                    datafileobject.datafileid, datafileobject.objecttype, datafileobject.objectname,
                    datafileobject.stagingtableschema, datafileobject.stagingtablename, datafileobject.skipobject
                )
            else:
                sql = f"""
                UPDATE {self.datafileobjecttable}
                SET datafileid = ?, objecttype = ?, objectname = ?, stagingtableschema = ?, stagingtablename = ?, skipobject = ?
                WHERE datafileobjectid = ?
                """
                params = (
                    datafileobject.datafileid, datafileobject.objecttype, datafileobject.objectname,
                    datafileobject.stagingtableschema, datafileobject.stagingtablename, datafileobject.skipobject,
                    datafileobject.datafileobjectid
                )

   
            rowcount = self.execute_dml(sql, params)

            return rowcount

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
        AND dfo.datafileobjectid IS NULL
        GROUP BY df.datafileid
        """
        ###filetype list is hardcoded for now but should really lookup a list of readable file types. Then again they will only work if the switches are coded for the methods to handle them.
        ###As a first stepe we can construct the list and pass it in.

        ##print(f"DEBUG: SQL for file object read: {sql}")
        params =[jobrunversionid, *exts]
        rows = self.execute_query(sql, params, fetchone=False)
        return rows

    @property
    def all_tables_info(self) -> List[Dict]:
        return self._all_tables_info

    @property
    def user_defined_schemas(self) -> List[Dict]:
        return self._user_defined_schemas

############# End of Class

def normalize_path_key(pathlike) -> str:
    return str(Path(pathlike).resolve()).replace("\\", "/").rstrip("/").lower()