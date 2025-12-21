from __future__ import annotations

from datetime import timedelta

from airflow.api_fastapi.common.db.common import SessionDep
from airflow.api_fastapi.common.router import AirflowRouter
from airflow.utils.timezone import utcnow

from astronomer.airflow.version_check.models.db import AstronomerAvailableVersion
from astronomer.airflow.version_check.update_checks import get_runtime_version
from astronomer.airflow.version_check.version_api.datamodels import (
    DismissResponse,
    StatusResponse,
    VersionStatus,
    VersionWarning,
    WarningLevel,
    WarningType,
)

ui_router = AirflowRouter(tags=["UI"])


def _get_priority_warning(
    current_version: AstronomerAvailableVersion | None,
    eom_threshold_days: int,
    eobs_threshold_days: int,
    eom_opt_out: bool,
    eobs_opt_out: bool,
) -> VersionWarning | None:
    """
    Get the highest priority warning for the current version.

    Priority order (highest to lowest):
    1. Yanked version (critical)
    2. End of Basic Support (EOBS) warning
    3. End of Maintenance (EOM) warning
    """
    if not current_version:
        return None

    now = utcnow()

    # Check for yanked version first (highest priority)
    if current_version.yanked:
        return VersionWarning(
            type=WarningType.YANKED,
            level=WarningLevel.CRITICAL,
            message=(
                f"Warning: Astronomer Runtime version {current_version.version} has been yanked. "
                "We strongly recommend upgrading to a more recent supported version."
            ),
            days_remaining=None,
            can_dismiss=False,  # Yanked warnings cannot be dismissed
        )

    # Check for EOBS warning (second priority)
    if not eobs_opt_out and current_version.end_of_basic_support:
        days_to_eobs = (current_version.end_of_basic_support - now).days
        if days_to_eobs <= eobs_threshold_days:
            # Check if dismissed
            if current_version.eobs_dismissed_until and now < current_version.eobs_dismissed_until:
                pass  # Dismissed, skip to EOM check
            else:
                level = WarningLevel.CRITICAL if days_to_eobs <= 0 else WarningLevel.WARNING
                if days_to_eobs <= 0:
                    message = (
                        f"Astronomer Runtime version {current_version.version} has reached its end of basic support."
                    )
                else:
                    message = (
                        f"Astronomer Runtime version {current_version.version} "
                        f"will reach its end of basic support in {days_to_eobs} days."
                    )
                return VersionWarning(
                    type=WarningType.EOBS,
                    level=level,
                    message=message,
                    days_remaining=days_to_eobs,
                    dismissed_until=current_version.eobs_dismissed_until,
                    can_dismiss=True,
                )

    # Check for EOM warning (third priority)
    if not eom_opt_out and current_version.end_of_maintenance:
        days_to_eom = (current_version.end_of_maintenance - now).days
        if days_to_eom <= eom_threshold_days:
            # Check if dismissed
            if current_version.eom_dismissed_until and now < current_version.eom_dismissed_until:
                return None  # Dismissed
            level = WarningLevel.CRITICAL if days_to_eom <= 0 else WarningLevel.WARNING
            if days_to_eom <= 0:
                message = f"Astronomer Runtime version {current_version.version} has reached its end of maintenance."
            else:
                message = (
                    f"Astronomer Runtime version {current_version.version} "
                    f"will reach its end of maintenance in {days_to_eom} days."
                )
            return VersionWarning(
                type=WarningType.EOM,
                level=level,
                message=message,
                days_remaining=days_to_eom,
                dismissed_until=current_version.eom_dismissed_until,
                can_dismiss=True,
            )

    return None


@ui_router.get("/status")
def get_status(session: SessionDep) -> StatusResponse:
    """Get the current version status and any active warnings."""
    from astronomer.airflow.version_check.plugin import (
        eobs_warning_opt_out,
        eobs_warning_threshold_days,
        eom_warning_opt_out,
        eom_warning_threshold_days,
    )

    runtime_version = get_runtime_version()

    current_version = None
    if runtime_version:
        current_version = (
            session.query(AstronomerAvailableVersion)
            .filter(AstronomerAvailableVersion.version == str(runtime_version))
            .one_or_none()
        )

    warning = _get_priority_warning(
        current_version=current_version,
        eom_threshold_days=eom_warning_threshold_days,
        eobs_threshold_days=eobs_warning_threshold_days,
        eom_opt_out=eom_warning_opt_out,
        eobs_opt_out=eobs_warning_opt_out,
    )

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
