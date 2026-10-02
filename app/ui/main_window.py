"""Main application window."""

from tokenize import group
from typing import Dict, List

from PyQt6.QtWidgets import QCheckBox, QDialog, QComboBox,QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QMessageBox, QListWidget, QListWidgetItem, QSplitter, QTreeWidget, QTreeWidgetItem
from PyQt6.QtGui import QBrush, QBrush, QColor, QIcon, QFont, QAction
from PyQt6.QtCore import Qt
from config.config import Config
from app.services.db_service import DatabaseService
from app.models.migration_state import JobStateManager
from app.ui.tabs.data_explorer_tab import DynamicGrid
from config.dropdown_config import DROPDOWN_LOOKUPS
from app.models.migration_context import MigrationContext
from app.ui.task_edit_dialog import TaskEditDialog
from app.ui.tabs.workflow_tab_registry import WORKFLOW_TABS, WorkflowPhase
from app.ui.tabs.data_explorer_tab import DataExplorerTab
from app.ui.theme import set_dark_mode

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

        # all refreshing now in the above call to _update_database_info_cache()
        #self.db_service.refresh_job_cache()
        #self.db_service.refresh_jobrunversion_cache()
        #self.db_service.refresh_table_cache()
        #self.db_service.refresh_datafile_cache()
        #self.db_service.refresh_datafileobject_cache()
        #self.db_service.refresh_datafileobjectfield_cache() 
        #self.db_service.refresh_datafileobjectfieldheader_cache()
        #self.db_service.refresh_datafileobjectheaderrow_cache()

        #if self.context.current_jobrunversionid is not None:
        #    self.db_service.refresh_jobfolder_cache(self.context.current_jobrunversionid)
        #    self.db_service.refresh_jobfile_cache(self.context.current_jobrunversionid)

        self.setWindowTitle(app_config.get("title", "migr8lite"))
        self.icon = QIcon(app_config.get("window_icon", None))
        self.setWindowIcon(self.icon)
        self.setGeometry(100, 100, app_config.get("window_width", 1400), app_config.get("window_height", 900))

        self.dark_mode_enabled = False

        self._setup_ui()
        self._create_view_menu()
        self._toggle_dark_mode(self.dark_mode_enabled)



    def _update_database_info_cache(self) -> None:
        if self.db_service._connection:
            self.db_service.refresh_table_cache()
            self.db_service.refresh_datafile_cache()
            self.db_service.refresh_job_cache()
            self.db_service.refresh_jobrunversion_cache()
            if self.context.current_jobrunversionid is not None:
                self.db_service.refresh_jobfolder_cache(self.context.current_jobrunversionid)
                self.db_service.refresh_jobfile_cache(self.context.current_jobrunversionid)
            self.db_service.refresh_datafileobject_cache()
            self.db_service.refresh_datafileobjectfield_cache() 
            self.db_service.refresh_datafileobjectfieldheader_cache()
            self.db_service.refresh_datafileobjectheaderrow_cache()
   
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

        task_layout.addWidget(QLabel("Run Version:"))
        self.jobrunversion_combo = QComboBox()
        self.jobrunversion_combo.currentIndexChanged.connect(
            self._on_jobrunversion_changed
        )
        task_layout.addWidget(self.jobrunversion_combo, 1)

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
        self._refresh_jobrunversion_list()
        self._refresh_task_table_panel(self.migration_task_combo.currentData())


    
    def _create_view_menu(self) -> None:
        """Create view-related menu actions."""
        view_menu = self.menuBar().addMenu("View")

        self.dark_mode_action = QAction("Dark Mode", self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(False)

        self.dark_mode_action.toggled.connect(
            self._toggle_dark_mode
        )

        view_menu.addAction(self.dark_mode_action)

    def _create_workflow_tabs(self) -> QTabWidget:
        """Create workflow tabs from the central workflow-tab registry."""
        tab_widget = QTabWidget()

        # Lets MainWindow find a workflow panel later, if required.
        self.workflow_tab_pages: dict[WorkflowPhase, QWidget] = {}

        for tab_definition in WORKFLOW_TABS:
            if not tab_definition.enabled:
                continue

            tab_page = tab_definition.factory(self.context, self.config, self.db_service)
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


        self.group_by_file = QCheckBox("Group by Folder?")  
        self.group_by_file.setChecked(False)
        self.group_by_file.stateChanged.connect(lambda _: self._refresh_task_table_panel(self.migration_task_combo.currentData()))

        header_layout = QHBoxLayout()   
        
        header_layout.addWidget(QLabel("Objects in Current Task"))
        header_layout.addWidget(self.group_by_file)

        layout.addLayout(header_layout)

        self.task_table_tree = QTreeWidget()
        self.task_table_tree.setHeaderLabel("File & Object >> Table")
        self.task_table_tree.itemClicked.connect(
            self._on_task_table_selected
        )

        layout.addWidget(self.task_table_tree)

        return panel   

    def _refresh_task_table_panel(self, task_id: int) -> None:
        """Refresh the task table panel to show tables for the given task."""
        #print(f"DEBUG: jobfolder cache size = {len(self.db_service._jobfolders_by_id)}")

        try:
            tables: List[Dict] = []
            datafiles: dict[int, Dict] = {}
            tables = self.db_service.get_datafileobjects_for_task(task_id)
            datafiles = self.db_service.get_datafile_occurrence_number(task_id)
            
            all_tables_info = self.context.all_tables_info  # renamed - don't shadow
            self.task_table_tree.clear()

            group_by_file = self.group_by_file.isChecked()

            # Group by distinct filename
            filename_dict: dict[tuple[int, str], list] = {}
            for row in tables:
                filename = row['filename']
                folderid = row['folderid']
                
                #print(f"DEBUG: row folderid = {folderid!r} (type={type(folderid)})")
                filename_dict.setdefault((folderid, filename), []).append(row)

            if group_by_file:
                for folderid in sorted({key[0] for key in filename_dict.keys()}):
                    folder = self.db_service.get_jobfolder(folderid)
                    if folder:
                        folder_item = QTreeWidgetItem([f"{folder.folderpath}"])
                        folder_item.setExpanded(True)
                        folder_item.setData(0, Qt.ItemDataRole.UserRole, folderid)
                        folder_item.setFlags(folder_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        folder_item.setCheckState(0, Qt.CheckState.Unchecked)
                        folder_item.setForeground(0, QBrush(QColor("blue")))
                        folder_item.setBackground(0, QBrush(QColor("lightgray")))

            prevfolderid: int = -1      
            alldups: bool = True
            # Create tree structure
            for folderid, filename in sorted(filename_dict.keys()):
                folder = self.db_service.get_jobfolder(folderid)
                folderpath = folder.folderpath if folder else ""
                fileid = filename_dict[(folderid, filename)][0]['jobfileid']
                datafile_occurrence_number = datafiles[fileid]['occurrence_number'] if fileid in datafiles else 1
                #print(f"DEBUG: fileid = {fileid}, datafile_occurrence_number = {datafile_occurrence_number}")
                file_item = QTreeWidgetItem([f"{filename} -- {folderpath}"])

                if group_by_file and folderid != prevfolderid:
                    alldups = True
                    folder_item = QTreeWidgetItem([f"{folder.folderpath}"])
                    folder_item.setExpanded(True)
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, folderid)
                    #folder_item.setFlags(folder_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    #folder_item.setCheckState(0, Qt.CheckState.Unchecked)
                    folder_item.setForeground(0, QBrush(QColor("blue")))
                    folder_item.setBackground(0, QBrush(QColor("lightgray")))

                if datafile_occurrence_number > 1:
                    file_item.setForeground(0, QBrush(QColor("red")))
                else:
                    file_item.setForeground(0, QBrush(QColor("black")))
                    alldups = False

                prevfolderid = folderid
                for table in sorted(
                    filename_dict[(folderid, filename)],
                    key=lambda x: x['stagingtablename'] or "",
                ):
                    # Compare staging table info against actual imported tables
                    staging_name = table["stagingtablename"]
                    staging_schema = table["stagingtableschema"]
                    imported = ( 
                        staging_name is not None
                        and staging_schema is not None
                        and any(
                        t['TABLE_NAME'] == table['stagingtablename']
                        and t['TABLE_SCHEMA'] == table['stagingtableschema']
                        for t in all_tables_info
                        )
                    )

                    item = QTreeWidgetItem(
                        [f"{table['objectname']} {'✔' if imported else '✖'} [{staging_schema or '(no schema)'}].[{staging_name or '(no staging table)'}]"]
                    )
                    item.setData(0, Qt.ItemDataRole.UserRole, table)
                    file_item.addChild(item)

                if group_by_file:
                    folder_item.addChild(file_item)
                    if alldups:
                        folder_item.setForeground(0, QBrush(QColor("red")))
                    self.task_table_tree.addTopLevelItem(folder_item)
                else:
                    self.task_table_tree.addTopLevelItem(file_item)

        except Exception as error:
            print(f"DEBUG: Failed to refresh task table panel: {error}")
            QMessageBox.critical(self, "Error", f"Failed to refresh task table panel: {error}")
            self.status_label.setText("Error refreshing task table panel")
        else:
            self.status_label.setText("Task table panel refreshed successfully")

    def _on_jobrunversion_changed(self) -> None:
        jobrunversion_id = self.jobrunversion_combo.currentData()
        self.context.set_jobrunversion(jobrunversion_id)

        self.db_service.refresh_jobfolder_cache(jobrunversion_id)
        self.db_service.refresh_jobfile_cache(jobrunversion_id)      

    def _on_migration_task_changed(self) -> None:
        """When migration task changes, notify context."""
        task_id = self.migration_task_combo.currentData()
        print(f"DEBUG: Migration task changed to: {task_id}")
        self.context.set_task(task_id)

        self.db_service.refresh_table_cache()
        self.db_service.refresh_datafile_cache()
        if self.context.current_jobrunversionid is not None:
            self.db_service.refresh_jobfolder_cache(self.context.current_jobrunversionid)
            self.db_service.refresh_jobfile_cache(self.context.current_jobrunversionid)

        
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

    def _refresh_jobrunversion_list(self) -> None:
        """Refresh the job run version list in the combo box."""
        if self.context.current_task_id is None:
            self.jobrunversion_combo.clear()
            return
        else:
            try:
                jobrunversions = self.db_service.get_jobrunversions(self.context.current_task_id)
                self.jobrunversion_combo.clear()
                for jobrunversion in jobrunversions:
                    self.jobrunversion_combo.addItem(f"{jobrunversion.runversion}", jobrunversion.jobrunversionid)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to refresh job run version list: {e}")

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


    def _toggle_dark_mode(self, enabled: bool) -> None:
        """Switch between dark and light application themes."""
        self.dark_mode_enabled = enabled
        set_dark_mode(enabled)

        self.dark_mode_action.setText(
            "Light Mode" if enabled else "Dark Mode"
        )

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

