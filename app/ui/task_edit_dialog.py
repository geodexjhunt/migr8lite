
from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox
from typing import Optional
class TaskEditDialog(QDialog):
    """Dialog for creating/editing a migration task, with validation before save."""
    
    def __init__(self, parent=None, task_id: Optional[int] = None):
        super().__init__(parent)
        self.task_id = task_id
        self.saved_task_id = None
        self.setWindowTitle("New Migration Task" if task_id is None else "Edit Migration Task")
        
        layout = QFormLayout()
        
        self.name_edit = QLineEdit()
        layout.addRow("Task Name:", self.name_edit)
        
        self.description_edit = QLineEdit()
        layout.addRow("Description:", self.description_edit)

        self.schema_edit = QLineEdit()
        layout.addRow("Schema Name:", self.schema_edit)

        self.jobprefix_edit = QLineEdit()
        layout.addRow("Job Prefix:", self.jobprefix_edit)

        self.status_edit = QLineEdit()
        layout.addRow("Status:", self.status_edit)

        self.purpose_edit = QLineEdit()
        layout.addRow("Purpose:", self.purpose_edit)
        
        # Load existing data if editing
        if task_id is not None:
            self._load_task_data(task_id)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
        
        self.setLayout(layout)
    
    def _on_save(self) -> None:
        """Validate before accepting."""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Task name is required")
            return
        
        try:
            self.saved_task_id = self.parent().db_service.save_migration_task(
                task_id=self.task_id,
                name=self.name_edit.text().strip(),
                description=self.description_edit.text().strip(),
                schemaname=self.schema_edit.text().strip(),
                jobprefix=self.jobprefix_edit.text().strip(),
                status=self.status_edit.text().strip(),
                purpose=self.purpose_edit.text().strip()
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save task: {e}")

    def _load_task_data(self, task_id: int) -> None:
        """Load existing task data into the dialog fields."""
        try:
            # Fetch task data from db_service
            task_data = self.parent().db_service.get_migration_tasks()
            task = next((t for t in task_data if t['jobid'] == task_id), None)
            if task:
                self.name_edit.setText(task.get('jobname', ''))
                self.description_edit.setText(task.get('description', ''))
                self.schema_edit.setText(task.get('schemaname', ''))
                self.jobprefix_edit.setText(task.get('jobprefix', ''))
                self.status_edit.setText(task.get('status', ''))
                self.purpose_edit.setText(task.get('purpose', ''))
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load task data: {e}")