"""Adaptive card creation for approval workflows.

This module provides functions for creating Microsoft Teams Adaptive Cards
for various approval workflows, including SSM command approvals.
"""

from ohlala_smartops.cards.approval_cards import (
    create_approved_confirmation_card,
    create_batch_approval_card,
    create_batch_approval_card_sync,
    create_denied_confirmation_card,
    create_ssm_approval_card,
    create_ssm_approval_card_sync,
)

__all__ = [
    "create_approved_confirmation_card",
    "create_batch_approval_card",
    "create_batch_approval_card_sync",
    "create_denied_confirmation_card",
    "create_ssm_approval_card",
    "create_ssm_approval_card_sync",
]
