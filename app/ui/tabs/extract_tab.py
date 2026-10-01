from multiprocessing import context

from pathlib import Path
from app.models.system_model import DataFileObjectHeaderRow, JobFolder
from app.services.extract_service import ExtractService
from config.config import Config
from PyQt6.QtWidgets import (
    QCheckBox, QSplitter, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QMessageBox,
)
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtCore import Qt
from typing import List, Dict
from app.models.migration_context import MigrationContext
from config.config import Config
from app.services.db_service import DatabaseService
from app.ui.tabs.dynamic_grid import DynamicGrid

class ExtractTab(QWidget):

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

        self.extract_service = ExtractService(
            context=self.context,
            db_service=self.db_service,  
        )

        self._updating_checks = False  # guard against recursive itemChanged signals

        self.current_table_schema = ""
        self.current_table_name = ""

        self._build_ui()

        self.context.task_changed.connect(self._on_task_changed)
        self.context.jobrunversion_changed.connect(self._on_jobrunversion_changed)


    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Objects in Current Task"))

        self.hide_dup_checkbox = QCheckBox("Hide Duplicates DataFiles?")
        self.hide_dup_checkbox.setChecked(True)  # default to hiding duplicates
        self.hide_dup_checkbox.stateChanged.connect(lambda _: self._refresh_extract_tree(self.context.current_task_id))
        header_layout.addWidget(self.hide_dup_checkbox)

        layout.addLayout(header_layout)

        central_layout = QVBoxLayout()

        central_splitter = QSplitter(Qt.Orientation.Horizontal)

        central_left_layout = QVBoxLayout()
        self.extract_tree = QTreeWidget()
        self.extract_tree.setHeaderLabel("File & Object >> Table")
        self.extract_tree.itemChanged.connect(self._on_item_changed)
        self.extract_tree.itemSelectionChanged.connect(self._on_selection_changed)
        central_left_layout.addWidget(self.extract_tree)
       
        central_splitter.addWidget(QWidget())
        central_splitter.widget(0).setLayout(central_left_layout)
    
        central_right_layout = QVBoxLayout()
        self.extract_details_label = QLabel("Preview files and assess header locations.")
        central_right_layout.addWidget(self.extract_details_label)
        self.preview_grid = DynamicGrid(context=self.context)
        central_right_layout.addWidget(self.preview_grid)

        central_splitter.addWidget(QWidget())
        central_splitter.widget(1).setLayout(central_right_layout)
 
        central_layout.addWidget(central_splitter)

        layout.addLayout(central_layout)
        
        extract_footer_layout = QVBoxLayout()

        self.extract_selected_button = QPushButton("Extract Selected Files")
        self.extract_selected_button.clicked.connect(self._on_extract_selected_clicked)
        extract_footer_layout.addWidget(self.extract_selected_button)

        self.extract_all_button = QPushButton("Extract All Files")
        self.extract_all_button.clicked.connect(self._on_extract_all_clicked)
        extract_footer_layout.addWidget(self.extract_all_button)   
        layout.addLayout(extract_footer_layout)


    # ------------------------------------------------------------------
    # Context signal handlers
    # ------------------------------------------------------------------

    def _on_task_changed(self, task_id: int) -> None:
        """Clear or refresh task-scoped content."""
        jobrunversion = self.context.current_jobrunversionid
        if jobrunversion is None:
            return
        self._refresh_extract_tree(task_id)

    def _on_jobrunversion_changed(self, jobrunversionid: int) -> None:
        """Load import details for the newly selected task table."""
        jobrunversion = self.context.current_jobrunversionid
        if jobrunversion is None:
            return
        task_id = self.context.current_task_id
        self._refresh_extract_tree(task_id)
    # ------------------------------------------------------------------
    # Tree building
    # ------------------------------------------------------------------

    def _refresh_extract_tree(self, task_id: int) -> None:
        """Refresh the extract tree, always grouped by folder, with checkboxes."""
        try:
            jobrunversion = self.context.current_jobrunversionid
            if jobrunversion is None:
                return
            self.db_service.refresh_jobfolder_cache(jobrunversion)
            
            tables: List[Dict] = []
            datafiles: dict[int, Dict] = {}           
            
            tables = self.db_service.get_datafileobjects_for_task(task_id)
            datafiles = self.db_service.get_datafile_occurrence_number(task_id)
            all_tables_info = self.context.all_tables_info

            self._updating_checks = True  # suppress itemChanged while (re)building
            self.extract_tree.clear()

            # Group by (folderid, filename)
            filename_dict: dict[tuple[int, str], list] = {}
            for row in tables:
                filename = row["filename"]
                folderid = row["folderid"]
                filename_dict.setdefault((folderid, filename), []).append(row)

            prevfolderid: int = -1
            alldups: bool = True
            folder_item: QTreeWidgetItem | None = None

            for folderid, filename in sorted(filename_dict.keys()):
                folder = self.db_service.get_jobfolder(folderid)
                folderpath = folder.folderpath if folder else ""
                fileid = filename_dict[(folderid, filename)][0]['jobfileid']
                datafile_occurrence_number = datafiles[fileid]['occurrence_number'] if fileid in datafiles else 1
                #print(f"DEBUG: fileid = {fileid}, datafile_occurrence_number = {datafile_occurrence_number}")
                #print(f"Processing folder: {folderpath}")
                if folderid != prevfolderid:
                    alldups = True
                    folder_item = QTreeWidgetItem([folderpath])
                    folder_item.setExpanded(True)
                    folder_item.setData(0, Qt.ItemDataRole.UserRole, {"level": "folder", "folderid": folderid})
                    folder_item.setFlags(
                        folder_item.flags()
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsAutoTristate
                        | Qt.ItemFlag.ItemIsEnabled
                    )
                    folder_item.setCheckState(0, Qt.CheckState.Unchecked)
                    self.extract_tree.addTopLevelItem(folder_item)
                    prevfolderid = folderid

                file_item = QTreeWidgetItem([filename])

                if datafile_occurrence_number > 1:
                    file_item.setForeground(0, QBrush(QColor("red")))
                else:
                    file_item.setForeground(0, QBrush(QColor("black")))
                    alldups = False
    
                file_item.setData(0, Qt.ItemDataRole.UserRole, {"level": "file", "folderid": folderid, "filename": filename, "occurrence_number": datafile_occurrence_number})
                file_item.setFlags(
                    file_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsAutoTristate
                )
                file_item.setCheckState(0, Qt.CheckState.Unchecked)
               

                for table in sorted(
                    filename_dict[(folderid, filename)],
                    key=lambda x: x["stagingtablename"] or "",
                ):
                    staging_name = table["stagingtablename"]
                    staging_schema = table["stagingtableschema"]
                    imported = (
                        staging_name is not None
                        and staging_schema is not None
                        and any(
                            t["TABLE_NAME"] == staging_name
                            and t["TABLE_SCHEMA"] == staging_schema
                            for t in all_tables_info
                        )
                    )

                    table_item = QTreeWidgetItem(
                        [f"{table['objectname']} {'✔' if imported else '✖'} {staging_name or '(no staging table)'}"]
                    )
                    table_item.setData(0, Qt.ItemDataRole.UserRole, {"level": "table", "row": table, "occurrence_number": datafile_occurrence_number})
                    
                    table_item.setFlags(table_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    table_item.setCheckState(0, Qt.CheckState.Unchecked)

                    if datafile_occurrence_number > 1:
                        table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                        if self.hide_dup_checkbox.isChecked():
                            table_item.setHidden(True)
                    file_item.addChild(table_item)

                if datafile_occurrence_number > 1:
                    file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                    if self.hide_dup_checkbox.isChecked():
                        file_item.setHidden(True)
                folder_item.addChild(file_item)
                if alldups == True:
                    folder_item.setFlags(folder_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                    folder_item.setForeground(0, QBrush(QColor("red")))
                    if self.hide_dup_checkbox.isChecked():
                        folder_item.setHidden(True)
            self._updating_checks = False

        except Exception as error:
            self._updating_checks = False
            print(f"DEBUG: Failed to refresh extract tree: {error}")
            QMessageBox.critical(self, "Error", f"Failed to refresh extract tree: {error}")

    # ------------------------------------------------------------------
    # Checkbox propagation
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Propagate check state: parent -> children (top-down), child -> parent (bottom-up)."""
        if self._updating_checks or column != 0:
            return

        self._updating_checks = True
        try:
            new_state = item.checkState(0)

            # Only propagate a definite (non-partial) state downward.
            if new_state != Qt.CheckState.PartiallyChecked:
                self._set_children_check_state(item, new_state)

            self._update_parent_check_state(item.parent())
        finally:
            self._updating_checks = False

    def _set_children_check_state(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        """Recursively apply a check state to all children of `item`."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_check_state(child, state)

    def _update_parent_check_state(self, parent: QTreeWidgetItem | None) -> None:
        """Recalculate a parent's check state based on its children, and bubble up."""
        if parent is None:
            return

        states = {parent.child(i).checkState(0) for i in range(parent.childCount())}

        if states == {Qt.CheckState.Checked}:
            parent.setCheckState(0, Qt.CheckState.Checked)
        elif states == {Qt.CheckState.Unchecked}:
            parent.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)

        self._update_parent_check_state(parent.parent())

    # ------------------------------------------------------------------
    # Querying selected items
    # ------------------------------------------------------------------

    def get_selected_tables(self) -> list[dict]:
        """Return the raw `row` dicts for every checked leaf (table) item."""
        selected: list[dict] = []

        def walk(item: QTreeWidgetItem) -> None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("level") == "table":
                if item.checkState(0) == Qt.CheckState.Checked:
                    selected.append(data["row"])
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.extract_tree.topLevelItemCount()):
            walk(self.extract_tree.topLevelItem(i))

        return selected

    def get_all_unique_tables(self) -> list[dict]:
        """Return the raw `row` dicts for every table item where occurrence_number = 1."""
        all_tables: list[dict] = []

        def walk(item: QTreeWidgetItem) -> None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("level") == "table":
                if data.get("occurrence_number") == 1:
                    all_tables.append(data["row"])
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.extract_tree.topLevelItemCount()):
            walk(self.extract_tree.topLevelItem(i))

        return all_tables

    def _on_extract_all_clicked(self) -> None:
        selected_tables = self.get_all_unique_tables()

        # TODO: replace with real extraction logic
        print(f"DEBUG: Extracting all {len(selected_tables)} table(s):")
        for row in selected_tables:
            print(f"  - {row.get('objectname')} ({row.get('stagingtablename')})")

    def _on_extract_selected_clicked(self) -> None:
        selected_tables = self.get_selected_tables()

        if not selected_tables:
            QMessageBox.information(self, "No Selection", "No tables are selected for extraction.")
            return

        # TODO: replace with real extraction logic
        print(f"DEBUG: Extracting {len(selected_tables)} selected table(s):")
        for row in selected_tables:
            print(f"  - {row.get('objectname')} ({row.get('stagingtablename')})")

    # ------------------------------------------------------------------
    #  Table Preview Generation
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        #print("On Selection changed fired")
        selected_items = self.extract_tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            user_data = item.data(0, Qt.ItemDataRole.UserRole)
            #print("User data retrieved:", user_data)
            if isinstance(user_data, dict) and user_data.get("level") == "table":
                #print("Table selected with user_data:", user_data)
                self.extract_details_label.setText(f"Selected: {user_data.get('objectname', 'Unknown')}")
                self._load_preview(user_data)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        #print("On Item clicked fired")
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("level") == "table":
            self.extract_details_label.setText(f"Selected: {data.get('objectname', 'Unknown')}")
            self._load_preview(data)
            
    def _load_preview(self, data: dict):
        #print("Loading preview for data:", data)
        full_row = data["row"]
            
        datafileobjectid = full_row["datafileobjectid"]
        objectname = full_row["objectname"]
        staging_tablename = full_row["stagingtablename"]
        staging_schema = full_row["stagingtableschema"]
        #print(f"Full row data: {full_row}")
        if self.current_table_name != staging_tablename or self.current_table_schema != staging_schema:
            self.current_table_name = staging_tablename
            self.current_table_schema = staging_schema

            self.preview_grid.clear_contents()

            header_row_from_cache: DataFileObjectHeaderRow = self.db_service.get_datafileheaderrow_object_by_datafileobjectid_and_headernum(datafileobjectid, 1)
            header_row = header_row_from_cache.rownumber if header_row_from_cache else 1
            folder_from_cache: JobFolder = self.db_service.get_jobfolder(full_row["folderid"])
            folderpath = folder_from_cache.folderpath
            filename = full_row["filename"]
            #print(f"Job folder from cache: {folder_from_cache}")
            # combine folderpath and filename as a path 
            file_path = Path(folderpath) / filename

            preview_df = self.extract_service.preview_with_header(
                file_path=file_path,
                sheet_name=objectname,
                header_row=header_row
            )

            cols: List[Dict]
            rows: List[Dict]

            # Cols needs to have the Column names as COLUMN_NAME in the dict
            cols = [{'COLUMN_NAME': col} for col in preview_df.columns]
            # rows is a list of data row dicts
            rows = [dict(zip(preview_df.columns, row)) for row in preview_df.values.tolist()]

            editable = False
            #print(f"Preview DataFrame loaded with columns: {cols} and number of rows: {len(rows)}")
            self.preview_grid.load_data(rows=rows, columns=cols, editable=editable)