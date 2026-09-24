from dataclasses import dataclass
from typing import Callable

from PyQt6.QtWidgets import QWidget

from app.models.migration_context import MigrationContext
from app.models.system_model import WorkflowPhase

# Import real tab classes as you create them.
# from tabs.import_tab import ImportTab
from app.ui.tabs.extract_tab import ExtractTab

    


@dataclass(frozen=True)
class WorkflowTabDefinition:
    """Metadata and factory for a workflow tab."""

    phase: WorkflowPhase | None
    label: str
    factory: Callable[[MigrationContext], QWidget]
    enabled: bool = True


class PlaceholderWorkflowTab(QWidget):
    """Temporary panel until a real implementation is added."""

    def __init__(
        self,
        context: MigrationContext,
        title: str,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.title = title

        # This tab can later subscribe to:
        # self.context.task_changed.connect(self._on_task_changed)
        # self.context.table_changed.connect(self._on_table_changed)


def create_placeholder_tab(
    title: str,
) -> Callable[[MigrationContext], QWidget]:
    """Create a factory compatible with WorkflowTabDefinition."""

    def factory(context: MigrationContext) -> QWidget:
        return PlaceholderWorkflowTab(context, title)

    return factory


WORKFLOW_TABS: list[WorkflowTabDefinition] = [
    WorkflowTabDefinition(
        phase=WorkflowPhase.IMPORT,
        label="Import",
        factory=create_placeholder_tab("Import"),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.EXTRACT,
        label="Extract",
        factory=lambda context: ExtractTab(context),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.VIEW_SOURCE,
        label="View Source",
        factory=create_placeholder_tab("View Source"),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.GENERATE_MAPPINGS,
        label="Generate Mappings",
        factory=create_placeholder_tab("Generate Mappings"),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.APPROVE_MAPPINGS,
        label="Approve Mappings",
        factory=create_placeholder_tab("Approve Mappings"),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.VIEW_TRANSFORMED,
        label="View Transformed",
        factory=create_placeholder_tab("View Transformed"),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.EXTRACT_DISTINCT,
        label="Extract Distinct",
        factory=create_placeholder_tab("Extract Distinct"),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.VALUE_MAPPINGS,
        label="Value Mappings",
        factory=create_placeholder_tab("Value Mappings"),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.VALIDATIONS,
        label="Validations",
        factory=create_placeholder_tab("Validations"),
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.UPDATE_DATA,
        label="Update Data",
        factory=create_placeholder_tab("Update Data"),
    ),
]