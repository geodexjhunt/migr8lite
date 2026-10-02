"""Container widget with two synchronized DynamicGrid instances."""

from turtle import color
from typing import Dict, List, Any
from PyQt6.QtWidgets import QFrame, QHeaderView, QSizePolicy, QWidget, QVBoxLayout, QSplitter, QPushButton, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QPixmap
from app.ui.tabs.dynamic_grid import DynamicGrid
from app.models.migration_context import MigrationContext


class SyncedDualGrid(QWidget):
    """Two vertically stacked grids with synchronized column widths and horizontal scroll."""
    
    def __init__(self, context: MigrationContext, parent=None):
        super().__init__(parent)
        self.context = context
        self._syncing = False  # Guard against infinite resize loops

        self.origheadercolor: QColor = QColor(200, 200, 255)  # Light blue, matches your header row color
        self.preheadercolor: QColor = QColor(255, 255, 200)
        # QColor(200, 200, 255) — light blue
        # QColor(255, 255, 200) — light yellow
        # QColor(200, 255, 200) — light green
        # QColor(255, 220, 220) — light red

        # Create grids
        self.top_grid = DynamicGrid(context, parent=self)
        self.bottom_grid = DynamicGrid(context, parent=self)

        # Disable stretch-last-section to prevent resize feedback loops between synced grids
        self.top_grid.horizontalHeader().setStretchLastSection(False)
        self.bottom_grid.horizontalHeader().setStretchLastSection(False)

        # Hide header on top grid
        self.top_grid.horizontalHeader().hide()  # Hide duplicate header
        # Top grid is read-only (pre-header data + original header row)
        self.top_grid.setEditTriggers(self.top_grid.EditTrigger.NoEditTriggers)
        
        # Bottom grid: editable or read-only depending on use case
        # (For preview, set to NoEditTriggers; for actual import data, allow edits)
        
        # Create toggle button for top panel
        self.toggle_top_btn = QPushButton("▼ Hide Pre-Header Rows")
        self.toggle_top_btn.setMaximumWidth(200)
        self.toggle_top_btn.clicked.connect(self._toggle_top_panel)
        self.top_panel_visible = True
        
        # Create legend
        self.legend1 = self._create_legend(self.origheadercolor,'Orig Header Row')
        self.legend2 = self._create_legend(self.preheadercolor,'Pre Header Rows')

        # Splitter to allow resizing between grids
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.top_grid)
        self.splitter.addWidget(self.bottom_grid)
        
        # Set initial sizes: top 100px, bottom gets rest
        self.splitter.setSizes([100, 400])
        
        # Layout
        layout = QVBoxLayout()
        headerlayout = QHBoxLayout()
        headerlayout.addWidget(self.toggle_top_btn)
        headerlayout.addWidget(self.legend1)
        headerlayout.addWidget(self.legend2)
        headerlayout.addStretch()
        layout.addLayout(headerlayout)
        layout.addWidget(self.splitter)
        self.setLayout(layout)
        
        # Sync column widths and horizontal scroll
        self._setup_sync()
    
    def _setup_sync(self) -> None:
        """Connect resize and scroll events between top and bottom grids."""
        top_header = self.top_grid.horizontalHeader()
        bottom_header = self.bottom_grid.horizontalHeader()

        # Make top grid header non-resizable (read-only, no user resize feedback loop)
        top_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        
        # Sync column width changes (both directions)
        #top_header.sectionResized.connect(
        #    lambda logical_idx, old_size, new_size: self._sync_column_width(
        #        logical_idx, new_size, bottom_header
        #    )
        #)
        
        bottom_header.sectionResized.connect(
            lambda logical_idx, old_size, new_size: self._sync_column_width(
                logical_idx, new_size, top_header
            )
        )
        
        # Sync horizontal scrollbars
        top_scroll = self.top_grid.horizontalScrollBar()
        bottom_scroll = self.bottom_grid.horizontalScrollBar()
        
        top_scroll.valueChanged.connect(bottom_scroll.setValue)
        bottom_scroll.valueChanged.connect(top_scroll.setValue)
    
    def _sync_column_width(self, logical_idx: int, new_size: int, target_header) -> None:
        """Sync a column width to target header, guarding against infinite loops and invalid indices."""
        if self._syncing:
            return
        
        # Guard: target header might not have this column yet (e.g. during initial load)
        if logical_idx >= target_header.count():
            return
        
        self._syncing = True
        if target_header.sectionSize(logical_idx) != new_size:
            target_header.resizeSection(logical_idx, new_size)
        self._syncing = False
    
    def _toggle_top_panel(self) -> None:
        """Toggle visibility of top grid panel."""
        self.top_panel_visible = not self.top_panel_visible
        
        if self.top_panel_visible:
            self.splitter.setSizes([100, 400])
            self.toggle_top_btn.setText("▼ Hide Pre-Header Rows")
        else:
            self.splitter.setSizes([0, 500])
            self.toggle_top_btn.setText("► Show Pre-Header Rows")
    
    def load_data(
        self,
        top_columns: List[Dict],
        top_rows: List[Dict],
        bottom_columns: List[Dict],
        bottom_rows: List[Dict],
        bottom_editable: bool = False,
    ) -> None:
        """Load data into both grids.
        
        Args:
            top_columns: Column metadata for pre-header grid
            top_rows: Pre-header + original header row data
            bottom_columns: Column metadata for data grid
            bottom_rows: Actual data rows (from data_df)
            bottom_editable: Whether bottom grid is editable
        """
        print("Loading data into synced dual grid")
        #print(f"Top columns: {top_columns}")
        #print(f"Bottom columns: {bottom_columns}")

        # Temporarily block resize signals to avoid cross-grid triggering during initial load
        self.top_grid.horizontalHeader().blockSignals(True)
        self.bottom_grid.horizontalHeader().blockSignals(True)
        
        self.top_grid.load_data(top_columns, top_rows, editable=False)
        self.bottom_grid.load_data(bottom_columns, bottom_rows, editable=bottom_editable)

        # Align column widths to the larger of each pair, now that both grids have content
        self._align_initial_column_widths()

        # Size top grid to fit up to 5 rows, no more
        self._set_initial_top_grid_height(max_visible_rows=5)


        # Unblock signals after initial alignment
        self.top_grid.horizontalHeader().blockSignals(False)
        self.bottom_grid.horizontalHeader().blockSignals(False)

        # Highlight all pre-header rows in top grid
        self.highlight_all_rows(
            self.top_grid,
            self.preheadercolor)  # Light yellow, adjust to preference

        # Highlight the last row in top grid as the original header
        self.highlight_last_row_as_header(
            self.top_grid, 
            self.origheadercolor)  # Light blue, adjust to preference


    
    def get_bottom_grid(self) -> DynamicGrid:
        """Return the bottom (data) grid for direct access if needed."""
        return self.bottom_grid
    
    def get_top_grid(self) -> DynamicGrid:
        """Return the top (pre-header) grid for direct access if needed."""
        return self.top_grid

    def clear_contents(self) -> None:
        """Clear contents of both top and bottom grids."""
        self.top_grid.clear_contents()
        self.bottom_grid.clear_contents()

    def highlight_last_row_as_header(self, grid: DynamicGrid, color: QColor) -> None:
        """Highlight the last row in a grid with a background color."""
        last_row = grid.rowCount() - 1
        if last_row < 0:
            return
        
        for col_idx in range(grid.columnCount()):
            item = grid.item(last_row, col_idx)
            if item:
                item.setBackground(QBrush(color))

    def highlight_all_rows(self, grid: DynamicGrid, color: QColor) -> None:
        """Highlight all rows in a grid with a background color."""
        row_count = grid.rowCount()
        if row_count == 0:
            return

        for row_idx in range(row_count):
            for col_idx in range(grid.columnCount()):
                item = grid.item(row_idx, col_idx)
                if item:
                    item.setBackground(QBrush(color))

    def _align_initial_column_widths(self) -> None:
        """After both grids are loaded, align column widths by taking the max of each pair.
        This gives a level playing field before live resize-sync takes over."""
        top_header = self.top_grid.horizontalHeader()
        bottom_header = self.bottom_grid.horizontalHeader()
        
        col_count = min(top_header.count(), bottom_header.count())
        
        for col_idx in range(col_count):
            top_width = top_header.sectionSize(col_idx)
            bottom_width = bottom_header.sectionSize(col_idx)
            
            if top_width != bottom_width:
                max_width = max(top_width, bottom_width)
                top_header.resizeSection(col_idx, max_width)
                bottom_header.resizeSection(col_idx, max_width)

    def _set_initial_top_grid_height(self, max_visible_rows: int = 5) -> None:
        """Size the top grid to show up to max_visible_rows rows, no more, no less than needed."""
        row_count = self.top_grid.rowCount()
        visible_rows = min(row_count, max_visible_rows)
        
        if visible_rows == 0:
            total_height = 0
        else:
            row_height = self.top_grid.rowHeight(0) if row_count > 0 else 24  # fallback
            
            # Account for frame border (top grid header is hidden, so no header height needed)
            frame_width = self.top_grid.frameWidth() * 2
            
            # Horizontal scrollbar height, in case columns overflow
            scrollbar_height = self.top_grid.horizontalScrollBar().sizeHint().height()
            
            total_height = (row_height * visible_rows) + frame_width + scrollbar_height
        
        # Apply to splitter: top gets calculated height, bottom gets remaining space
        total_splitter_height = self.splitter.height() or 500  # fallback if not yet rendered
        bottom_height = max(total_splitter_height - total_height, 100)
        
        self.splitter.setSizes([total_height, bottom_height])

    def _create_legend(self,origheadercolor: QColor, text: str ) -> QWidget:
        """Create a legend widget showing the original header row color."""
        legend_widget = QWidget()
        legend_layout = QHBoxLayout()
        legend_layout.setContentsMargins(0, 0, 0, 0)  # Remove extra padding
        
        # Create a colored swatch (small pixmap)
        #swatch_size = 20
        #swatch = QPixmap(swatch_size, swatch_size)
        #swatch.fill(origheadercolor)  # Light blue, matches your header row color
        #swatch.rect()

        swatch = self._create_color_swatch(origheadercolor)

        # Swatch label (just displays the pixmap)
        #swatch_label = QLabel()
        #swatch_label.setPixmap(swatch)
        
        # Text label
        text_label = QLabel(text)
        
        #legend_layout.addWidget(swatch_label)
        legend_layout.addWidget(swatch)
        legend_layout.addWidget(text_label)
        legend_layout.addStretch()  # Push to the left
        
        legend_widget.setLayout(legend_layout)
        legend_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return legend_widget

    def _create_color_swatch(self, color: QColor, size: int = 20) -> QFrame:
        """Create a bordered color swatch frame."""
        swatch_frame = QFrame()
        swatch_frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgb({color.red()}, {color.green()}, {color.blue()});
                border: 1px solid #000;
                border-radius: 2px;
            }}
        """)
        swatch_frame.setFixedSize(size, size)
        return swatch_frame