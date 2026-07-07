import time
from enum import Enum

from pydantic import BaseModel, Field


class SpecStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class AtSpecResult(BaseModel):
    id: str = ""
    name: str = ""
    status: SpecStatus = SpecStatus.PASSED
    error: str = ""
    duration: float = 0.0
    skip_reason: str = ""


class AtSuiteResult(BaseModel):
    suite_name: str = ""
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    timeout: int = 0
    total: int = 0
    specs: list[AtSpecResult] = Field(default_factory=list)
    duration: float = 0.0
    error: str = ""
