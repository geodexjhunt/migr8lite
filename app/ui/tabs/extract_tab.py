from datetime import datetime, date
from multiprocessing import context
import json
from pathlib import Path
from collections import defaultdict
from app.models.system_model import DataFileObjectHeaderRow, ExistingTablePolicy, JobFolder, IssueType, TableExtractRequest, ExtractResult
from app.services.extract_service import ExtractService
from config.config import Config
from PyQt6.QtWidgets import (
    QCheckBox, QSplitter, QTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QMessageBox,QDialog
)
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtCore import Qt
from typing import List, Dict
from app.models.migration_context import MigrationContext
from config.config import Config
from app.services.db_service import DatabaseService
from app.ui.tabs.dynamic_grid import DynamicGrid
from app.ui.tabs.synced_dual_grid import SyncedDualGrid

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
        self.current_datafileobjectid = None
        self.current_header_number = None
        self.current_data = {
                "row": {
                    "datafileobjectid": None,
                    "headerrownumber": None,
                    "previewrownumber": None,
                    "objectname": "",
                    "stagingtablename": "",
                    "stagingtableschema": ""
                }
        }
                

        self._build_ui()

        self.context.task_changed.connect(self._on_task_changed)
        self.context.jobrunversion_changed.connect(self._on_jobrunversion_changed)


    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Objects in Current Task"))

        self.hide_dup_checkbox = QCheckBox("Hide Duplicates DataFiles?")
        self.hide_dup_checkbox.setChecked(True)  # default to hiding duplicates
        #self.hide_dup_checkbox.stateChanged.connect(lambda _: self._refresh_extract_tree(self.context.current_task_id))
        header_layout.addWidget(self.hide_dup_checkbox)

        self.hide_extracted_checkbox = QCheckBox("Hide Extracted DataFiles?")
        self.hide_extracted_checkbox.setChecked(True)  # default to hiding extracted files
        #self.hide_extracted_checkbox.stateChanged.connect(lambda _: self._refresh_extract_tree(self.context.current_task_id))
        header_layout.addWidget(self.hide_extracted_checkbox)
        header_layout.addStretch()  # Push everything to the left

        self.hide_extracted_checkbox.toggled.connect(lambda _: self._apply_visibility())
        self.hide_dup_checkbox.toggled.connect(lambda _: self._apply_visibility())


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
        #self.preview_grid = DynamicGrid(context=self.context)
        #central_right_layout.addWidget(self.preview_grid)
        self.dual_grid = SyncedDualGrid(context=self.context, parent=self)
        self.dual_grid.header_number_changed.connect(self._on_header_number_changed)
        self.dual_grid.header_number_saved.connect(self._on_header_number_saved)
        central_right_layout.addWidget(self.dual_grid)


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
            all_tables_info = self.db_service._all_tables_info

            self._updating_checks = True  # suppress itemChanged while (re)building

            #store the expanded state of the tree
            expanded_items = set()
            self._collect_expanded(self.extract_tree.invisibleRootItem(), expanded_items)

            self.extract_tree.clear()
            
            # Group by (folderid, filename)
            filename_dict: dict[tuple[int, str], list] = {}
            for row in tables:
                filename = row["filename"]
                folderid = row["folderid"]
                filename_dict.setdefault((folderid, filename), []).append(row)

            prevfolderid: int = -1
            folder_item: QTreeWidgetItem | None = None

            for folderid, filename in sorted(filename_dict.keys()):
                allfileimported = True
                folder = self.db_service.get_jobfolder(folderid)
                folderpath = folder.folderpath if folder else ""
                fileid = filename_dict[(folderid, filename)][0]['jobfileid']
                datafile_occurrence_number = datafiles[fileid]['occurrence_number'] if fileid in datafiles else 1
                #print(f"DEBUG: fileid = {fileid}, datafile_occurrence_number = {datafile_occurrence_number}")
                #print(f"Processing folder: {folderpath}")
                if folderid != prevfolderid:
                    #print(f"DEBUG: Processing new folder: {folderid}")


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
                    #self.extract_tree.addTopLevelItem(folder_item)
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
                           t['TABLE_NAME'] == table['stagingtablename']
                           and t['TABLE_SCHEMA'] == table['stagingtableschema']
                           for t in all_tables_info
                           )
                    )

                    table_item = QTreeWidgetItem(
                        [f"{table['objectname']} {'✔' if imported else '✖'} [{staging_schema or '(no schema)'}].[{staging_name or '(no staging table)'}]"]
                    )

                    table_item.setData(0, Qt.ItemDataRole.UserRole, {"level": "table", "row": table, "occurrence_number": datafile_occurrence_number, "imported":imported})
                    
                    table_item.setFlags(table_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    table_item.setCheckState(0, Qt.CheckState.Unchecked)

                    if imported:
                        table_item.setBackground(0, QBrush(QColor("green")))
                        table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                     

                    if datafile_occurrence_number > 1:
                        table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)

                    file_item.addChild(table_item)

                if datafile_occurrence_number > 1:
                    file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                
                folder_item.addChild(file_item)
                
                self.extract_tree.addTopLevelItem(folder_item)
        
             # restore the expanded state of the tree after rebuilding
            self._restore_expanded(self.extract_tree.invisibleRootItem(), expanded_items) 
            self._apply_visibility()
            self._updating_checks = False

        except Exception as error:
            self._updating_checks = False
            print(f"DEBUG: Failed to refresh extract tree: {error}")
            QMessageBox.critical(self, "Error", f"Failed to refresh extract tree: {error}")

    # ------------------------------------------------------------------
    # Tree Helpers
    # ------------------------------------------------------------------


    def _item_key(self, item) -> str | None:
        """Convert item's UserRole dict to a hashable string key."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return None
        # Sort keys for consistent ordering
        return json.dumps(data, sort_keys=True)

    def _collect_expanded(self, parent, out: set) -> None:
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.isExpanded():
                key = self._item_key(child)
                if key is not None:
                    out.add(key)
            self._collect_expanded(child, out)

    def _restore_expanded(self, parent, keys: set) -> None:
        for i in range(parent.childCount()):
            child = parent.child(i)
            if self._item_key(child) in keys:
                child.setExpanded(True)
            self._restore_expanded(child, keys)

    def _apply_visibility(self) -> None:
        hide_extracted = self.hide_extracted_checkbox.isChecked()
        hide_dups = self.hide_dup_checkbox.isChecked()
        
        root = self.extract_tree.invisibleRootItem()
        for i in range(root.childCount()):
            folder = root.child(i)
            visible_files = 0
            dupfiles = 0
            importedfiles = 0

            for j in range(folder.childCount()):
                file_item = folder.child(j)
                fdata = file_item.data(0, Qt.ItemDataRole.UserRole) or {}
                is_dup = fdata.get("occurrence_number", 1) > 1
                imported_tables = 0
                visible_tables = 0
                if is_dup:
                    dupfiles += 1
                for k in range(file_item.childCount()):
                    table_item = file_item.child(k)
                    tdata = table_item.data(0, Qt.ItemDataRole.UserRole) or {}
                    imported = tdata.get("imported", False)
                    if is_dup:
                        table_item.setForeground(0, QBrush(QColor("red")))
                    if imported:
                        table_item.setBackground(0, QBrush(QColor("green")))
                        imported_tables += 1
                    hide_table = (hide_extracted and imported) \
                                or (hide_dups and is_dup)
                    table_item.setHidden(hide_table)
                    if not hide_table:
                        visible_tables += 1
                # colour a file green if all its tables are imported
                if imported_tables == file_item.childCount() and file_item.childCount() > 0:
                    file_item.setBackground(0, QBrush(QColor("green")))
                    importedfiles += 1
                if is_dup:
                    file_item.setForeground(0, QBrush(QColor("red")))
                # hide a file if it is a hidden dup, or has tables but none are left visible
                hide_file = (hide_dups and is_dup) \
                            or (hide_extracted and file_item.childCount() > 0 and visible_tables == 0)
                file_item.setHidden(hide_file)
                if not hide_file:
                    visible_files += 1
            if importedfiles == folder.childCount() and folder.childCount() > 0:
                folder.setBackground(0, QBrush(QColor("green")))
            if dupfiles == folder.childCount() and folder.childCount() > 0:
                folder.setForeground(0, QBrush(QColor("red")))

            folder.setHidden((hide_dups or hide_extracted) and visible_files == 0)
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


    # ------------------------------------------------------------------
    #  Button Handling
    # ------------------------------------------------------------------

    def _on_extract_all_clicked(self) -> None:
        selected_tables = self.get_all_unique_tables()
        if not selected_tables:
            QMessageBox.information(self, "No Selection", "No tables are available for extraction.")
            return
        else:
            self._extract_tables(selected_tables)

    def _on_extract_selected_clicked(self) -> None:
        selected_tables = self.get_selected_tables()

        if not selected_tables:
            QMessageBox.information(self, "No Selection", "No tables are selected for extraction.")
            return
        else:
            self._extract_tables(selected_tables)
    
    # ------------------------------------------------------------------
    #  Signal Change Handling
    # ------------------------------------------------------------------

    def _on_header_number_changed(self, value: int) -> None:
        print(f"Header number changed to: {value}")
        preview_data = self.current_data
        preview_data["row"]["previewrownumber"] = value
        if isinstance(preview_data, dict):
            #print(f"Preview data updated: {preview_data}")
            self.extract_details_label.setText(f"Selected: {preview_data["row"]["objectname"] or 'Unknown'}")
            self._load_preview(preview_data)

    def _on_header_number_saved(self, value: int) -> None:
        print(f"Header number saved as: {value}")
        currentheaderrow = self.current_data["row"]["headerrownumber"]
        currentdatafileobjectid = self.current_data["row"]["datafileobjectid"]
        if value != currentheaderrow or currentheaderrow is None:
            newdatafileobjectheaderrow = DataFileObjectHeaderRow(
                datafileobjectid=currentdatafileobjectid,
                headernum=1,
                rownumber=value,
                datafileobjectheaderrowid=-1,
                timestamp=datetime.now()
            )
            return_value = self.db_service.upsert_datafileobjectheaderrow_row(newdatafileobjectheaderrow)
            print(f"Upsert return value: {return_value}")
            self.current_data["row"]["headerrownumber"] = value
            self.current_data["row"]["previewrownumber"] = None
            self._load_preview(self.current_data)
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
                self.extract_details_label.setText(f"Selected: {user_data["row"]["objectname"] or 'Unknown'}")
                user_data["row"]["previewrownumber"] = None
                user_data["row"]["headerrownumber"] = None
                self.current_data = user_data
                self._load_preview(user_data)
            ## if its a file item, but the file item only contains 1 table, then get the table
            elif isinstance(user_data, dict) and user_data.get("level") == "file":
                child_count = item.childCount()
                if child_count == 1:
                    child_item = item.child(0)
                    child_data = child_item.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(child_data, dict) and child_data.get("level") == "table":
                        self.extract_details_label.setText(f"Selected: {child_data["row"]["objectname"] or 'Unknown'}")
                        child_data["row"]["previewrownumber"] = None
                        child_data["row"]["headerrownumber"] = None                      
                        self.current_data = child_data

                        self._load_preview(child_data)
           
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        #print("On Item clicked fired")
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data["row"]["datafileobjectid"] != self.current_data["row"]["datafileobjectid"]:
                print("Selected item is different from the current data.")
                data["row"]["previewrownumber"] = None
                data["row"]["headerrownumber"] = None
                if isinstance(data, dict) and data.get("level") == "table":
                    self.extract_details_label.setText(f"Selected: {data["row"]["objectname"] or 'Unknown'}")
                    self.current_data = data
                    self._load_preview(data)
        else:
            print("Selected item is the same as the current data.")
 
    def _load_preview(self, data: dict):
        #print("Loading preview for data:", data)
        full_row = data["row"]
            
        datafileobjectid = full_row["datafileobjectid"]
        objectname = full_row["objectname"]
        staging_tablename = full_row["stagingtablename"]
        staging_schema = full_row["stagingtableschema"]
        previewheader = full_row["previewrownumber"]   

        self.dual_grid.clear_contents()

        if previewheader is not None:
            header_row = previewheader
        else:
            header_row_from_cache: DataFileObjectHeaderRow = self.db_service.get_datafileheaderrow_object_by_datafileobjectid_and_headernum(datafileobjectid, 1)
            header_row = header_row_from_cache.rownumber if header_row_from_cache else 1
            self.current_data["row"]["headerrownumber"] = header_row

        print(f"Refreshing Preview with Header row: {header_row}")
        folder_from_cache: JobFolder = self.db_service.get_jobfolder(full_row["folderid"])
        folderpath = folder_from_cache.folderpath
        filename = full_row["filename"]
        #print(f"Job folder from cache: {folder_from_cache}")
        # combine folderpath and filename as a path 
        file_path = Path(folderpath) / filename

        pre_header_df, data_df = self.extract_service.preview_with_header(
            file_path=file_path,
            sheet_name=objectname,
            header_row=header_row
        )

        # Split into pre-header and data based on _is_pre_header flag
        #pre_header_df = preview_df[preview_df['_is_pre_header'] == True]
        #data_df = preview_df[preview_df['_is_pre_header'] == False]


        cols_for_both: List[Dict]
        #rows: List[Dict]
        top_rows: List[Dict]
        bottom_rows: List[Dict]


        # Cols needs to have the Column names as COLUMN_NAME in the dict
        cols_for_both = [{'COLUMN_NAME': col} for col in data_df.columns]
        # rows is a list of data row dicts
        #rows = [dict(zip(data_df.columns, row)) for row in data_df.values.tolist()]

        # Build rows, excluding metadata columns
        top_rows = [
            {col: row.get(col, "") for col in data_df.columns}
            for _, row in pre_header_df.iterrows()
        ]
        bottom_rows = [
            {col: row.get(col, "") for col in data_df.columns}
            for _, row in data_df.iterrows()
        ]


        editable = False
        #print(f"Preview DataFrame loaded with columns: {cols} and number of rows: {len(rows)}")
        #self.preview_grid.load_data(rows=rows, columns=cols, editable=editable)
        # Load into dual grid
        #self.dual_grid = SyncedDualGrid(self.context, parent=self)
        self.dual_grid.load_data(
            top_columns=cols_for_both,
            top_rows=top_rows,
            bottom_columns=cols_for_both,
            bottom_rows=bottom_rows,
            bottom_editable=editable  # For preview; set True for actual import
        )

        self.dual_grid.set_header_number_in_chooser(header_row)

    # ------------------------------------------------------------------
    #  Table Extraction
    # ------------------------------------------------------------------

    def _extract_tables(self, tables: list[dict]) -> None:
        # ---- Group by jobfileid (this has alreadt been resolved to a 1:1 relationship to datafileid) (dict preserves first-seen order) ----
        by_file: dict[int, list[dict]] = defaultdict(list)
        for table in tables:
            by_file[table.get("jobfileid")].append(table)

        # ---- Phase 1: pre-flight + decisions (GUI thread, nothing is extracted yet) ----
        remembered_policy: ExistingTablePolicy | None = None  # set by an "ALL" button
        plan: dict[int, list[TableExtractRequest]] = {}

        for jobfileid, file_tables in by_file.items():
            requests: list[TableExtractRequest] = []

            for table in file_tables:

                policy = ExistingTablePolicy.NOT_SET
                pre = self.extract_service.check_table(table)

                if IssueType.TABLE_EXISTS in pre.issues:
                    if remembered_policy is not None:
                        policy = remembered_policy
                    else:
                        choice = self._ask_existing_table(table, offer_all=len(tables) > 1)
                        if choice is None:
                            return  # user cancelled: nothing has been extracted
                        policy, apply_all = choice
                        if apply_all:
                            remembered_policy = policy

                requests.append(
                    TableExtractRequest(
                        datafileobjectid=table.get("datafileobjectid"),
                        existing_policy=policy,
                        stagingtablename=table.get("stagingtablename"),
                        stagingtableschema=table.get("stagingtableschema"),
                    )
                )

            plan[jobfileid] = requests

        # ---- Phase 2: one process_file call per file ----
        summary: list[tuple[int, TableExtractRequest, ExtractResult]] = []
        for jobfileid, requests in plan.items():
            results = self.extract_service.process_file(jobfileid, requests)
            summary.extend(zip([jobfileid] * len(requests), requests, results))

        self._show_summary(summary)

    def _ask_existing_table(self, table: dict, offer_all: bool = True):
        """Returns (policy, apply_all) or None if cancelled."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Table already exists")
        box.setText(
            f"Staging table '{table.get('stagingtablename')}' already exists "
            f"(source object: {table.get('objectname')}).\n\nWhat should happen?"
        )

        R = QMessageBox.ButtonRole
        buttons = {
            box.addButton("Skip", R.ActionRole): (ExistingTablePolicy.SKIP, False),
            #box.addButton("Append", R.ActionRole): (ExistingTablePolicy.APPEND, False),
            box.addButton("Replace", R.ActionRole): (ExistingTablePolicy.REPLACE, False),
        }
        if offer_all:
            buttons.update({
                box.addButton("Skip All", R.ActionRole): (ExistingTablePolicy.SKIP, True),
                #box.addButton("Append All", R.ActionRole): (ExistingTablePolicy.APPEND, True),
                box.addButton("Replace All", R.ActionRole): (ExistingTablePolicy.REPLACE, True),
            })
        cancel = box.addButton("Cancel", R.RejectRole)
        box.setEscapeButton(cancel)

        box.exec()
        return buttons.get(box.clickedButton())  # None for Cancel or the window close button
    
    def _show_summary(self, summary: list[tuple[int, TableExtractRequest, ExtractResult]]):
        """Display a summary of extraction results to the user."""
        # Implement the summary display logic here, e.g., using a QMessageBox or a custom dialog.
        if not summary:
            QMessageBox.information(self, "Extraction Summary", "No extraction results to display.")
            return

        self.extract_summary = QDialog(self)

        message = ""
        for datafileid, request, result in summary:
            message += f"DataFile ID: {datafileid}\n"
            message += f"Request: {request}\n"
            message += f"Result: {result}\n"
            message += "-" * 40 + "\n"

        layout = QVBoxLayout()
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setText(message)#
        text_edit.setMaximumHeight(600)
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(text_edit)
        self.extract_summary.setLayout(layout)
        self.extract_summary.setWindowTitle("Extraction Summary")
        self.extract_summary.exec()

