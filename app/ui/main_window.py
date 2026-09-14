"""Main application window."""

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QMessageBox, QListWidget, QListWidgetItem, QSplitter
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
        layout.addWidget(QLabel("Available Tables & Views"))
        
        # Splitter for list and grid
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Table list widget (left panel)
        self.table_list = QListWidget()
        self.table_list.itemClicked.connect(self._on_table_selected)
        splitter.addWidget(self.table_list)
        
        # Dynamic grid (right panel for columns/data)
        self.data_grid = DynamicGrid()
        splitter.addWidget(self.data_grid)
        
        # Set reasonable split sizes
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
        widget.setLayout(layout)
        return widget
    
    def _populate_table_list(self) -> None:
        """Populate the table list widget with all available tables."""
        self.table_list.clear()
        for table_info in self.all_tables_info:
            schema = table_info['TABLE_SCHEMA']
            table_name = table_info['TABLE_NAME']
            table_type = table_info['TABLE_TYPE']
            
            # Display as "schema.table (TYPE)"
            display_name = f"{schema}.{table_name} ({table_type})"
            item = QListWidgetItem(display_name)
            # Store full table info in item data for later retrieval
            item.setData(Qt.ItemDataRole.UserRole, table_info)
            self.table_list.addItem(item)
        
        self.status_label.setText(f"Loaded {len(self.all_tables_info)} tables from database")
    
    def _on_table_selected(self, item: QListWidgetItem) -> None:
        """Handle table selection from list."""
        try:
            table_info = item.data(Qt.ItemDataRole.UserRole)
            schema = table_info['TABLE_SCHEMA']
            table_name = table_info['TABLE_NAME']
            
            # Get column information
            columns = self.db_service.get_columns_info(schema, table_name)
            
            # Load columns into grid (empty rows for now)
            rows = []
            self.data_grid.load_data(columns, rows, editable=False)
            
            self.status_label.setText(f"Selected: {schema}.{table_name} - {len(columns)} columns")
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Table", f"Failed to load table structure: {e}")
            self.status_label.setText("Error loading table")
    
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

