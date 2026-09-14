"""Database service for MSSQL operations."""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional
import pyodbc
from app.config import Config

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
    
    def get_columns_info(self, schema: str, table: str) -> List[Dict]:
        query = "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?"
        return self.execute_query(query, (schema, table))
