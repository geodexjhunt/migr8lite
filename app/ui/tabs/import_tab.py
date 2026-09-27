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

from app.services.import_service import ImportService
from config.config import Config
from app.services.file_service import get_file_counts


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

        self.import_service = ImportService(
            config=self.config,
            context=self.context,
            db_service=self.db_service,
        )


        self.current_task = self.context.current_task_id
        self.current_table = self.context.current_table

        self.context.task_changed.connect(self._on_task_changed)
        self.context.table_changed.connect(self._on_table_changed)

        self.import_service.log_appended.connect(self.append_log)

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
        self.run_btn.clicked.connect(self._run_import_step_1)
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
        initialjobfolders = self.db_service.get_initial_jobfolders_for_task(currentjob) 
        return [f.get('folderpath') for f in initialjobfolders]
    

    def _refresh_selected_job_folders_list(self):
        currentjob = self.current_task
        if currentjob is None:
            self.append_log(f"Cant load job folders until a job is selected.")
            return
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

    def _get_inputs(self):
        return {
            "server": self.server_input.text().strip(),
            "database": self.database_input.text().strip(),
            "table_prefix": self.table_prefix_input.text().strip(),
            "date_format": self.date_format_combo.currentText().strip(),
            "table_schema": self.table_schema_combo.currentText().strip(),
            "initial_folders": self._get_selected_job_initial_folders(self.current_task),
            "task_id": self.current_task,
        }
    
    def _validate_inputs(self, cfg) -> bool:
        required = ["server", "database", "table_schema"]
        for key in required:
            if not cfg[key]:
                QMessageBox.warning(self, "Missing Input", f"Please enter: {key.replace('_', ' ').title()}")
                return False

        return True

    def _prompt_run_mode(self) -> str | None:
        """
        Returns: 'new', 'append', or None if cancelled.
        """
        box = QMessageBox(self)
        box.setWindowTitle("Run Mode")
        box.setText("Do you wish to start a new run or append to the previous?")
        new_btn = box.addButton("Yes - New Run", QMessageBox.ButtonRole.YesRole)
        app_btn = box.addButton("No - Append to Previous", QMessageBox.ButtonRole.NoRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked == new_btn:
            return "new"
        if clicked == app_btn:
            return "append"
        if clicked == cancel_btn:
            return None
        return None

    def _prompt_import_mode(self) -> str | None:
        """
        Returns: 'Import', 'Read', or None if cancelled.
        """
        box = QMessageBox(self)
        box.setWindowTitle("Import Mode")
        box.setText("Do you wish to import the data after scanning files?")
        import_btn = box.addButton("Import", QMessageBox.ButtonRole.YesRole)
        read_btn = box.addButton("Read", QMessageBox.ButtonRole.NoRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked == import_btn:
            return "Import"
        if clicked == read_btn:
            return "Read"
        if clicked == cancel_btn:
            return None
        return None

    def _prompt_read_fileobjects(self) -> bool | None:
        """
        Returns: True if user wants to read file objects, False if not, None if cancelled   
        """
        box = QMessageBox(self)
        box.setWindowTitle("Read File Objects?")
        box.setText("Do you wish to read file objects (e.g., names of Excel sheets, Access tables)?")
        yes_btn = box.addButton("Yes", QMessageBox.ButtonRole.YesRole)      
        no_btn = box.addButton("No", QMessageBox.ButtonRole.NoRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)   
        box.exec()  

        clicked = box.clickedButton()
        if clicked == yes_btn:
            return True     
        if clicked == no_btn:
            return False
        if clicked == cancel_btn:
            return None 

    def _prompt_read_fieldobjects(self) -> bool | None:
        """
        Returns: True if fields to be read, or None if cancelled.
        """
        box = QMessageBox(self)
        #box.setWindowTitle("Read File Object Fields and Load Content?")
        box.setWindowTitle("Read File Object Fields?")
        box.setText("Do you wish to read file object fields (e.g., Excel sheet columns, Access table fields)?")
        #\n\nSelect 'Read' to only read fields, or 'Import' to read fields and load content.")
        fields_only_btn = box.addButton("Yes", QMessageBox.ButtonRole.YesRole)
        no_btn = box.addButton("No", QMessageBox.ButtonRole.NoRole)
        #fields_and_load_btn = box.addButton("Import", QMessageBox.ButtonRole.NoRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked == fields_only_btn:
            return True
        if clicked == no_btn:
            return False
        if clicked == cancel_btn:
            return None
        return None

    def _run_import_step_1(self):
        """Collect UI values, validate them, and start an import."""
        import_config = self._get_inputs()

        if not self._validate_inputs(import_config):
            return

        # --- prompts first ---
        run_mode = self._prompt_run_mode()
        if run_mode is None:
            self.append_log("⏭️ Cancelled run mode selection.")
            return  

        read_objects = self._prompt_read_fileobjects()  
        if read_objects is None:
            self.append_log("⏭️ Cancelled read file objects selection.")
            return  

        read_fields = self._prompt_read_fieldobjects()
        if read_fields is None:
            self.append_log("⏭️ Cancelled read file fields selection.")
            return


        # --- selected job context ---
        jobid = self.context.current_task_id
        if not jobid:
            QMessageBox.warning(self, "No Job Selected", "Please select a job before running.")
            return

        initial_folders = import_config.get("initial_folders")

        if not initial_folders:
            QMessageBox.warning(self, "No Initial Folders", "Please specify at least one initial folder before running.")
            return
        else:
            grand_totals_by_ext, outstring = get_file_counts(initial_folders)
            for line in outstring:
                self.append_log(line)   
            grand_total = sum(grand_totals_by_ext.values())
            self.append_log(f"Grand total of all files: {grand_total}")

        if grand_total == 0:
            QMessageBox.information(self, "No Files", f"No matching files found in any initial folder")
            return

        # 1) resolve runversion (and insert RunVersion row if 'new')
        runversion = self.db_service.resolve_runversion(run_mode, jobid)
        self.append_log(f"▶ Job {jobid} using runversion={runversion} (mode={run_mode})")
        jobrunversionid = self.db_service.get_runversionid(runversion, jobid) 

        self.append_log(f"▶ JobRunVersionID: {jobrunversionid}")

        ### run datafile scan and insert here
        self.import_service.run_file_scan(jobrunversionid)
        if read_objects:
            self.append_log("▶ Reading file objects as requested.")
            if read_fields:
                self.append_log("▶ Reading file fields as requested.")
            else:
                self.append_log("▶ Skipping file fields as not requested.")

            self.import_service.run_file_object_scan(jobrunversionid,read_fields)
            
            if read_fields:
                self.append_log("▶ File scan and Obeject Scan completed including field scan.")
            else:
                self.append_log("▶ File scan and Object Scan completed without field scan.")
        else:
            self.append_log("▶ File Scan Complete. No file objects or field scan requested.")