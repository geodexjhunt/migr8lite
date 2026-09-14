"""Dynamic grid widget for displaying table data."""

from typing import Dict, List, Optional, Any
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt

class DynamicGrid(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.column_metadata: Dict[str, Dict] = {}
        self.row_data: List[Dict[str, Any]] = []
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setStretchLastSection(True)
    
    def load_data(self, columns: List[Dict], rows: List[Dict], editable: bool = True) -> None:
        """Load data into grid based on schema and rows.
        
        Args:
            columns: List of column metadata dicts with COLUMN_NAME, DATA_TYPE, etc.
            rows: List of data row dicts
            editable: Whether grid cells are editable
        """
        self.row_data = rows
        self.column_metadata = {col['COLUMN_NAME']: col for col in columns}
        
        column_names = [col['COLUMN_NAME'] for col in columns]
        self.setColumnCount(len(column_names))
        self.setHorizontalHeaderLabels(column_names)
        self.setRowCount(len(rows))
        
        for row_idx, row_data in enumerate(rows):
            for col_idx, col_name in enumerate(column_names):
                value = row_data.get(col_name, "")
                item = QTableWidgetItem(str(value) if value else "")
                if not editable or col_name.lower() in ["id", "created_at", "updated_at"]:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row_idx, col_idx, item)
        
        self.resizeColumnsToContents()
    
    def get_all_rows(self) -> List[Dict[str, Any]]:
        """Get all rows as list of dictionaries."""
        rows = []
        for row_idx in range(self.rowCount()):
            row_dict = {}
            for col_idx in range(self.columnCount()):
                col_name = self.horizontalHeaderItem(col_idx).text()
                item = self.item(row_idx, col_idx)
                row_dict[col_name] = item.text() if item else None
            rows.append(row_dict)
        return rows
