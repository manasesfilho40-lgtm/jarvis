import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("command_validator")


class DangerLevel(Enum):
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class ValidationResult(Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REQUIRES_CONFIRMATION = "requires_confirmation"


@dataclass
class CommandValidation:
    command: str
    tool: str
    result: ValidationResult
    danger_level: DangerLevel
    reason: str = ""
    suggested_message: str = ""
    metadata: dict = field(default_factory=dict)

    def is_allowed(self) -> bool:
        return self.result == ValidationResult.ALLOWED

    def needs_confirmation(self) -> bool:
        return self.result == ValidationResult.REQUIRES_CONFIRMATION


DANGEROUS_PATTERNS = [
    (r'\b(rm\s+-rf|format|del\s+/f|fdisk|mkfs|dd\s+if=)\b', DangerLevel.CRITICAL, "Destructive system command"),
    (r'\b(shutdown|reboot|halt|poweroff)\b', DangerLevel.HIGH, "System shutdown/reboot"),
    (r'\b(reg\s+(delete|add|remove)|regedit)\b', DangerLevel.CRITICAL, "Registry modification"),
    (r'\b(net\s+user|net\s+localgroup|net\s+accounts)\b', DangerLevel.CRITICAL, "User account modification"),
    (r'\b(dangerous|exploit|malware|virus|trojan)\b', DangerLevel.HIGH, "Potentially dangerous operation"),
    (r'\b(delete|remove)\s+(system|windows|system32)\b', DangerLevel.CRITICAL, "System file deletion"),
]

CONFIRMATION_PATTERNS = [
    (r'\b(install|uninstall)\b', DangerLevel.MEDIUM, "Software installation requires confirmation"),
    (r'\b(format|wipe|erase)\b', DangerLevel.HIGH, "Data destruction requires confirmation"),
    (r'\b(delete|remove)\s+(file|folder|directory)\b', DangerLevel.MEDIUM, "File deletion requires confirmation"),
    (r'\b(send\s+message|email|whatsapp)\b', DangerLevel.LOW, "Sending messages requires confirmation"),
    (r'\b(purchase|buy|order|subscribe|pag[ai]r|comprar)\b', DangerLevel.MEDIUM, "Financial transaction requires confirmation"),
    (r'\b(login|sign[-\s]?in|authenticate)\b', DangerLevel.MEDIUM, "Login/Authentication requires confirmation"),
    (r'\b(password|senha)\b', DangerLevel.HIGH, "Password operation requires confirmation"),
]


class CommandValidator:
    def __init__(self, require_confirmation: bool = True):
        self.require_confirmation = require_confirmation
        self._allowed_tools: set[str] = set()
        self._blocked_tools: set[str] = set()
        self._dangerous_commands: list[tuple[re.Pattern, DangerLevel, str]] = [
            (re.compile(p), dl, msg) for p, dl, msg in DANGEROUS_PATTERNS
        ]
        self._confirmation_commands: list[tuple[re.Pattern, DangerLevel, str]] = [
            (re.compile(p), dl, msg) for p, dl, msg in CONFIRMATION_PATTERNS
        ]
        self._confirmation_history: dict[str, float] = {}
        self._confirmation_cooldown = 300.0

    def allow_tool(self, *tool_names: str):
        for name in tool_names:
            self._allowed_tools.add(name)

    def block_tool(self, *tool_names: str):
        for name in tool_names:
            self._blocked_tools.add(name)

    def validate(self, command: str, tool: str = "", context: Optional[dict] = None) -> CommandValidation:
        context = context or {}

        if tool in self._blocked_tools:
            return CommandValidation(
                command=command, tool=tool,
                result=ValidationResult.BLOCKED,
                danger_level=DangerLevel.HIGH,
                reason=f"Tool '{tool}' is blocked",
                suggested_message=f"I cannot use {tool}, sir. It has been disabled for security reasons.",
            )

        command_lower = command.lower()

        for pattern, danger, reason in self._dangerous_commands:
            if pattern.search(command_lower):
                return CommandValidation(
                    command=command, tool=tool,
                    result=ValidationResult.BLOCKED,
                    danger_level=danger,
                    reason=reason,
                    suggested_message=f"I cannot perform this operation, sir. {reason}.",
                )

        for pattern, danger, reason in self._confirmation_commands:
            if pattern.search(command_lower):
                cache_key = f"{tool}:{pattern.pattern}"
                if cache_key in self._confirmation_history:
                    elapsed = time.time() - self._confirmation_history[cache_key]
                    if elapsed < self._confirmation_cooldown:
                        return CommandValidation(
                            command=command, tool=tool,
                            result=ValidationResult.ALLOWED,
                            danger_level=danger,
                            reason="Previously confirmed",
                        )

                if self.require_confirmation:
                    return CommandValidation(
                        command=command, tool=tool,
                        result=ValidationResult.REQUIRES_CONFIRMATION,
                        danger_level=danger,
                        reason=reason,
                        suggested_message=f"Sir, I need your confirmation: {reason}. Shall I proceed?",
                    )

        return CommandValidation(
            command=command, tool=tool,
            result=ValidationResult.ALLOWED,
            danger_level=DangerLevel.SAFE,
            reason="Command validated",
        )

    def confirm(self, command: str, tool: str = ""):
        cache_key = f"{tool}:{command[:50]}"
        self._confirmation_history[cache_key] = time.time()

    def validate_shell_command(self, command: str) -> CommandValidation:
        blocked_commands = [
            r'^\s*(rm\s+-rf\s+/|format\s+[a-z]:|del\s+/[fq]\s+[a-z]:)',
            r'(sudo\s+)?(shutdown|reboot|halt|poweroff)\s+(-[a-z]+\s+)?(now|0)',
            r'(reg\s+(delete|add|remove)\s+)',
            r'(net\s+user\s+/\s*(add|delete))',
        ]
        command_stripped = command.strip()
        for pattern in blocked_commands:
            if re.match(pattern, command_stripped, re.IGNORECASE):
                return CommandValidation(
                    command=command, tool="shell",
                    result=ValidationResult.BLOCKED,
                    danger_level=DangerLevel.CRITICAL,
                    reason="Blocked shell command",
                )
        return CommandValidation(
            command=command, tool="shell",
            result=ValidationResult.ALLOWED,
            danger_level=DangerLevel.LOW,
        )

    def validate_file_path(self, path: str) -> CommandValidation:
        protected_paths = [
            r'[\\/]Windows[\\/]',
            r'[\\/]System32[\\/]',
            r'[\\/]Program Files[\\/]',
            r'[\\/]Program Files \(x86\)[\\/]',
            r'[\\/]etc[\\/]',
            r'[\\/]usr[\\/]lib[\\/]',
        ]
        for pattern in protected_paths:
            if re.search(pattern, path, re.IGNORECASE):
                return CommandValidation(
                    command=path, tool="file_operation",
                    result=ValidationResult.BLOCKED,
                    danger_level=DangerLevel.CRITICAL,
                    reason="Protected system path",
                )
        return CommandValidation(
            command=path, tool="file_operation",
            result=ValidationResult.ALLOWED,
            danger_level=DangerLevel.SAFE,
        )

    def get_safe_tools(self) -> list[str]:
        return [t for t in self._allowed_tools if t not in self._blocked_tools]

    def __repr__(self):
        return f"CommandValidator(allowed={len(self._allowed_tools)}, blocked={len(self._blocked_tools)})"


_validator_instance = None


def get_validator() -> CommandValidator:
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = CommandValidator()
    return _validator_instance
