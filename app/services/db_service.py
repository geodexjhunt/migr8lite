"""Database service for MSSQL operations."""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional
import pyodbc
from config.config import Config

class DatabaseConnectionError(Exception):
    pass

class DatabaseService:
    def __init__(self, config: Config):
        self.config = config
        self._connection = None
    
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
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict]:
        with self.get_cursor() as cursor:
            cursor.execute(query, params or ())
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

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