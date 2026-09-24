
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

class MigrationContext(QObject):
    task_changed = pyqtSignal(object)
    table_changed = pyqtSignal(object)
    database_metadata_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_task_id = None
        self.current_table = None
        # Shared database metadata cache
        self.user_defined_schemas: list[dict[str, Any]] = []
        self.all_tables_info: list[dict[str, Any]] = []

    def set_task(self, task_id):
        self.current_task_id = task_id
        self.current_table = None
        self.task_changed.emit(task_id)

    def set_table(self, table_info):
        self.current_table = table_info
        self.table_changed.emit(table_info)

    def set_database_metadata(
        self,
        user_defined_schemas: list[dict[str, Any]],
        all_tables_info: list[dict[str, Any]],
    ) -> None:
        self.user_defined_schemas = user_defined_schemas
        self.all_tables_info = all_tables_info
        self.database_metadata_changed.emit()