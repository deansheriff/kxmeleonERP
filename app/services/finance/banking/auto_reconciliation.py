"""Auto-reconciliation service facade.

The method implementations live in ``auto_reconciliation_parts``. This module
keeps the historical import path stable for callers and tests.
"""

from __future__ import annotations

from app.services.finance.banking.auto_reconciliation_parts import (
    AutoReconciliationCoreService,
    AutoReconciliationHelperService,
    AutoReconciliationPaymentService,
    AutoReconciliationSpecialService,
)
from app.services.finance.banking.auto_reconciliation_parts.base import (
    AMOUNT_TOLERANCE,
    SYSTEM_USER_ID,
    AutoMatchDefaults,
    AutoMatchResult,
    logger,
)


class AutoReconciliationService(  # type: ignore[misc]
    AutoReconciliationCoreService,
    AutoReconciliationPaymentService,
    AutoReconciliationSpecialService,
    AutoReconciliationHelperService,
):
    """Unified auto-reconciliation service facade."""

    logger = logger
    SYSTEM_USER_ID = SYSTEM_USER_ID


__all__ = [
    "AMOUNT_TOLERANCE",
    "AutoMatchDefaults",
    "AutoMatchResult",
    "AutoReconciliationService",
    "SYSTEM_USER_ID",
]
