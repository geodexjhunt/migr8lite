
import traceback

import pandas as pd
import re
from typing import Dict, List
from pathlib import Path
from app.constants import SQLSERVER_MAX_IDENTIFIER_LEN
from app.models.system_model import DataFileObject, ExistingTablePolicy, ExtractResult, ExtractStatus, IssueType, PreflightResult, TableExtractRequest
from app.services.file_service import *
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

        self._raw_df_cache = {}

    def extract_object(self, datafileobject: DataFileObject) -> None:
        """Extract a single DataFileObject's contents into its staging table."""
        schema = datafileobject.stagingtableschema
        table_name = datafileobject.stagingtablename

        df = load_text_file_to_dataframe(Path(datafileobject.filepath))

        self._create_staging_table_if_needed(schema, table_name, df)
        self._write_dataframe_to_table(schema, table_name, df)

    def check_table(self, table: Dict[str, Any]) -> PreflightResult:
        """Read-only: detect problems without changing anything."""
        schema = table["stagingtableschema"]
        table_name = table["stagingtablename"]
        try:
            exists = self.db_service.table_exists(schema, table_name)
        except Exception as exc:
            return PreflightResult(issues=[IssueType.CHECK_FAILED], detail=str(exc))
        result = PreflightResult()
        if exists:
            result.issues.append(IssueType.TABLE_EXISTS)
            result.detail = f"{schema}.{table_name} already exists"
        return result

    def process_file(self,jobfileid: int,requests: List[TableExtractRequest]) -> List[ExtractResult]:
        """Open the datafile ONCE, extract each requested object using its own policy.
        Never prompts. Returns one ExtractResult per request, in the same order.
        A failure on one table should be captured in its result, not abort the rest."""

        results: List[ExtractResult] = []
        to_extract: List[TableExtractRequest] = []

        jobfile = self.db_service.get_jobfile_by_id(jobfileid)
        jobfolder = self.db_service.get_jobfolder_by_id(jobfile.folderid)
        filepath = Path(jobfolder.folderpath) / jobfile.filename
        ftype, subtype  = get_ftype_subtype_from_path(filepath)
        
        if not jobfile:
            raise ValueError(f"JobFile with ID {jobfileid} not found")
        if not jobfolder:
            raise ValueError(f"JobFolder with ID {jobfile.folderid} not found") 


        for request in requests:
            if request.existing_policy == ExistingTablePolicy.NOT_SET:
                # No conflict detected; proceed with APPEND or REPLACE as your default
                request.existing_policy = ExistingTablePolicy.REPLACE
                to_extract.append(request)
            elif request.existing_policy == ExistingTablePolicy.ABORT:
                results.append(ExtractResult(
                    status=ExtractStatus.SKIPPED,
                    message="Table exists; operation aborted per policy"
                ))
            elif request.existing_policy == ExistingTablePolicy.SKIP:
                results.append(ExtractResult(
                    status=ExtractStatus.SKIPPED,
                    message="User skipped this table"
                ))
            elif request.existing_policy == ExistingTablePolicy.APPEND:
                results.append(ExtractResult(
                    status=ExtractStatus.SKIPPED,
                    message="This shouldn't be possible as removed from gui choices!"
                ))
            else:
                # REPLACE OR NO VALUE BECAUSE NO CONFLICT
                to_extract.append(request)

        # Open the file once and extract the approved tables
        if to_extract:
            extracted: Dict[int, ObjectExtraction] 
            extracted = process_datafile_for_extraction(
                db_service=self.db_service,
                fp=filepath,
                ftype=ftype,
                subtype=subtype,
                requests=to_extract,
            )
            
            # Write and collect results for extracted tables
            for request in to_extract:
                result = self._write_extracted_table(
                    request=request,
                    df=extracted.get(request.datafileobjectid).df if extracted.get(request.datafileobjectid) else None,
                )
                results.append(result)

        return results

    def _write_extracted_table(self, request: TableExtractRequest, df: pd.DataFrame | None) -> ExtractResult:
        """
        Write the extracted table to the database or storage.
        """
        # Skip and Abort have already been removed - so all remaining calls to this method assume drop and re-create table.


        try:
            if df is None:
                return ExtractResult(
                    status=ExtractStatus.FAILED,
                    message=f"Failed to write extracted table: Dataframe is None"
                    )
    
            header_values = {}
            for idx, val in enumerate(df.columns.tolist()):
                header_values[idx] = {"OrigFieldName": val}
            generated  = generate_column_names(header_values)  # your existing UnknownCol# logic

            # Plain list of strings, 0-based, in column order
            column_names: list[str] = [generated[i]["SanitizedFieldName"] for i in range(len(df.columns))]

            self.db_service.drop_table_if_exists(request.stagingtablename, request.stagingtableschema)  

            col_types_from_pd = infer_dataframe_sql_types_from_pandas(df, date_format_label="Auto") 

            col_types_to_create: Dict[str, str] = {
                column_names[idx - 1]: col_type["sql_type"]
                for idx, col_type in col_types_from_pd.items()
            }

            # Apply sanitized names to the DataFrame
            df.columns = column_names

            self.db_service.create_table(
                table_name=request.stagingtablename,
                col_types=col_types_to_create,
                schema=request.stagingtableschema
            )

            self.db_service.insert_dataframe(
                table_name=request.stagingtablename,
                df=df,
                schema=request.stagingtableschema
            )

            # Implement the actual writing logic here
            # For now, just return a success result
            return ExtractResult(
                status=ExtractStatus.SUCCESS,
                message="Table Dropped, Created, Extracted and written successfully"
            )
        except Exception as e:
            traceback.print_exc()
            return ExtractResult(
                status=ExtractStatus.FAILED,
                message=f"Failed to write extracted table: {type(e).__name__}: {e!r}"
                #message=f"Failed to write extracted table: {e}"
            )

    # ------------------------------------------------------------------
    #  Preview Methods
    # ------------------------------------------------------------------

    def apply_header_row(self, df: pd.DataFrame, header_row: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Given a raw dataframe (no header assumed) and a 1-indexed header_row,
        extract column names from that row and tag pre-header rows.
        """
        header_idx = header_row - 1  # convert to 0-indexed

        # Extract header values, filling nulls with UnknownCol#
        header_values: Dict[int,Dict] = {}
        for idx, val in enumerate(df.iloc[header_idx].tolist()):
            header_values[idx] = {"OrigFieldName": val}

        column_names = generate_column_names(header_values)  # your existing UnknownCol# logic

        # extract the OrigFieldName from the header_values in index order
        col_list: list[str] = [column_names[idx]["SanitizedFieldName"] for idx in range(len(column_names))]

        # Rows strictly after the header become the "real" data
        data_df = df.iloc[header_idx + 1:].copy()
        data_df.columns = col_list

        # Rows before (and including?) the header become "pre-header" rows
        pre_header_df = df.iloc[:header_idx].copy()
        pre_header_df.columns = col_list  # same column count, so labels still line up positionally

        # Build the original header row as its own DataFrame row, using col_list as column names
        orig_header_row = {
            col_list[idx]: header_values[idx]["OrigFieldName"]
            for idx in range(len(col_list))
        }
        orig_header_df = pd.DataFrame([orig_header_row], columns=col_list)

        # Append the original header row to the end of pre_header_df (its original position)
        pre_header_df = pd.concat([pre_header_df, orig_header_df], ignore_index=True)


        # Add row numbering + flag
        max_row = len(df)
        data_df["_source_row_number"] = range(header_idx + 1, header_idx + 1 + len(data_df))
        data_df["_is_pre_header"] = False

        pre_header_df["_source_row_number"] = range(1, len(pre_header_df) + 1)
        pre_header_df["_is_pre_header"] = True

        #combined = pd.concat([data_df, pre_header_df], ignore_index=True)
        #combined = combined.fillna("")  # or another placeholder
        return pre_header_df.fillna(""), data_df.fillna("")
    
    def preview_with_header(self, file_path: Path, sheet_name: str | None, header_row: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        cache_key = (file_path, sheet_name)
        operable = get_operable_filetypes()
        ext = file_path.suffix.lower().lstrip(".")
        meta = operable.get(ext)
        if not meta:
            self.append_log(f"⏭️ Unsupported extension for file object read: .{ext} ({file_path.name})")
            return pd.DataFrame(), pd.DataFrame()  # or continue

        ftype = (meta.get("type") or "").lower()
        subtype = (meta.get("subtype") or "").lower()

        if cache_key not in self._raw_df_cache:
            if ftype == "excel":
                self._raw_df_cache[cache_key] = load_excel_sheet_to_dataframe(file_path, sheet_name, dtype=str)
            elif ftype == "text":
                self._raw_df_cache[cache_key] = load_text_file_to_dataframe(file_path,drop_all_null_columns=True, log_fn=None)
            elif ftype == "database" and subtype == "access":
                self._raw_df_cache[cache_key] = load_access_table_to_dataframe(file_path, sheet_name, dtype=str)

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