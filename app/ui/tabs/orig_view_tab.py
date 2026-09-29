from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.migration_context import MigrationContext
from app.ui.tabs.dynamic_grid import DynamicGrid
from app.services.db_service import DatabaseService
from config.config import SYSTEM_ALIASES, Config
from config.dropdown_config import DROPDOWN_LOOKUPS


class ViewOrig(QWidget):
    """Database table viewer and editable DynamicGrid host."""

    status_changed = pyqtSignal(str)

    def __init__(
        self,
        context: MigrationContext, 
        config: Config,
        db_service: DatabaseService,
        parent: QWidget | None = None,
        
            ) -> None:
        super().__init__(parent)

        self.config = config
        self.db_service = db_service
        self.context = context

        self.current_table_schema: str | None = None
        self.current_table_name: str | None = None
        self.current_table_primary_keys: list[str] = []
        self._last_grid_row: int | None = None

        self.context.table_changed.connect(self._on_table_changed)
        self.db_service.table_cache_changed.connect(self._on_database_metadata_changed)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        title_label = QLabel("Viewing Original Extracted Data")
        title_label.setFixedHeight(30)
        layout.addWidget(title_label)


        self.data_grid = DynamicGrid(context=self.context)
        self.data_grid.itemSelectionChanged.connect(self._on_grid_row_changed)
        self.data_grid.rowLostFocus.connect(self._on_grid_lost_focus)

        layout.addWidget(self.data_grid)


    def _on_grid_lost_focus(self, row_idx: int) -> None:
        """Save row when grid loses focus."""
        if self.data_grid.is_row_dirty(row_idx):
            self._save_grid_row(row_idx)

    def _on_grid_row_changed(self) -> None:
        """Handle row selection change in grid - save previous row if dirty."""
        current_row = self.data_grid.currentRow()
        
        # Find which row was previously selected
        if not hasattr(self, '_last_grid_row'):
            self._last_grid_row = None
        
        if self._last_grid_row is not None and self._last_grid_row != current_row:
            self._save_grid_row(self._last_grid_row)
        
        self._last_grid_row = current_row

    def _save_grid_row(self, row_idx: int) -> None:
        """Save a single row if it has been modified."""
        print(f"DEBUG: _save_grid_row() called for row {row_idx}")
        
        if not self.data_grid.is_row_dirty(row_idx):
            print(f"DEBUG: Row {row_idx} is not dirty, skipping save")
            return

        # Get only changed columns
        changed_columns = self.data_grid.get_changed_columns(row_idx)

        # Check if anything actually changed
        if not changed_columns:
            print(f"DEBUG: Row {row_idx} marked dirty but no actual changes detected, skipping update")
            self.data_grid.clear_dirty_flag(row_idx)
            return
        
        if not hasattr(self, 'current_table_primary_keys') or not self.current_table_primary_keys:
            error_msg = "No primary key found for this table"
            print(f"DEBUG: ERROR - {error_msg}")
            QMessageBox.warning(self, "Cannot Save", error_msg)
            return
        
        try:
            schema = self._current_table_schema
            table_name = self._current_table_name
            
            print(f"DEBUG: Saving row {row_idx} from {schema}.{table_name}")
            
            # Get original PK values
            original_row = self.data_grid.get_original_row_data(row_idx)
            
            print(f"DEBUG: Original row: {original_row}")
            print(f"DEBUG: Changed columns: {changed_columns}")
            
            # Build PK dict from original values (in case user modified PK)
            pk_dict = {pk: original_row.get(pk) for pk in self.current_table_primary_keys}
            print(f"DEBUG: Primary keys for WHERE clause: {pk_dict}")
            
            # Update database
            print(f"DEBUG: Calling db_service.update_row()")
            result = self.db_service.update_row(schema, table_name, pk_dict, changed_columns)
            print(f"DEBUG: update_row() returned: {result}")
            
            # Clear dirty flag
            self.data_grid.clear_dirty_flag(row_idx)
            self._set_status(f"Saved row {row_idx + 1} ({len(changed_columns)} column(s) updated)")


            print(f"DEBUG: Row {row_idx} saved successfully")
            
        except Exception as e:
            error_msg = f"Failed to save row: {str(e)}"
            print(f"DEBUG: EXCEPTION - {error_msg}")
            print(f"DEBUG: Exception type: {type(e).__name__}")
            import traceback
            print(f"DEBUG: Traceback:\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Save Error", error_msg)


    def _on_table_changed(self, table_info) -> None:
        """Handle table selection."""
        schema = table_info.get("schema") if table_info else None
        table_name = table_info.get("table_name") if table_info else None
        
        if schema is None or table_name is None:
            print("DEBUG: No table selected, clearing data grid.")
            self.data_grid.clear_contents()
            self.current_table_schema = None
            self.current_table_name = None
            self.current_table_primary_keys = []
            return
        try:
            self.current_table_schema = schema
            self.current_table_name = table_name   

            #get pk information
            self.current_table_primary_keys = self.db_service.get_table_primary_keys(schema, table_name)
            
            # Get column information
            columns = self.db_service.get_columns_info(schema, table_name)

            if not columns:
                QMessageBox.warning(self, "No Columns", f"Table {schema}.{table_name} has no columns")
                return

            # Build and execute SELECT query
            qualified_table = f"{schema}.{table_name}"
            query = f"SELECT * FROM {qualified_table}"
            rows = self.db_service.execute_query(query)

            # Handle empty results gracefully
            if rows is None:
                rows = []
                
            # Load columns into grid
            self.data_grid.load_data(columns, rows, editable=True)

            # Apply dropdowns to configured columns
            self._apply_dropdowns_to_grid(schema, table_name, columns)         
            
            row_count = len(rows) if rows else 0
            self._set_status(f"Selected: {qualified_table} - {len(columns)} columns, {row_count} rows")
      

        except Exception as e:
            QMessageBox.critical(self, "Error Loading Table", f"Failed to load table data: {e}")
            self._set_status("Error loading table")

    def _apply_dropdowns_to_grid(self, schema: str, table_name: str, columns: list[dict]) -> None:
        """Apply dropdown lookups to configured columns."""

        # Find matching config for this table
        for config in DROPDOWN_LOOKUPS:
            if config['schema'] == schema and config['table'] == table_name:
                print(f"DEBUG: Found matching dropdown config for {schema}.{table_name}")
                # Find column index
                col_name = config['column']
                col_idx = next((i for i, col in enumerate(columns) 
                            if col['COLUMN_NAME'] == col_name), None)
                
                if col_idx is not None:
                    print(f"DEBUG: Applying dropdown to column {col_name} at index {col_idx}")
                    try:
                        # Fetch dropdown values from reference table
                        dropdown_values = self.db_service.get_dropdown_values(
                            config['ref_schema'],
                            config['ref_table'],
                            config['ref_column_key'],
                            config['ref_column_desc']
                        )
                        print(f"DEBUG: Fetched dropdown values for {schema}.{table_name}.{col_name}: {dropdown_values}")
                        
                        # Apply to grid
                        self.data_grid.set_column_dropdown(col_idx, dropdown_values)
                        print(f"DEBUG: Applied dropdown to {schema}.{table_name}.{col_name}")
                        
                    except Exception as e:
                        print(f"DEBUG: Failed to apply dropdown: {e}")

    def closeEvent(self, event) -> None:
        """Handle window close - prompt for unsaved changes."""
        if self._has_unsaved_changes():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save | 
                QMessageBox.StandardButton.Discard | 
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Save:
                # Save all dirty rows
                for row_idx in list(self.data_grid.dirty_rows):
                    self._save_grid_row(row_idx)
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        
        try:
            self.db_service.disconnect()
        except:
            pass
        event.accept()

    def _has_unsaved_changes(self) -> bool:
        """Check if grid has dirty rows."""
        return len(self.data_grid.dirty_rows) > 0


    def save_pending_changes(self) -> bool:
        """Save all dirty rows; False means at least one save failed."""
        for row_idx in list(self.data_grid.dirty_rows):
            if not self._save_grid_row(row_idx):
                return False

        return True

    def _save_or_discard_pending_changes(self) -> bool:
        """Ask the user what to do before loading another table."""
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Save changes before switching tables?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Cancel:
            return False

        if reply == QMessageBox.StandardButton.Save:
            return self.save_pending_changes()

        self.data_grid.dirty_rows.clear()
        return True
    
    def update_original_row_data(self, row_idx: int) -> None:
        """Set the saved baseline for a row after a successful database update."""
        if 0 <= row_idx < len(self.original_row_data):
            self.original_row_data[row_idx] = self.get_row_data(row_idx)

    def _set_status(self, message: str) -> None:
        """Send status text upward without coupling to MainWindow."""
        self.status_changed.emit(message)

    def _show_error(self, title: str, message: str) -> None:
        print(f"DEBUG: {title} - {message}")
        QMessageBox.critical(self, title, message)
        self._set_status(message)


    def _on_database_metadata_changed(self) -> None:
        """Refresh datagrid after database metadata changes."""
        print("DEBUG: Database metadata changed")
        self.data_grid.clear_contents()