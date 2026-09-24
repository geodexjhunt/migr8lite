"""Main application window."""

from PyQt6.QtWidgets import QDialog, QComboBox,QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QMessageBox, QListWidget, QListWidgetItem, QSplitter, QTreeWidget, QTreeWidgetItem
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import Qt
from config.config import Config
from app.services.db_service import DatabaseService
from app.models.migration_state import JobStateManager
from app.ui.tabs.data_explorer_tab import DynamicGrid
from config.dropdown_config import DROPDOWN_LOOKUPS
from app.models.migration_context import MigrationContext
from app.ui.task_edit_dialog import TaskEditDialog
from app.models.workflow_tab_registry import WORKFLOW_TABS, WorkflowPhase
from app.ui.tabs.data_explorer_tab import DataExplorerTab


class MainWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.db_service = DatabaseService(config)
        self.job_state = JobStateManager()
       
        app_config = config.app_config
        # Create shared context first - tabs will need it during construction
        self.context = MigrationContext(self)

        self._connect_database()
        self._update_database_info_cache()

        self.setWindowTitle(app_config.get("title", "migr8lite"))
        self.icon = QIcon(app_config.get("window_icon", None))
        self.setWindowIcon(self.icon)
        self.setGeometry(100, 100, app_config.get("window_width", 1400), app_config.get("window_height", 900))

        self._setup_ui()



    def _update_database_info_cache(self) -> None:
        if not self.db_service._connection:
            self.context.set_database_metadata([], [])
            #self.status_label.setText(
            #     "Unable to update local cache of migration DB schema"
            # )
            return

        user_defined_schemas = (
            self.db_service.get_user_defined_schemas_info()
        )

        all_tables_info = (
            self.db_service.get_all_tables_info_for_schemas(
                [
                    schema["SCHEMA_NAME"]
                    for schema in user_defined_schemas
                ]
            )
        )

        self.context.set_database_metadata(
            user_defined_schemas,
            all_tables_info,
        )




    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        title_label = QLabel("migr8lite - Migration Management System")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)

        # Persistent task toolbar
        task_layout = QHBoxLayout()
        task_layout.addWidget(QLabel("Migration Task:"))

        self.migration_task_combo = QComboBox()
        self.migration_task_combo.currentIndexChanged.connect(
            self._on_migration_task_changed
        )
        task_layout.addWidget(self.migration_task_combo, 1)

        self.btn_new_task = QPushButton("New")
        self.btn_edit_task = QPushButton("Edit")
        self.btn_delete_task = QPushButton("Delete")

        self.btn_new_task.clicked.connect(self._on_new_task)
        self.btn_edit_task.clicked.connect(self._on_edit_task)
        self.btn_delete_task.clicked.connect(self._on_delete_task)

        task_layout.addWidget(self.btn_new_task)
        task_layout.addWidget(self.btn_edit_task)
        task_layout.addWidget(self.btn_delete_task)

        main_layout.addLayout(task_layout)

        self.status_label = QLabel("Ready")

        # Main content area
        content_splitter = QSplitter(Qt.Orientation.Horizontal)


        self.task_table_panel = self._create_task_table_panel()
        content_splitter.addWidget(self.task_table_panel)

        self.workflow_tabs = self._create_workflow_tabs()
        content_splitter.addWidget(self.workflow_tabs)

        content_splitter.setStretchFactor(0, 0)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setSizes([240, 1000])

        main_layout.addWidget(content_splitter, 1)
        
        main_layout.addWidget(self.status_label)

        self._refresh_task_list()
        self._refresh_task_table_panel(self.migration_task_combo.currentData())

    def _create_workflow_tabs(self) -> QTabWidget:
        """Create workflow tabs from the central workflow-tab registry."""
        tab_widget = QTabWidget()

        # Lets MainWindow find a workflow panel later, if required.
        self.workflow_tab_pages: dict[WorkflowPhase, QWidget] = {}

        for tab_definition in WORKFLOW_TABS:
            if not tab_definition.enabled:
                continue

            tab_page = tab_definition.factory(self.context)
            tab_widget.addTab(tab_page, tab_definition.label)

            if tab_definition.phase is not None:
                self.workflow_tab_pages[tab_definition.phase] = tab_page

        # Data Explorer is deliberately last and remains a utility tab rather
        # than a task-scoped workflow phase.
        self.data_explorer_tab = DataExplorerTab(db_service=self.db_service, context=self.context)

        self.data_explorer_tab.status_changed.connect(self.status_label.setText)

        tab_widget.addTab(self.data_explorer_tab, "Data Explorer")

        return tab_widget

     


    def _create_task_table_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel) 

        layout.addWidget(QLabel("Objects in Current Task"))

        self.task_table_tree = QTreeWidget()
        self.task_table_tree.setHeaderLabel("File & Object >> Table")
        self.task_table_tree.itemClicked.connect(
            self._on_task_table_selected
        )

        layout.addWidget(self.task_table_tree)

        return panel   

    def _refresh_task_table_panel(self, task_id: int) -> None:
        """Refresh the task table panel to show tables for the given task."""
        try:
            tables = self.db_service.get_datafileobjects_for_task(task_id)
            all_tables_info = self.context.all_tables_info  # renamed - don't shadow
            self.task_table_tree.clear()

            # Group by distinct filename
            filename_dict: dict[str, list] = {}
            for row in tables:
                filename = row['filename']
                filename_dict.setdefault(filename, []).append(row)

            # Create tree structure
            for filename in sorted(filename_dict.keys()):
                file_item = QTreeWidgetItem([filename])

                for table in sorted(
                    filename_dict[filename],
                    key=lambda x: x['stagingtablename']
                ):
                    # Compare staging table info against actual imported tables
                    imported = any(
                        t['TABLE_NAME'] == table['stagingtablename']
                        and t['TABLE_SCHEMA'] == table['stagingtableschema']
                        for t in all_tables_info
                    )

                    item = QTreeWidgetItem(
                        [f"{table['stagingtablename']} {'✔' if imported else '✖'}"]
                    )
                    item.setData(0, Qt.ItemDataRole.UserRole, table)
                    file_item.addChild(item)

                self.task_table_tree.addTopLevelItem(file_item)

        except Exception as error:
            print(f"DEBUG: Failed to refresh task table panel: {error}")
            QMessageBox.critical(self, "Error", f"Failed to refresh task table panel: {error}")
            self.status_label.setText("Error refreshing task table panel")
        else:
            self.status_label.setText("Task table panel refreshed successfully")

    def _on_migration_task_changed(self) -> None:
        """When migration task changes, notify context."""
        task_id = self.migration_task_combo.currentData()
        print(f"DEBUG: Migration task changed to: {task_id}")
        self.context.set_task(task_id)
        
        # Refresh the task table panel to show tables for new task
        self._refresh_task_table_panel(task_id)

    def _on_task_table_selected(
        self,
        item: QTreeWidgetItem,
        column: int
    ) -> None:
        table_info = item.data(0, Qt.ItemDataRole.UserRole)

        if not isinstance(table_info, dict):
            return

        schema = table_info["stagingtableschema"]
        table_name = table_info["stagingtablename"]

        self.status_label.setText(
            f"Selected table: {schema}.{table_name}"
        )

        # Update shared context - this emits table_changed signal
        # Any tab connected to context.table_changed will react automatically
        self.context.set_table(table_info)

    def _on_new_task(self) -> None:
        """Open dialog to create a new migration task."""
        dialog = TaskEditDialog(parent=self, task_id=None)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_task_list()
            # Optionally auto-select the newly created task
            new_task_id = dialog.saved_task_id
            self._select_task_in_combo(new_task_id)

    def _on_edit_task(self) -> None:
        """Open dialog to edit the currently selected task."""
        task_id = self.migration_task_combo.currentData()
        if task_id is None:
            QMessageBox.warning(self, "No Task Selected", "Please select a task to edit")
            return
        
        dialog = TaskEditDialog(parent=self, task_id=task_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_task_list()

    def _on_delete_task(self) -> None:
        """Delete the currently selected task after confirmation."""
        task_id = self.migration_task_combo.currentData()
        if task_id is None:
            QMessageBox.warning(self, "No Task Selected", "Please select a task to delete")
            return
        
        task_name = self.migration_task_combo.currentText()
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete task '{task_name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db_service.delete_migration_task(task_id)
                self._refresh_task_list()
                self.status_label.setText(f"Deleted task: {task_name}")
            except Exception as e:
                QMessageBox.critical(self, "Delete Error", f"Failed to delete task: {e}")

    def _refresh_task_list(self) -> None:
        """Refresh the migration task list in the combo box."""
        try:
            tasks = self.db_service.get_migration_tasks()
            self.migration_task_combo.clear()
            for task in tasks:
                self.migration_task_combo.addItem(task['jobname'], task['jobid'])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to refresh task list: {e}")

    def _select_task_in_combo(self, task_id: int) -> None:
        """Select a task in the combo box by its ID."""
        index = self.migration_task_combo.findData(task_id)
        if index != -1:
            self.migration_task_combo.setCurrentIndex(index)
    
    def _connect_database(self) -> None:
        try:
            self.db_service.connect()
            #self.status_label.setText("Connected to database")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to connect: {e}")
            #self.status_label.setText("Disconnected")
    

    def closeEvent(self, event) -> None:
        """Prompt to save Data Explorer changes before exiting."""
        if self.data_explorer_tab._has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "Save Data Explorer changes before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )

            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

            if (
                reply == QMessageBox.StandardButton.Save
                and not self.data_explorer_tab.save_pending_changes()
            ):
                event.ignore()
                return

        try:
            self.db_service.disconnect()
        except Exception as error:
            print(f"DEBUG: Database disconnect failed: {error}")

        event.accept()

