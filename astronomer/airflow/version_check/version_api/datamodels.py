from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class WarningType(str, Enum):
    """Type of version warning."""

    EOM = "eom"  # End of Maintenance
    EOBS = "eobs"  # End of Basic Support
    YANKED = "yanked"


class WarningLevel(str, Enum):
    """Severity level of the warning."""

    WARNING = "warning"
    CRITICAL = "critical"


class VersionWarning(BaseModel):
    """Details about a version warning."""

    type: WarningType
    level: WarningLevel
    message: str
    days_remaining: int | None = None
    dismissed_until: datetime | None = None
    can_dismiss: bool = True


class VersionStatus(BaseModel):
    """Current version status information."""

    current_version: str | None
    warning: VersionWarning | None = None


class StatusResponse(BaseModel):
    """Response from the status endpoint."""

    status: VersionStatus


class DismissRequest(BaseModel):
    """Request to dismiss a warning."""

    pass  # No additional fields needed, the type is in the URL


class DismissResponse(BaseModel):
    """Response after dismissing a warning."""

    success: bool
    dismissed_until: datetime | None = None
    message: str

