"""Main application window."""

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QMessageBox, QListWidget, QListWidgetItem, QSplitter, QTreeWidget, QTreeWidgetItem
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt
from app.config import Config
from app.services.db_service import DatabaseService
from app.models.migration_state import JobStateManager
from app.ui.dynamic_grid import DynamicGrid

class MainWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.db_service = DatabaseService(config)
        self.job_state = JobStateManager()
       
        app_config = config.app_config
        self.setWindowTitle(app_config.get("title", "migr8lite"))
        self.setGeometry(100, 100, app_config.get("window_width", 1400), app_config.get("window_height", 900))
        self._setup_ui()
        self._connect_database()

        self.user_defined_schemas = []
        self.all_tables_info = []
        self.current_table_primary_keys = []
        self._current_table_schema = None
        self._current_table_name = None

        self._update_database_info_cache()

    def _update_database_info_cache(self) -> None:
        if self.db_service._connection:
            self.user_defined_schemas = self.db_service.get_user_defined_schemas_info()
            self.all_tables_info = self.db_service.get_all_tables_info_for_schemas(
                [schema["SCHEMA_NAME"] for schema in self.user_defined_schemas]
            )
            self._populate_table_list()
        else:
            self.status_label.setText("Unable to update local cache of migration db schema")
            self.user_defined_schemas = []
            self.all_tables_info = []

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        
        title_label = QLabel("migr8lite - Migration Management System")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_workflow_panel(), "Workflow")
        self.tab_widget.addTab(self._create_data_explorer(), "Data Explorer")
        main_layout.addWidget(self.tab_widget)
        
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)
        central_widget.setLayout(main_layout)
    
    def _create_workflow_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        label = QLabel("Workflow Panel (Coming Soon)")
        layout.addWidget(label)
        for phase_label, phase_id in [("Define Migration", "a_define"), ("Import Files", "b_import")]:
            btn = QPushButton(phase_label)
            btn.clicked.connect(lambda checked, pid=phase_id: self._on_phase_clicked(pid))
            layout.addWidget(btn)
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_data_explorer(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("Available Tables & Views")
        title_label.setFixedHeight(30)
        layout.addWidget(title_label)
        
        # Splitter for list and grid
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Table list widget (left panel)
        self.table_list = QTreeWidget()
        self.table_list.setHeaderLabel("Schemas")
        self.table_list.itemClicked.connect(self._on_table_selected)
        splitter.addWidget(self.table_list)
        
        # Dynamic grid (right panel for columns/data)
        self.data_grid = DynamicGrid()
        self.data_grid.itemSelectionChanged.connect(self._on_grid_row_changed) 
        self.data_grid.rowLostFocus.connect(self._on_grid_lost_focus) 
        splitter.addWidget(self.data_grid)
        
        # Set reasonable split sizes
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter, 1)
        widget.setLayout(layout)
        return widget
    
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
            self.status_label.setText(f"Saved row {row_idx + 1} ({len(changed_columns)} column(s) updated)")
            print(f"DEBUG: Row {row_idx} saved successfully")
            
        except Exception as e:
            error_msg = f"Failed to save row: {str(e)}"
            print(f"DEBUG: EXCEPTION - {error_msg}")
            print(f"DEBUG: Exception type: {type(e).__name__}")
            import traceback
            print(f"DEBUG: Traceback:\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Save Error", error_msg)

    def _populate_table_list(self) -> None:
        """Populate the tree with schemas as parent nodes and tables as children."""
        self.table_list.clear()
        
        # Group tables by schema
        schemas_dict = {}
        for table_info in self.all_tables_info:
            schema = table_info['TABLE_SCHEMA']
            if schema not in schemas_dict:
                schemas_dict[schema] = []
            schemas_dict[schema].append(table_info)
        
        # Create tree structure
        for schema in sorted(schemas_dict.keys()):
            schema_item = QTreeWidgetItem([schema])
            
            for table_info in sorted(schemas_dict[schema], key=lambda x: x['TABLE_NAME']):
                table_name = table_info['TABLE_NAME']
                table_type = table_info['TABLE_TYPE']
                display_name = f"{table_name}" ## i've removed table type from here as not useful
                
                table_item = QTreeWidgetItem([display_name])
                table_item.setData(0, Qt.ItemDataRole.UserRole, table_info)
                schema_item.addChild(table_item)
            
            self.table_list.addTopLevelItem(schema_item)
        
        self.status_label.setText(f"Loaded {len(self.all_tables_info)} tables from {len(schemas_dict)} schemas")
    
    def _on_table_selected(self, item: QTreeWidgetItem) -> None:
        """Handle table selection from list."""
        try:
            table_info = item.data(0, Qt.ItemDataRole.UserRole)

            # Only process if it's a table item (has table_info), not a schema node
            if table_info is None:
                return

            schema = table_info['TABLE_SCHEMA']
            table_name = table_info['TABLE_NAME']

            self._current_table_schema = schema
            self._current_table_name = table_name   

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
            
            row_count = len(rows) if rows else 0
            self.status_label.setText(f"Selected: {qualified_table} - {len(columns)} columns, {row_count} rows")
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Table", f"Failed to load table data: {e}")
            self.status_label.setText("Error loading table")

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
    
    def _connect_database(self) -> None:
        try:
            self.db_service.connect()
            self.status_label.setText("Connected to database")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to connect: {e}")
            self.status_label.setText("Disconnected")
    
    def _on_phase_clicked(self, phase_id: str) -> None:
        self.status_label.setText(f"Navigating to: {phase_id}")
    
    def closeEvent(self, event) -> None:
        try:
            self.db_service.disconnect()
        except:
            pass
        event.accept()

