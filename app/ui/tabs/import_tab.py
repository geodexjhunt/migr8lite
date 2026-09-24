from multiprocessing import context
import pyodbc
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget
from app.models.migration_context import MigrationContext
from app.services.db_service import DatabaseService
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (    QApplication,    QFileDialog,    QGridLayout,    QLabel,
    QLineEdit,    QMainWindow,    QMessageBox,    QPushButton,    QTextEdit,    QWidget,
    QHBoxLayout,    QVBoxLayout,    QInputDialog,    QComboBox,    QDialog,    QListWidget,
    QListWidgetItem,    QSizePolicy)

from config.config import Config


class ImportTab(QWidget):
    status_changed = pyqtSignal(str)
    def __init__(
        self,
        context: MigrationContext, 
        config: Config,
        db_service: DatabaseService,
        parent: QWidget | None = None,
        
            ) -> None:
        super().__init__(parent)

        self.context = context
        self.config = config
        self.db_service = db_service

        self.current_task = self.context.current_task_id
        self.current_table = self.context.current_table

        self.context.task_changed.connect(self._on_task_changed)
        self.context.table_changed.connect(self._on_table_changed)

        self._setup_ui()
        #don't need to refresh as it is refreshed by the context signals
        #self._refresh_ui()

    def _on_task_changed(self, task_id) -> None:
        """Clear or refresh task-scoped content."""
        self.current_task = task_id
        self._refresh_ui()

    def _on_table_changed(self, table_info) -> None:
        """Load import details for the newly selected task table."""
        self.current_table = table_info
        self._refresh_ui()

    def _setup_ui(self) -> None:
        #central = QWidget()
        # layout = QGridLayout(central)
        layout = QGridLayout(self)
        title_label = QLabel("Import Files to Migration DB")
        title_label.setFixedHeight(30)
        

        self.server_input = QLineEdit()
        self.server_input.setReadOnly(True)
        self.database_input = QLineEdit()
        self.database_input.setReadOnly(True)

        self.table_prefix_input = QLineEdit("stg")
        #self.table_schema_input = QLineEdit("migr")
        self.table_schema_combo = QComboBox()

        self.date_format_combo = QComboBox()
        self.date_format_combo.addItems([
            "Auto",
            "YYYY-MM-DD",
            "DD-MM-YYYY",
            "MM-DD-YYYY",
            "YYYY-MM-DD HH:MM:SS",
        ])

        self.initial_folders_list = QListWidget()
        self.initial_folders_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.initial_folders_list.setEnabled(False)  # read-only in main UI
        # make list resist vertical growth
        self.initial_folders_list.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        ext_row = QHBoxLayout()

        layout.addWidget(title_label, 0, 0, 1, 2)

        layout.addWidget(QLabel("Server Name:"), 1, 0)
        layout.addWidget(self.server_input, 1, 1)

        layout.addWidget(QLabel("Database Name:"), 2, 0)
        layout.addWidget(self.database_input, 2, 1)

        ext_row.addWidget(QLabel("Date Format:"))
        ext_row.addWidget(self.date_format_combo)
        layout.addLayout(ext_row, 3, 1)

        layout.addWidget(QLabel("Table Prefix:"), 4, 0)
        layout.addWidget(self.table_prefix_input, 4, 1)

        layout.addWidget(QLabel("Table Schema:"), 5, 0)
        #layout.addWidget(self.table_schema_input, 5, 1)
        layout.addWidget(self.table_schema_combo, 5, 1) 

        layout.addWidget(QLabel("Initial Folders:"), 6, 0)
        layout.addWidget(self.initial_folders_list, 6, 1)

        ext2_row = QHBoxLayout()

        self.connect_btn = QPushButton("Test SQL Connection")
        self.connect_btn.clicked.connect(self._test_connection)
        ext2_row.addWidget(self.connect_btn)

        self.test_schema_btn = QPushButton("Test Schema Exists")
        self.test_schema_btn.clicked.connect(self._test_schema_exists)
        ext2_row.addWidget(self.test_schema_btn)

        layout.addLayout(ext2_row, 7, 1, 1, 2)

        self.run_btn = QPushButton("Run Load")
        #self.run_btn.clicked.connect(self.run_process)
        layout.addWidget(self.run_btn, 8, 1)

        self.read_fileobjects_btn = QPushButton("List File Objects of Latest Run for this Job")
        #self.read_fileobjects_btn.clicked.connect(self.on_read_file_objects)
        layout.addWidget(self.read_fileobjects_btn, 9, 1)

        self.read_fileobjectfields_btn = QPushButton("List File Object Fields & Load Content for this Job")
        #self.read_fileobjectfields_btn.clicked.connect(self.on_read_file_object_fields)
        layout.addWidget(self.read_fileobjectfields_btn, 10, 1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        # let log take extra space
        self.log.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout.setRowStretch(11, 1)   # row containing log
        layout.setRowStretch(6, 0)    # row containing list
        layout.addWidget(self.log, 11 , 0, 1, 2)

        #self.refresh_profile_dropdown()
        #self.refresh_selected_job_folders_list()

        self.append_log("ODBC drivers: " + ", ".join(pyodbc.drivers()))

        self._refresh_schema_combo()
        self.failed_files = []


    def _test_connection(self):
        if self.db_service.test_connected():
            self.append_log("SQL Connection Successful.")
        else:
            self.append_log("SQL Connection Failed.")

    def _test_schema_exists(self):
        schemas = self.db_service.get_user_defined_schemas_info()
        schema = self.table_schema_combo.currentText()

        if any(s.get('SCHEMA_NAME') == schema for s in schemas):
            self.append_log(f"Schema '{schema}' exists.")
        else:
            self.append_log(f"Schema '{schema}' does not exist.")   




    def _refresh_schema_combo(self):
        self.table_schema_combo.clear()

        schemas = self.db_service.get_user_defined_schemas_info()
        if schemas:
            for schema in schemas:
                self.table_schema_combo.addItem(schema.get('SCHEMA_NAME'))
            

        self.table_schema_combo.setCurrentIndex(0)
        

    def _refresh_ui(self):
        """Refresh the UI elements with the latest data."""
        self._refresh_database_info()
        self._refresh_selected_job_folders_list()

    def _refresh_database_info(self):
        p = self.config.get("database", None)
        if not p:
            return
        self.server_input.setText(p.get("server", ""))
        self.database_input.setText(p.get("database", ""))
        self.append_log(f"Refreshed Database Info: Server={p.get('server', '')}, Database={p.get('database', '')}")

    def _get_selected_job_initial_folders(self, currentjob: int = None) -> list[str]:
        self.append_log(f"This woulld query folders for jobid: {currentjob}.")
        return ["1","2","3","4","5"]

    def _refresh_selected_job_folders_list(self):
        currentjob = self.current_task
        self.initial_folders_list.clear()
        for p in self._get_selected_job_initial_folders(currentjob):
            self.initial_folders_list.addItem(QListWidgetItem(p))
        
        self.append_log(f"Loaded job folders for jobid: {currentjob}.")
        self._update_initial_folders_list_height()

    def append_log(self, msg: str):
        self.log.append(msg)

    def _set_status(self, message: str) -> None:
        """Send status text upward without coupling to MainWindow."""
        self.status_changed.emit(message)

    def _update_initial_folders_list_height(self):
        lw = self.initial_folders_list
        count = lw.count()
        visible_rows = min(max(count, 1), 5)

        row_h = lw.sizeHintForRow(0)
        if row_h < 0:
            row_h = lw.fontMetrics().height() + 6

        frame = lw.frameWidth() * 2
        h = frame + (row_h * visible_rows)
        lw.setMaximumHeight(h)
        lw.setMinimumHeight(h)   # fixed-at-content height; remove if you want slight shrink/grow
