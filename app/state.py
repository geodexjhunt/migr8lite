"""Migration job state management."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime

class JobStatus(str, Enum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class MigrationJob:
    job_id: str
    name: str
    description: Optional[str] = None
    status: JobStatus = JobStatus.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    source_table: Optional[str] = None
    target_table: Optional[str] = None
    current_phase: str = "a_define"
    metadata: Dict = field(default_factory=dict)

class JobStateManager:
    def __init__(self):
        self._current_job: Optional[MigrationJob] = None
        self._jobs: Dict[str, MigrationJob] = {}
    
    def create_job(self, job_id: str, name: str, description: Optional[str] = None) -> MigrationJob:
        job = MigrationJob(job_id=job_id, name=name, description=description)
        self._jobs[job_id] = job
        self._current_job = job
        return job
    
    def get_current_job(self) -> Optional[MigrationJob]:
        return self._current_job
