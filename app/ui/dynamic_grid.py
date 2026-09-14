"""Dynamic grid widget for displaying table data."""

from typing import Dict, List, Optional, Any
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem,QAbstractItemView,QComboBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFocusEvent

class DynamicGrid(QTableWidget):
    # Add this signal at class level
    rowLostFocus = pyqtSignal(int)  # Emits row index when focus leaves
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.column_metadata: Dict[str, Dict] = {}
        self.row_data: List[Dict[str, Any]] = []
        self.original_row_data: List[Dict[str, Any]] = []  # Track original state
        self.dirty_rows: set = set()  # Track which rows have been modified
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setStretchLastSection(True)

        # Enable editing
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | 
            QAbstractItemView.EditTrigger.SelectedClicked |
            QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        
        # Connect cell change signal
        self.itemChanged.connect(self._on_cell_changed)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """Emit signal when grid loses focus."""
        current_row = self.currentRow()
        if current_row >= 0:
            print(f"DEBUG [Grid]: focusOutEvent - row {current_row} lost focus")
            self.rowLostFocus.emit(current_row)
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse clicks - save current row if clicking outside data area."""
        # Get the item at click position
        item = self.itemAt(event.pos())
        
        current_row = self.currentRow()
        
        # If clicking in empty space or different row, emit signal
        if item is None and current_row >= 0:
            print(f"DEBUG [Grid]: Click in empty space while on row {current_row}")
            self.rowLostFocus.emit(current_row)
        
        super().mousePressEvent(event)

    def load_data(self, columns: List[Dict], rows: List[Dict], editable: bool = True) -> None:
        """Load data into grid based on schema and rows.
        
        Args:
            columns: List of column metadata dicts with COLUMN_NAME, DATA_TYPE, etc.
            rows: List of data row dicts
            editable: Whether grid cells are editable
        """
        #print(f"DEBUG [Grid]: load_data() called with {len(rows)} rows")
        #print(f"DEBUG [Grid]: Columns: {[col['COLUMN_NAME'] for col in columns]}")  

        self.row_data = rows
        self.original_row_data = [row.copy() for row in rows]
        self.column_metadata = {col['COLUMN_NAME']: col for col in columns}

        #print(f"DEBUG [Grid]: Original row data stored: {self.original_row_data}")
        self.dirty_rows.clear()

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
    def _on_cell_changed(self, item) -> None:
        """Track when cells are modified."""
        if item is not None:
            row = item.row()
            self.dirty_rows.add(row)

    def get_dirty_rows(self) -> Dict[int, Dict[str, Any]]:
        """Return only rows that have been modified with their current values."""
        dirty = {}
        for row_idx in self.dirty_rows:
            dirty[row_idx] = self.get_row_data(row_idx)
        return dirty

    def get_row_data(self, row_idx: int) -> Dict[str, Any]:
        """Get current data for a specific row."""
        row_dict = {}
        for col_idx in range(self.columnCount()):
            col_name = self.horizontalHeaderItem(col_idx).text()

            # Check if cell is a dropdown
            widget = self.cellWidget(row_idx, col_idx)
            if isinstance(widget, QComboBox):
                row_dict[col_name] = widget.currentData()
            else:
                item = self.item(row_idx, col_idx)
                row_dict[col_name] = item.text() if item else None
        return row_dict

    def get_original_row_data(self, row_idx: int) -> Dict[str, Any]:
        """Get original data for a specific row (before edits)."""
        if row_idx < len(self.original_row_data):
            data = self.original_row_data[row_idx].copy()
            #print(f"DEBUG [Grid]: get_original_row_data({row_idx}) returning: {data}")
            return data
        #print(f"DEBUG [Grid]: get_original_row_data({row_idx}) - row index out of bounds")
        return {}

    def is_row_dirty(self, row_idx: int) -> bool:
        """Check if a specific row has been modified."""
        return row_idx in self.dirty_rows

    def clear_dirty_flag(self, row_idx: int) -> None:
        """Clear dirty flag after successful save."""
        self.dirty_rows.discard(row_idx)

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
    
    def has_row_actually_changed(self, row_idx: int) -> bool:
        """Check if row data has actually changed from original."""
        return len(self.get_changed_columns(row_idx)) > 0

    def get_changed_columns(self, row_idx: int) -> Dict[str, Any]:
        """Return only the columns that have actually changed.
        Returns dict of {column_name: new_value} or empty dict if no changes."""
        if row_idx >= len(self.original_row_data):
            return {}
        
        original = self.original_row_data[row_idx]
        current = self.get_row_data(row_idx)
        
        # Compare each column value
        changed = {}
        for col_name in original.keys():
            if str(original.get(col_name, "")) != str(current.get(col_name, "")):
                changed[col_name] = current.get(col_name)
                #print(f"DEBUG [Grid]: Column '{col_name}' changed: '{original.get(col_name)}' -> '{current.get(col_name)}'")
        
        return changed


    def set_column_dropdown(self, col_idx: int, dropdown_values: List[Dict]) -> None:
        """Set a column to use a dropdown for all rows."""
        print(f"DEBUG [Grid]: Setting column {col_idx} as dropdown with {len(dropdown_values)} values")
        
        for row_idx in range(self.rowCount()):
            combo = QComboBox()
            
            # Add blank option
            combo.addItem("", None)
            
            # Add dropdown options
            for item in dropdown_values:
                key = item.get('refkey')
                desc = item.get('refdesc', key)
                display_text = f"{key} ({desc})"  # Show both
                combo.addItem(display_text, key)  # Store only key
            
            # Set current value if row has data
            current_cell = self.item(row_idx, col_idx)
            if current_cell:
                current_value = current_cell.text()
                index = combo.findData(current_value)
                if index >= 0:
                    combo.setCurrentIndex(index)
            
            # Track changes
            combo.currentIndexChanged.connect(
                lambda checked, r=row_idx, c=col_idx: self._on_dropdown_changed(r, c, combo)
            )
            
            self.setCellWidget(row_idx, col_idx, combo)

    def _on_dropdown_changed(self, row_idx: int, col_idx: int, combo: QComboBox) -> None:
        """Handle dropdown selection change."""
        self.dirty_rows.add(row_idx)
        print(f"DEBUG [Grid]: Dropdown changed at row {row_idx}, col {col_idx}: {combo.currentData()}")