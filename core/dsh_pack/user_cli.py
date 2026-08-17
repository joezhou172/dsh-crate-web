"""User-facing Phase 6.5 CLI adapter.

This module is deliberately a thin boundary around the existing Core CLI.
It translates stable user arguments, preserves the Core JSON result under
``result``, and adds operation reports.  Pack schema, Preflight, Import, and
Verify decisions remain owned by :mod:`dsh_pack.cli` and the Core modules.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Sequence

from . import cli as core_cli
from .diagnostics import CRATE_VERSION, DIAGNOSTIC_SCHEMA_VERSION, PRODUCER
from .errors import PackImportError
from .importer import ImportOptions, create_import_plan


_OPERATION_ID = re.compile(r"^op-[0-9a-f]{32}$")


def _default_dsh_home() -> Path:
    value = os.environ.get("DSH_HOME")
    return (Path(value).expanduser() if value else Path.home() / ".dsh").resolve()


def _dsh_home(value: str | None) -> Path:
    return (Path(value).expanduser() if value else _default_dsh_home()).resolve()


def _profile_path(value: str, home: Path) -> Path:
    candidate = Path(value).expanduser()
    if (
        candidate.is_absolute()
        or candidate.exists()
        or "/" in value
        or "\\" in value
        or (len(value) > 1 and value[1] == ":")
    ):
        return candidate.resolve()
    return (home / "profiles" / value).resolve()


def _operation_home(args: argparse.Namespace, *, profile: str | None = None) -> Path:
    explicit = getattr(args, "dsh_home", None)
    if explicit:
        return _dsh_home(explicit)
    if profile:
        candidate = Path(profile).expanduser()
        if candidate.is_absolute() or "/" in profile or "\\" in profile:
            resolved = candidate.resolve()
            if resolved.parent.name == "profiles":
                return resolved.parent.parent
    return _default_dsh_home()


def _json_error(message: str) -> dict[str, Any]:
    return {"status": "failed", "error": {"message": message}}


def _invoke_core(argv: list[str]) -> tuple[int, dict[str, Any]]:
    """Invoke the existing Core entry point and parse its JSON contract."""

    stdout = StringIO()
    stderr = StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = core_cli.main([*argv, "--json"])
    except SystemExit as error:
        exit_code = int(error.code or 0)
    except Exception as error:  # keep the user CLI machine-readable
        return 1, _json_error(str(error))

    raw = stdout.getvalue().strip()
    if not raw:
        return exit_code, _json_error(stderr.getvalue().strip() or "Core returned no JSON result")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return exit_code, _json_error(raw)
    if not isinstance(result, dict):
        return exit_code, _json_error("Core returned a non-object JSON result")
    return exit_code, result


def _user_status(command: str, exit_code: int, result: dict[str, Any]) -> str:
    if command == "verify":
        status = result.get("status")
        return status if isinstance(status, str) else ("PASS" if exit_code == 0 else "FAIL")
    if command == "inspect":
        status = result.get("status")
        return status if isinstance(status, str) else ("READY" if exit_code == 0 else "NOT_READY")
    return "PASS" if exit_code == 0 else "FAIL"


def _envelope(
    command: str,
    exit_code: int,
    result: dict[str, Any],
    *,
    operation_id: str | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    status = _user_status(command, exit_code, result)
    if dry_run and command == "import":
        preflight = result.get("plan", {}).get("preflight", {}) if isinstance(result.get("plan"), dict) else {}
        if isinstance(preflight, dict) and preflight.get("status") in {"READY", "NOT_READY"}:
            status = preflight["status"]
    return {
        "producer": PRODUCER,
        "crateVersion": CRATE_VERSION,
        "diagnosticSchemaVersion": DIAGNOSTIC_SCHEMA_VERSION,
        "operation": command,
        "operationId": operation_id,
        "command": command,
        "status": status,
        "exitCode": exit_code,
        "dryRun": dry_run,
        "result": result,
    }


def _new_operation_id() -> str:
    return f"op-{uuid.uuid4().hex}"


def _operation_path(home: Path, operation_id: str) -> Path:
    if not _OPERATION_ID.fullmatch(operation_id):
        raise ValueError("invalid operation id")
    return home / ".dsh-pack" / "operations" / f"{operation_id}.json"


def _record_operation(home: Path, envelope: dict[str, Any]) -> None:
    operation_id = envelope.get("operationId")
    if not isinstance(operation_id, str):
        return
    path = _operation_path(home, operation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schemaVersion": 1,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        **envelope,
    }
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_operation(home: Path, operation_id: str) -> dict[str, Any]:
    path = _operation_path(home, operation_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"operation report not found: {operation_id}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"operation report is unreadable: {operation_id}") from error
    if not isinstance(value, dict):
        raise ValueError(f"operation report is not a JSON object: {operation_id}")
    return value


def _print(value: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return
    operation_id = value.get("operationId")
    if operation_id:
        print(f"Operation: {operation_id}")
    elif value.get("dryRun"):
        print("Operation: not persisted (--dry-run)")
    print(f"Status: {value.get('status', 'UNKNOWN')}")
    result = value.get("result", value)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _append_option(argv: list[str], flag: str, value: str | None) -> None:
    if value:
        argv.extend([flag, value])


def _append_repeated(argv: list[str], flag: str, values: list[str]) -> None:
    for value in values:
        argv.extend([flag, value])


def _export_core_args(args: argparse.Namespace, home: Path) -> list[str]:
    argv = ["export", "--profile", str(_profile_path(args.profile, home)), "--output", str(Path(args.output).expanduser()), "--json"]
    _append_option(argv, "--environment-json", args.environment_json)
    for flag, value in (
        ("--dsh-version", args.dsh_version),
        ("--node-version", args.node_version),
        ("--os-name", args.os_name),
        ("--os-version", args.os_version),
        ("--os-arch", args.os_arch),
    ):
        _append_option(argv, flag, value)
    _append_repeated(argv, "--embed", args.embed)
    _append_repeated(argv, "--reference-only", args.reference_only)
    if args.include_installed_bundles:
        argv.append("--include-installed-bundles")
    _append_repeated(argv, "--required-secret", args.required_secret)
    return argv


def _inspect_core_args(args: argparse.Namespace) -> list[str]:
    argv = ["inspect", args.pack, "--json"]
    for flag, value in (
        ("--dsh-version", args.dsh_version),
        ("--node-version", args.node_version),
        ("--os-name", args.os_name),
        ("--os-version", args.os_version),
    ):
        _append_option(argv, flag, value)
    _append_repeated(argv, "--secret", args.secret)
    _append_repeated(argv, "--plugin", args.plugin)
    if args.check_reference_plugins:
        argv.append("--check-reference-plugins")
    if args.no_process_secrets:
        argv.append("--no-process-secrets")
    return argv


def _import_core_args(args: argparse.Namespace, home: Path) -> list[str]:
    argv = ["import", args.pack, "--dsh-home", str(home), "--json"]
    for flag, value in (
        ("--dsh-version", args.dsh_version),
        ("--node-version", args.node_version),
        ("--os-name", args.os_name),
        ("--os-version", args.os_version),
    ):
        _append_option(argv, flag, value)
    _append_repeated(argv, "--secret", args.secret)
    _append_repeated(argv, "--reference-plugin", args.reference_plugin)
    _append_option(argv, "--target-profile", args.target_profile)
    if args.overwrite:
        argv.append("--overwrite")
    if args.confirm_overwrite:
        argv.append("--confirm-overwrite")
    if args.offline:
        argv.append("--offline")
    if args.no_process_secrets:
        argv.append("--no-process-secrets")
    return argv


def _verify_core_args(args: argparse.Namespace, home: Path) -> list[str]:
    argv = ["verify", "--dsh-home", str(home), "--profile", args.profile, "--mode", args.mode, "--json"]
    _append_option(argv, "--runner-config", args.runner_config)
    _append_repeated(argv, "--plugin-contract", args.plugin_contract)
    for flag, value in (
        ("--dsh-version", args.dsh_version),
        ("--node-version", args.node_version),
        ("--os-name", args.os_name),
        ("--os-version", args.os_version),
    ):
        _append_option(argv, flag, value)
    _append_repeated(argv, "--secret", args.secret)
    if args.no_process_secrets:
        argv.append("--no-process-secrets")
    return argv


def _delete_core_args(args: argparse.Namespace, home: Path) -> list[str]:
    argv = ["delete-profile", "--dsh-home", str(home), "--profile", args.profile, "--json"]
    if args.confirm_delete:
        argv.append("--confirm-delete")
    return argv


def _finish_operation(
    command: str,
    args: argparse.Namespace,
    home: Path,
    exit_code: int,
    result: dict[str, Any],
) -> int:
    envelope = _envelope(command, exit_code, result, operation_id=_new_operation_id())
    try:
        _record_operation(home, envelope)
    except OSError as error:
        # The Core result remains authoritative; report persistence is a
        # secondary diagnostic aid and must not rewrite Core decisions.
        envelope["reportError"] = str(error)
    _print(envelope, as_json=args.json)
    return exit_code


def _run_export(args: argparse.Namespace) -> int:
    home = _operation_home(args, profile=args.profile)
    exit_code, result = _invoke_core(_export_core_args(args, home))
    return _finish_operation("export", args, home, exit_code, result)


def _run_inspect(args: argparse.Namespace) -> int:
    home = _operation_home(args)
    exit_code, result = _invoke_core(_inspect_core_args(args))
    return _finish_operation("inspect", args, home, exit_code, result)


def _import_options(args: argparse.Namespace) -> ImportOptions:
    environment: dict[str, dict[str, str]] = {}
    for section, version in (("dsh", args.dsh_version), ("node", args.node_version)):
        if version:
            environment[section] = {"version": version}
    if args.os_name or args.os_version:
        environment["os"] = {
            key: value
            for key, value in (("name", args.os_name), ("version", args.os_version))
            if value
        }
    available_secrets = set() if args.no_process_secrets else set(os.environ)
    available_secrets.update(args.secret)
    return ImportOptions(
        current_environment=environment,
        available_secrets=available_secrets,
        reference_plugin_sources=core_cli._reference_sources(args.reference_plugin),
        allow_network_reference_install=not args.offline,
        target_profile_name=args.target_profile,
        overwrite_existing_profile=args.overwrite,
        overwrite_confirmation="OVERWRITE" if args.confirm_overwrite else None,
    )


def _run_dry_import(args: argparse.Namespace, home: Path) -> tuple[int, dict[str, Any]]:
    try:
        plan = create_import_plan(args.pack, home, options=_import_options(args))
    except (PackImportError, ValueError, OSError) as error:
        return 1, {"status": "failed", "error": error.as_dict() if isinstance(error, PackImportError) else {"message": str(error)}}
    return 0, {"status": "dry-run", "readOnly": True, "plan": plan.as_dict()}


def _run_import(args: argparse.Namespace) -> int:
    home = _dsh_home(args.dsh_home)
    if args.dry_run:
        exit_code, result = _run_dry_import(args, home)
        envelope = _envelope("import", exit_code, result, operation_id=None, dry_run=True)
        _print(envelope, as_json=args.json)
        return exit_code
    exit_code, result = _invoke_core(_import_core_args(args, home))
    return _finish_operation("import", args, home, exit_code, result)


def _run_verify(args: argparse.Namespace) -> int:
    home = _dsh_home(args.dsh_home)
    exit_code, result = _invoke_core(_verify_core_args(args, home))
    return _finish_operation("verify", args, home, exit_code, result)


def _run_delete_profile(args: argparse.Namespace) -> int:
    home = _dsh_home(args.dsh_home)
    exit_code, result = _invoke_core(_delete_core_args(args, home))
    return _finish_operation("delete-profile", args, home, exit_code, result)


def _run_report(args: argparse.Namespace) -> int:
    try:
        report = _load_operation(_dsh_home(args.dsh_home), args.operation_id)
    except ValueError as error:
        value = {"status": "FAIL", "error": {"message": str(error)}}
        _print(value, as_json=args.json)
        return 1
    _print(report, as_json=args.json)
    # Reading a report succeeded even when the recorded operation failed.
    # The original operation exit code remains available in the report.
    return 0


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dsh-home", help="DSH_HOME used for Profile resolution and operation reports")
    parser.add_argument("--dsh-version", help="current DSH version evidence")
    parser.add_argument("--node-version", help="current Node version evidence")
    parser.add_argument("--os-name", help="current OS name evidence")
    parser.add_argument("--os-version", help="current OS version evidence")
    parser.add_argument("--secret", action="append", default=[], help="declare an available Secret name")
    parser.add_argument("--no-process-secrets", action="store_true", help="do not use current process environment names")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dsh-crate", description="User-facing DSH Crate commands backed by the existing Core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export", help="export one Profile to a .dshcrate")
    export.add_argument("--profile", required=True, help="Profile name or Profile directory")
    export.add_argument("-o", "--output", required=True, help="output .dshcrate path")
    export.add_argument("--environment-json", help="JSON file containing Pack environment")
    export.add_argument("--dsh-version", default="unknown", help="DSH version evidence")
    export.add_argument("--node-version", default="unknown", help="Node version evidence")
    export.add_argument("--os-name", default="unknown", help="OS name evidence")
    export.add_argument("--os-version", default="unknown", help="OS version evidence")
    export.add_argument("--os-arch", default="unknown", help="OS architecture evidence")
    export.add_argument("--embed", action="append", default=[], metavar="PLUGIN")
    export.add_argument("--reference-only", action="append", default=[], metavar="PLUGIN")
    export.add_argument("--include-installed-bundles", action="store_true", help="include direct installed Bundle inventory in the exported Profile composition")
    export.add_argument("--required-secret", action="append", default=[], metavar="NAME")
    export.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    export.add_argument("--dsh-home", help="DSH_HOME used for Profile-name resolution and reports")
    export.set_defaults(handler=_run_export)

    inspect = subparsers.add_parser("inspect", help="read-only Pack preflight")
    inspect.add_argument("pack", help="input .dshcrate")
    _add_runtime_options(inspect)
    inspect.add_argument("--plugin", action="append", default=[], metavar="NAME[@VERSION]")
    inspect.add_argument("--check-reference-plugins", action="store_true")
    inspect.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    inspect.set_defaults(handler=_run_inspect)

    import_parser = subparsers.add_parser("import", help="import a Pack as a new Profile")
    import_parser.add_argument("pack", help="input .dshcrate")
    _add_runtime_options(import_parser)
    import_parser.add_argument("--dry-run", action="store_true", help="preflight and plan only; never write the target DSH_HOME")
    import_parser.add_argument("--offline", action="store_true", help="disable npm/GitHub fallback for missing reference-only plugins")
    import_parser.add_argument("--target-profile", help="new target Profile name; duplicate names are rejected")
    import_parser.add_argument("--overwrite", action="store_true", help="replace an existing Profile after confirmation")
    import_parser.add_argument("--confirm-overwrite", action="store_true", help="confirm the destructive overwrite operation")
    import_parser.add_argument("--reference-plugin", action="append", default=[], metavar="NAME=PACKAGE_DIR")
    import_parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    import_parser.set_defaults(handler=_run_import)

    verify = subparsers.add_parser("verify", help="verify a prepared Profile")
    verify.add_argument("--profile", required=True, help="Profile name under DSH_HOME/profiles")
    verify.add_argument("--mode", choices=("web", "headless"), default="web")
    verify.add_argument("--runner-config", help="JSON config for an explicit subprocess VerifyAdapter")
    verify.add_argument("--plugin-contract", action="append", default=[])
    _add_runtime_options(verify)
    verify.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    verify.set_defaults(handler=_run_verify)

    report = subparsers.add_parser("report", help="read a persisted operation report")
    report.add_argument("operation_id", help="operation id returned by a non-dry-run command")
    report.add_argument("--dsh-home", help="DSH_HOME containing .dsh-pack/operations")
    report.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    report.set_defaults(handler=_run_report)

    delete = subparsers.add_parser("delete-profile", help="delete one Profile after explicit confirmation")
    delete.add_argument("--profile", required=True, help="Profile name under DSH_HOME/profiles")
    delete.add_argument("--confirm-delete", action="store_true", help="confirm the destructive deletion")
    delete.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    delete.add_argument("--dsh-home", help="DSH_HOME containing the Profile and operation reports")
    delete.set_defaults(handler=_run_delete_profile)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # The Web bridge may resolve the installed ``dsh-pack`` console script.
    # Keep that existing integration on the raw Core contract; the bridge
    # sets this marker explicitly and never consumes the user envelope.
    if os.environ.get("DSH_PACK_CORE_MODE") == "1":
        return core_cli.main(argv)
    args = _build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover - exercised by the console script
    raise SystemExit(main())
