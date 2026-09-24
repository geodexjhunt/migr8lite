from multiprocessing import context

from PyQt6.QtWidgets import QWidget
from app.models.migration_context import MigrationContext

class ExtractTab(QWidget):
    def __init__(self, context: MigrationContext, parent=None):
        super().__init__(parent)
        self.context = context

        self.context.task_changed.connect(self._on_task_changed)
        self.context.table_changed.connect(self._on_table_changed)

    def _on_task_changed(self, task_id) -> None:
        """Clear or refresh task-scoped content."""

    def _on_table_changed(self, table_info) -> None:
        """Load import details for the newly selected task table."""