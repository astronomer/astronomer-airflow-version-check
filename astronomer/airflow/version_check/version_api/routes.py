from __future__ import annotations

from datetime import timedelta

from airflow.api_fastapi.common.db.common import SessionDep
from airflow.api_fastapi.common.router import AirflowRouter
from airflow.utils.timezone import utcnow

from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion
from astronomer.airflow.version_check.update_checks import UpdateAvailableHelper, get_runtime_version
from astronomer.airflow.version_check.version_api.datamodels import (
    DismissResponse,
    StatusResponse,
    VersionStatus,
    VersionWarning,
    WarningLevel,
    WarningType,
)

ui_router = AirflowRouter(tags=["UI"])


def _convert_warning_dict_to_model(warning_dict: dict | None) -> VersionWarning | None:
    """Convert warning dict from UpdateAvailableHelper to VersionWarning Pydantic model."""
    if not warning_dict:
        return None

    return VersionWarning(
        type=WarningType(warning_dict["type"]),
        level=WarningLevel(warning_dict["level"]),
        message=warning_dict.get("message", warning_dict.get("description", "")),
        days_remaining=warning_dict.get("days_remaining"),
        dismissed_until=warning_dict.get("dismissed_until"),
        can_dismiss=warning_dict.get("can_dismiss", True),
    )


@ui_router.get("/status")
def get_status(session: SessionDep) -> StatusResponse:
    """Get the current version status and any active warnings."""
    from astronomer.airflow.version_check.plugin import (
        eobs_warning_opt_out,
        eom_warning_opt_out,
    )

    runtime_version = get_runtime_version()

    current_version = None
    if runtime_version:
        current_version = (
            session.query(AstronomerAvailableVersion)
            .filter(AstronomerAvailableVersion.version == str(runtime_version))
            .one_or_none()
        )

    helper = UpdateAvailableHelper()
    warning_dict = helper.get_priority_warning(
        current_version=current_version,
        eom_opt_out=eom_warning_opt_out,
        eobs_opt_out=eobs_warning_opt_out,
    )
    warning = _convert_warning_dict_to_model(warning_dict)

    return StatusResponse(
        status=VersionStatus(
            current_version=runtime_version,
            warning=warning,
        )
    )


@ui_router.post("/dismiss/eom")
def dismiss_eom_warning(session: SessionDep) -> DismissResponse:
    """Dismiss the End of Maintenance (EOM) warning for the configured period."""
    from astronomer.airflow.version_check.plugin import eom_dismissal_period_days

    runtime_version = get_runtime_version()
    if not runtime_version:
        return DismissResponse(
            success=False,
            message="No runtime version found.",
        )

    current_version = (
        session.query(AstronomerAvailableVersion)
        .filter(AstronomerAvailableVersion.version == str(runtime_version))
        .one_or_none()
    )

    if not current_version:
        return DismissResponse(
            success=False,
            message=f"Version {runtime_version} not found in database.",
        )

    dismissed_until = utcnow() + timedelta(days=eom_dismissal_period_days)
    current_version.eom_dismissed_until = dismissed_until
    session.commit()

    return DismissResponse(
        success=True,
        dismissed_until=dismissed_until,
        message=f"EOM warning dismissed until {dismissed_until.strftime('%Y-%m-%d')}.",
    )


@ui_router.post("/dismiss/eobs")
def dismiss_eobs_warning(session: SessionDep) -> DismissResponse:
    """Dismiss the End of Basic Support (EOBS) warning for the configured period."""
    from astronomer.airflow.version_check.plugin import eobs_dismissal_period_days

    runtime_version = get_runtime_version()
    if not runtime_version:
        return DismissResponse(
            success=False,
            message="No runtime version found.",
        )

    current_version = (
        session.query(AstronomerAvailableVersion)
        .filter(AstronomerAvailableVersion.version == str(runtime_version))
        .one_or_none()
    )

    if not current_version:
        return DismissResponse(
            success=False,
            message=f"Version {runtime_version} not found in database.",
        )

    dismissed_until = utcnow() + timedelta(days=eobs_dismissal_period_days)
    current_version.eobs_dismissed_until = dismissed_until
    session.commit()

    return DismissResponse(
        success=True,
        dismissed_until=dismissed_until,
        message=f"EOBS warning dismissed until {dismissed_until.strftime('%Y-%m-%d')}.",
    )
