import pandas as pd
import re
from pathlib import Path
from app.constants import SQLSERVER_MAX_IDENTIFIER_LEN
from app.models.system_model import DataFileObject
from app.services import file_service
from app.services.db_service import DatabaseService
from app.models.migration_context import MigrationContext
from PyQt6.QtCore import QObject


class ExtractService(QObject):
    """
    Orchestrates extraction of DataFileObject contents into staging tables.

    Responsibilities:
    - Read file contents via file_service (re-used, not duplicated)
    - Create staging tables (schema/name already resolved on DataFileObject)
    - Write extracted data into staging tables
    - Report progress/results back to the UI
    """
    
    def __init__(self, context: MigrationContext, db_service: DatabaseService) -> None:
        super().__init__()
        self.context = context
        self.db_service = db_service

    def extract_object(self, datafileobject: DataFileObject) -> None:
        """Extract a single DataFileObject's contents into its staging table."""
        schema = datafileobject.stagingtableschema
        table_name = datafileobject.stagingtablename

        df = file_service.load_text_file_to_dataframe(Path(datafileobject.filepath))

        self._create_staging_table_if_needed(schema, table_name, df)
        self._write_dataframe_to_table(schema, table_name, df)

    def extract_selected(self, datafileobjects: list[DataFileObject]) -> None:
        """Extract multiple selected objects, e.g. from ExtractTab checkboxes."""
        for obj in datafileobjects:
            self.extract_object(obj)

    def _create_staging_table_if_needed(self, schema: str, table_name: str, df) -> None:
        ...

    def _write_dataframe_to_table(self, schema: str, table_name: str, df) -> None:
        ...

    def apply_header_row(self, df: pd.DataFrame, header_row: int) -> pd.DataFrame:
        """
        Given a raw dataframe (no header assumed) and a 1-indexed header_row,
        extract column names from that row and tag pre-header rows.
        """
        header_idx = header_row - 1  # convert to 0-indexed

        # Extract header values, filling nulls with UnknownCol#
        header_values = df.iloc[header_idx].tolist()
        column_names = self._generate_column_names(header_values)  # your existing UnknownCol# logic

        # Rows strictly after the header become the "real" data
        data_df = df.iloc[header_idx + 1:].copy()
        data_df.columns = column_names

        # Rows before (and including?) the header become "pre-header" rows
        pre_header_df = df.iloc[:header_idx].copy()
        pre_header_df.columns = column_names  # same column count, so labels still line up positionally

        # Add row numbering + flag
        max_row = len(df)
        data_df["_source_row_number"] = range(header_idx + 1, header_idx + 1 + len(data_df))
        data_df["_is_pre_header"] = False

        pre_header_df["_source_row_number"] = range(max_row + 1, max_row + 1 + len(pre_header_df))
        pre_header_df["_is_pre_header"] = True

        combined = pd.concat([data_df, pre_header_df], ignore_index=True)
        return combined
    
    def preview_with_header(self, file_path: Path, sheet_name: str | None, header_row: int) -> pd.DataFrame:
        cache_key = (file_path, sheet_name)
        if cache_key not in self._raw_df_cache:
            if sheet_name:
                self._raw_df_cache[cache_key] = file_service.load_excel_sheet_raw(file_path, sheet_name)
            else:
                self._raw_df_cache[cache_key] = file_service.load_text_file_raw(file_path)

        raw_df = self._raw_df_cache[cache_key]
        return self.apply_header_row(raw_df.copy(), header_row)

    
###### Below this line am not sure if I need these yet but might be relevant:

    def get_incremented_table_name(self,base_name: str, schema: str, max_len: int = SQLSERVER_MAX_IDENTIFIER_LEN ) -> str:
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