"""Slash command handlers for Ohlala SmartOps.

This package contains all slash command implementations. Commands provide
specific functionality like help, status checks, and EC2 operations.

Phase 5A: Initial commands (base, help, status).
Phase 5B: Instance management commands (list, start, stop, reboot).
Phase 5C: Monitoring & information commands (details, metrics, costs).
Phase 5D: SSM command execution (exec, commands).
Phase 5E: Resource tagging (tag, untag, find-tags).
Future phases will add advanced operations.
"""

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.commands.commands_list import CommandsListCommand
from ohlala_smartops.commands.costs import CostsCommand
from ohlala_smartops.commands.exec import ExecCommand
from ohlala_smartops.commands.find_by_tags import FindByTagsCommand
from ohlala_smartops.commands.help import HelpCommand
from ohlala_smartops.commands.instance_details import InstanceDetailsCommand
from ohlala_smartops.commands.list_instances import ListInstancesCommand
from ohlala_smartops.commands.metrics import MetricsCommand
from ohlala_smartops.commands.reboot import RebootInstanceCommand
from ohlala_smartops.commands.start import StartInstanceCommand
from ohlala_smartops.commands.status import StatusCommand
from ohlala_smartops.commands.stop import StopInstanceCommand
from ohlala_smartops.commands.tag import TagCommand
from ohlala_smartops.commands.untag import UntagCommand

__all__ = [
    "BaseCommand",
    "CommandsListCommand",
    "CostsCommand",
    "ExecCommand",
    "FindByTagsCommand",
    "HelpCommand",
    "InstanceDetailsCommand",
    "ListInstancesCommand",
    "MetricsCommand",
    "RebootInstanceCommand",
    "StartInstanceCommand",
    "StatusCommand",
    "StopInstanceCommand",
    "TagCommand",
    "UntagCommand",
]
