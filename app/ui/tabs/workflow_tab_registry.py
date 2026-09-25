from dataclasses import dataclass
from typing import Callable

from config.config import Config
from PyQt6.QtWidgets import QWidget


from app.models.migration_context import MigrationContext
from app.models.system_model import WorkflowPhase

from app.services.db_service import DatabaseService

# Import real tab classes as you create them.
# from tabs.import_tab import ImportTab

from app.ui.tabs.extract_tab import ExtractTab
from app.ui.tabs.import_tab import ImportTab

    


@dataclass(frozen=True)
class WorkflowTabDefinition:
    """Metadata and factory for a workflow tab."""

    phase: WorkflowPhase | None
    label: str
    factory: Callable[[MigrationContext,Config,DatabaseService], QWidget]
    enabled: bool = True


class PlaceholderWorkflowTab(QWidget):
    """Temporary panel until a real implementation is added."""

    def __init__(
        self,
        context: MigrationContext,
        config: Config,
        db_service: DatabaseService,
        title: str,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)

        self.title = title
        self.context = context
        self.config = config
        self.db_service = db_service
        # This tab can later subscribe to:
        # self.context.task_changed.connect(self._on_task_changed)
        # self.context.table_changed.connect(self._on_table_changed)


def create_placeholder_tab(
    title: str,
) -> Callable[[MigrationContext], QWidget]:
    """Create a factory compatible with WorkflowTabDefinition."""

    def factory(context: MigrationContext, config: Config, db_service: DatabaseService) -> QWidget:
        return PlaceholderWorkflowTab(context, config, db_service, title)

    return factory


WORKFLOW_TABS: list[WorkflowTabDefinition] = [
    WorkflowTabDefinition(
        phase=WorkflowPhase.IMPORT,
        label="Import",
        #factory=lambda context, config, db_service: ImportTab(context=context, config=config, db_service=db_service),
        factory = ImportTab
    ),
    WorkflowTabDefinition(
        phase=WorkflowPhase.EXTRACT,
        label="Extract",
        factory=lambda context, config, db_service: ExtractTab(context=context, config=config, db_service=  db_service),
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