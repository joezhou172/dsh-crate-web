"""DSH Pack Phase 1 core and Phase 2 export.

The Pack core validates semantic Pack data and reads/writes a safe ZIP
container with SHA-256 integrity metadata. Export reads an existing Profile
and uses local ``npm pack`` only for explicitly embedded artifacts; it does
not install packages or start DSH.
"""

from .errors import (
    DshPackError,
    DuplicateEntryError,
    ExportError,
    IntegrityError,
    PackImportError,
    PathSafetyError,
    PackFormatError,
    SchemaValidationError,
)
from .export import EMBEDDED, REFERENCE_ONLY, ExportOptions, ExportResult, PluginExportOptions, export_profile
from .importer import DeleteResult, ImportOptions, ImportPlan, ImportResult, create_import_plan, delete_profile, import_pack
from .pack import PackData, create, read
from .preflight import Finding, PreflightContext, PreflightResult, inspect_pack, render_text
from .validation import validate_archive_path, validate_environment, validate_manifest, validate_plugins_lock
from .verify import (
    RUNTIME_STEPS,
    SmokeTestContract,
    SubprocessVerifyAdapter,
    VerifyOptions,
    VerifyResult,
    VerifyStep,
    load_smoke_contracts,
    verify_profile,
)

__all__ = [
    "DshPackError",
    "DeleteResult",
    "DuplicateEntryError",
    "EMBEDDED",
    "ExportError",
    "ExportOptions",
    "ExportResult",
    "Finding",
    "IntegrityError",
    "ImportOptions",
    "ImportPlan",
    "ImportResult",
    "PackData",
    "PackFormatError",
    "PackImportError",
    "PathSafetyError",
    "PreflightContext",
    "PreflightResult",
    "PluginExportOptions",
    "REFERENCE_ONLY",
    "RUNTIME_STEPS",
    "SchemaValidationError",
    "SmokeTestContract",
    "SubprocessVerifyAdapter",
    "VerifyOptions",
    "VerifyResult",
    "VerifyStep",
    "create",
    "export_profile",
    "create_import_plan",
    "delete_profile",
    "import_pack",
    "inspect_pack",
    "read",
    "render_text",
    "validate_archive_path",
    "validate_environment",
    "validate_manifest",
    "validate_plugins_lock",
    "load_smoke_contracts",
    "verify_profile",
]
