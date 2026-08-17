"""Typed errors for the Phase 1 Pack reader and writer."""

from .diagnostics import decorate_issue


class DshPackError(Exception):
    """Base class for expected DSH Pack failures."""


class SchemaValidationError(DshPackError):
    """Pack JSON does not satisfy the supported schema."""


class PackFormatError(DshPackError):
    """The ZIP container or required Pack members are invalid."""


class PathSafetyError(DshPackError):
    """A Pack member escapes or violates the allowed archive path model."""


class DuplicateEntryError(PackFormatError):
    """A ZIP contains the same logical member more than once."""


class IntegrityError(DshPackError):
    """A declared integrity record does not match the Pack contents."""


class ExportError(DshPackError):
    """A Profile cannot be exported into a valid DSH Pack."""


class PackImportError(DshPackError):
    """A Pack cannot be prepared as a new Profile."""

    def __init__(self, message: str, *, stage: str, code: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.details = details or {}

    def as_dict(self) -> dict:
        details = dict(self.details)
        default_expected = {
            "planning": {"operation": "target Profile is available and safe to create or overwrite"},
            "configuration": {"operation": "write Pack profile configuration"},
            "embedded-install": {"operation": "install a valid embedded artifact"},
            "reference-install": {"operation": "install the reference-only package"},
            "network-install": {"operation": "download and install the recorded network package"},
            "delete": {"operation": "delete the selected Profile"},
            "version-confirmation": {"operation": "installed package matches Pack identity"},
            "commit": {"operation": "commit the prepared Profile and metadata"},
        }.get(self.stage, {"operation": "complete successfully"})
        default_evidence = {
            "stage": self.stage,
            "code": self.code,
            "error": details.get("error", str(self)),
        }
        default_impact = {
            "planning": "Import did not start and no target Profile was changed",
            "configuration": "the new Profile could not be fully configured",
            "embedded-install": "an embedded package was not installed",
            "reference-install": "a reference-only package was not installed",
            "network-install": "a network package was not installed into the temporary Profile",
            "delete": "the selected Profile was not deleted",
            "version-confirmation": "the installed package identity does not satisfy the Pack",
            "commit": "the prepared Profile was not committed as a successful Import",
        }.get(self.stage, f"Import stopped during {self.stage}")
        default_next_step = {
            "planning": "Choose a new target Profile and retry Import",
            "configuration": "check the Profile configuration target and retry Import",
            "embedded-install": "check the embedded artifact and retry Import",
            "reference-install": "provide the exact reference source or installer result and retry Import",
            "network-install": "check npm/network access or provide an embedded artifact and retry Import",
            "delete": "check the Profile path and retry the confirmed deletion",
            "version-confirmation": "provide an artifact with the Pack resolution version and retry Import",
            "commit": "inspect the commit evidence and retry Import",
        }.get(self.stage, "Review the diagnostic evidence, correct the reported item, and retry Import.")
        item = (
            details.get("item")
            or details.get("plugin")
            or details.get("path")
            or details.get("profilePath")
            or self.code
        )
        observed = details.get("observed") or {"message": str(self), "code": self.code}
        evidence = details.get("evidence") or {"stage": self.stage, "code": self.code}
        impact = details.get("impact") or f"Import stopped during {self.stage}"
        original_profile_status = details.get("originalProfileStatus", "unchanged")
        failed_profile_status = details.get(
            "failedProfileStatus",
            details.get("temporaryProfileStatus", "cleaned"),
        )
        temporary_profile_status = details.get("temporaryProfileStatus", failed_profile_status)
        result = {
            "code": self.code,
            "stage": self.stage,
            "item": item,
            "expected": details.get("expected") or default_expected,
            "observed": observed,
            "command": details.get("command"),
            "exitCode": details.get("exitCode"),
            "stdout": details.get("stdout"),
            "stderr": details.get("stderr"),
            "evidence": evidence or default_evidence,
            "impact": impact or default_impact,
            "originalProfileStatus": original_profile_status,
            "failedProfileStatus": failed_profile_status,
            "temporaryProfileStatus": temporary_profile_status,
            "canRetry": details.get("canRetry", True),
            "suggestedNextStep": details.get(
                "suggestedNextStep",
                default_next_step,
            ),
            "severity": details.get("severity", "BLOCKER"),
            "canContinue": details.get("canContinue", False),
            "suggestedChecks": details.get("suggestedChecks") or _default_checks(self.stage, self.code),
            "message": str(self),
            "details": details,
        }
        return decorate_issue(
            result,
            operation="import",
            status="FAIL",
            operation_id=details.get("operationId"),
        )


def _default_checks(stage: str, code: str) -> list[str]:
    """Return a small stage-aware list of checks for a failure diagnostic."""

    generic = [
        f"confirm the exact {code} evidence above",
        "verify the target DSH_HOME and Profile path are correct",
        "retry after correcting the reported item, or switch to a non-destructive alternative",
    ]
    stage_checks = {
        "planning": [
            "verify the target Profile name is available and safe",
            "confirm the Pack schema and SHA-256 integrity are valid",
            "review environment compatibility findings before Import",
        ],
        "configuration": [
            "inspect the Profile configuration files written by the Pack",
            "confirm the target Profile directory is writable",
        ],
        "embedded-install": [
            "verify the embedded artifact SHA-256 against the Pack lock",
            "confirm the artifact is a valid npm tarball",
            "check for unsupported hardlink or symlink members",
        ],
        "reference-install": [
            "provide the exact reference package source or installer result",
            "verify the installed reference package identity matches the Pack",
        ],
        "network-install": [
            "check npm registry and network reachability",
            "verify the recorded package version exists on the registry",
            "retry with a longer timeout, or provide an embedded artifact",
        ],
        "delete": [
            "confirm the exact Profile path and name",
            "verify the Profile is not the active runtime Profile",
        ],
        "version-confirmation": [
            "verify the installed package version matches the Pack resolution",
            "provide an artifact or source with the Pack resolution version",
        ],
        "commit": [
            "inspect the commit evidence for the Profile and metadata",
            "verify no half-written Profile or metadata remains",
        ],
    }
    return stage_checks.get(stage, generic)
