"""Command-line entry point for the DSH Pack core."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .errors import DshPackError, PackImportError
from .export import EMBEDDED, REFERENCE_ONLY, ExportOptions, PluginExportOptions, export_profile
from .importer import ImportOptions, create_import_plan, delete_profile, import_pack
from .preflight import PreflightContext, inspect_pack, render_text
from .verify import SubprocessVerifyAdapter, VerifyOptions, load_smoke_contracts, verify_profile


def _plugin_inventory(values: list[str]) -> dict[str, str | None]:
    inventory: dict[str, str | None] = {}
    for value in values:
        if "@" in value[1:]:
            name, version = value.rsplit("@", 1)
            inventory[name] = version or None
        else:
            inventory[value] = None
    return inventory


def _context(args: argparse.Namespace) -> PreflightContext:
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
    available_plugins = None
    if args.check_reference_plugins or args.plugin:
        available_plugins = _plugin_inventory(args.plugin)
    return PreflightContext(
        current_environment=environment,
        available_secrets=None if not args.no_process_secrets else set(),
        available_plugins=available_plugins,
        allow_network_reference_install=getattr(args, "allow_network_reference_install", False),
    )


def _inspect_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("inspect", help="read-only Pack preflight")
    parser.add_argument("pack", help="input .dshcrate")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--dsh-version", help="current DSH version")
    parser.add_argument("--node-version", help="current Node version")
    parser.add_argument("--os-name", help="current OS name")
    parser.add_argument("--os-version", help="current OS version")
    parser.add_argument("--secret", action="append", default=[], help="declare an available Secret name")
    parser.add_argument("--plugin", action="append", default=[], metavar="NAME[@VERSION]", help="declare an installed reference-only plugin")
    parser.add_argument("--check-reference-plugins", action="store_true", help="treat --plugin values as the complete plugin inventory")
    parser.add_argument("--allow-network-reference-install", action="store_true", help="report supported missing reference-only sources as npm network installs")
    parser.add_argument("--no-process-secrets", action="store_true", help="do not use current process environment names")
    parser.set_defaults(handler=_run_inspect)


def _export_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("export", help="export an existing Profile into a .dshcrate")
    parser.add_argument("--profile", required=True, help="Profile directory")
    parser.add_argument("--output", required=True, help="output .dshcrate path")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--environment-json", help="JSON object containing Pack environment")
    parser.add_argument("--dsh-version", default="unknown", help="DSH version evidence")
    parser.add_argument("--node-version", default="unknown", help="Node version evidence")
    parser.add_argument("--os-name", default="unknown", help="OS name evidence")
    parser.add_argument("--os-version", default="unknown", help="OS version evidence")
    parser.add_argument("--os-arch", default="unknown", help="OS architecture evidence")
    parser.add_argument("--embed", action="append", default=[], metavar="PLUGIN", help="embed one plugin artifact")
    parser.add_argument("--reference-only", action="append", default=[], metavar="PLUGIN", help="keep one plugin reference-only")
    parser.add_argument("--include-installed-bundles", action="store_true", help="include direct installed Bundle inventory in the exported Profile composition")
    parser.add_argument("--required-secret", action="append", default=[], metavar="NAME", help="record one required Secret name")
    parser.set_defaults(handler=_run_export)


def _reference_sources(values: list[str]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--reference-plugin must use NAME=PACKAGE_DIRECTORY")
        name, source = value.split("=", 1)
        if not name or not source:
            raise ValueError("--reference-plugin must use NAME=PACKAGE_DIRECTORY")
        sources[name] = Path(source)
    return sources


def _import_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("import", help="prepare a Pack as a new Profile")
    parser.add_argument("pack", help="input .dshcrate")
    parser.add_argument("--dsh-home", required=True, help="target isolated DSH_HOME")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--dsh-version", help="current DSH version")
    parser.add_argument("--node-version", help="current Node version")
    parser.add_argument("--os-name", help="current OS name")
    parser.add_argument("--os-version", help="current OS version")
    parser.add_argument("--secret", action="append", default=[], help="declare an available Secret name")
    parser.add_argument("--no-process-secrets", action="store_true", help="do not use current process environment names")
    parser.add_argument("--offline", action="store_true", help="disable npm/GitHub fallback for missing reference-only plugins")
    parser.add_argument("--target-profile", help="requested target Profile name; new imports refuse duplicate names")
    parser.add_argument("--overwrite", action="store_true", help="replace the selected existing Profile after explicit confirmation")
    parser.add_argument("--confirm-overwrite", action="store_true", help="confirm the destructive overwrite operation")
    parser.add_argument(
        "--reference-plugin",
        action="append",
        default=[],
        metavar="NAME=PACKAGE_DIR",
        help="install one reference-only plugin from a local package directory",
    )
    parser.add_argument("--plan-only", action="store_true", help="preflight and plan only; never write the target DSH_HOME")
    parser.set_defaults(handler=_run_import)


def _run_inspect(args: argparse.Namespace) -> int:
    context = _context(args)
    if args.secret:
        available = set() if context.available_secrets is not None else set()
        if context.available_secrets is None:
            import os

            available.update(os.environ)
        available.update(args.secret)
        context = PreflightContext(
            current_environment=context.current_environment,
            available_secrets=available,
            available_plugins=context.available_plugins,
            allow_network_reference_install=context.allow_network_reference_install,
        )
    result = inspect_pack(args.pack, context=context)
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(result))
    return 1 if result.blockers else 0


def _export_environment(args: argparse.Namespace) -> dict[str, object]:
    if args.environment_json:
        value = json.loads(Path(args.environment_json).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("environment JSON must contain an object")
        return value
    return {
        "schemaVersion": 1,
        "os": {"name": args.os_name, "version": args.os_version, "arch": args.os_arch},
        "node": {"version": args.node_version},
        "dsh": {"version": args.dsh_version},
    }


def _export_payload(result: object) -> dict[str, object]:
    # Keep this projection deliberately small and value-safe. PackData contains
    # artifact bytes, which must never be serialized into the UI/CLI response.
    export_result = result
    data = export_result.data  # type: ignore[attr-defined]
    return {
        "status": "exported",
        "path": str(export_result.path),  # type: ignore[attr-defined]
        "profile": data.manifest.get("profile"),
        "environment": data.manifest.get("environment"),
        "requiredSecrets": data.manifest.get("requiredSecrets", []),
        "plugins": data.plugins_lock.get("plugins", []),
        "artifactPaths": sorted(f"plugins/{name}" for name in data.plugin_artifacts),
    }


def _run_export(args: argparse.Namespace) -> int:
    overlap = set(args.embed) & set(args.reference_only)
    if overlap:
        payload = {"status": "failed", "error": {"message": f"plugin selected for both --embed and --reference-only: {sorted(overlap)}"}}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"EXPORT FAIL: {payload['error']['message']}")
        return 2
    plugin_options = {name: PluginExportOptions(mode=EMBEDDED) for name in args.embed}
    plugin_options.update({name: PluginExportOptions(mode=REFERENCE_ONLY) for name in args.reference_only})
    try:
        result = export_profile(
            args.profile,
            args.output,
            options=ExportOptions(
                environment=_export_environment(args),
                required_secrets=tuple(args.required_secret),
                plugin_options=plugin_options,
                include_installation_bundles=args.include_installed_bundles,
            ),
        )
    except (DshPackError, OSError, ValueError, json.JSONDecodeError) as error:
        payload = {"status": "failed", "error": {"message": str(error)}}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"EXPORT FAIL: {error}")
        return 2
    payload = _export_payload(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"EXPORT PASS: {result.path}")
    return 0


def _run_import(args: argparse.Namespace) -> int:
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
    try:
        sources = _reference_sources(args.reference_plugin)
        options = ImportOptions(
            current_environment=environment,
            available_secrets=available_secrets,
            reference_plugin_sources=sources,
            allow_network_reference_install=not args.offline,
            target_profile_name=args.target_profile,
            overwrite_existing_profile=args.overwrite,
            overwrite_confirmation="OVERWRITE" if args.confirm_overwrite else None,
        )
        if args.plan_only:
            plan = create_import_plan(args.pack, args.dsh_home, options=options)
            payload = {"status": "plan", "readOnly": True, "plan": plan.as_dict()}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"Plan: {plan.profile_name}")
            return 0
        result = import_pack(args.pack, args.dsh_home, options=options)
    except (PackImportError, ValueError, OSError) as error:
        payload = {"status": "failed", "error": error.as_dict() if isinstance(error, PackImportError) else {"message": str(error)}}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"Import failed: {payload['error'].get('message', str(error))}")
        return 1
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Status: {result.status}")
        print(f"Profile: {result.profile_path}")
        print(f"Metadata: {result.metadata_path}")
        print(f"Installed plugins: {len(result.installed_plugins)}")
    return 0


def _delete_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("delete-profile", help="delete one Profile after explicit confirmation")
    parser.add_argument("--dsh-home", required=True, help="DSH_HOME containing the Profile")
    parser.add_argument("--profile", required=True, help="Profile name under DSH_HOME/profiles")
    parser.add_argument("--confirm-delete", action="store_true", help="confirm the destructive deletion")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.set_defaults(handler=_run_delete_profile)


def _run_delete_profile(args: argparse.Namespace) -> int:
    try:
        result = delete_profile(
            args.dsh_home,
            args.profile,
            confirmation="DELETE" if args.confirm_delete else None,
        )
    except PackImportError as error:
        payload = {"status": "failed", "error": error.as_dict()}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"Delete failed: {error}")
        return 1
    payload = result.as_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Deleted Profile: {result.profile_name}")
    return 0


def _verify_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("verify", help="verify a prepared Profile without changing it")
    parser.add_argument("--dsh-home", required=True, help="isolated DSH_HOME containing the prepared Profile")
    parser.add_argument("--profile", required=True, help="Profile name under DSH_HOME/profiles")
    parser.add_argument("--mode", choices=("web", "headless"), default="web", help="runtime surface to verify")
    parser.add_argument("--runner-config", help="JSON config for an explicit subprocess VerifyAdapter")
    parser.add_argument("--plugin-contract", action="append", default=[], help="JSON file containing one plugin Smoke Test contract")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--dsh-version", help="current DSH version evidence")
    parser.add_argument("--node-version", help="current Node version evidence")
    parser.add_argument("--os-name", help="current OS name evidence")
    parser.add_argument("--os-version", help="current OS version evidence")
    parser.add_argument("--secret", action="append", default=[], help="declare an available Secret name")
    parser.add_argument("--no-process-secrets", action="store_true", help="do not use current process environment names")
    parser.set_defaults(handler=_run_verify)


def _run_verify(args: argparse.Namespace) -> int:
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
    try:
        contracts = tuple(
            contract
            for path in args.plugin_contract
            for contract in load_smoke_contracts(path)
        )
        adapter = None
        if args.runner_config:
            config = json.loads(Path(args.runner_config).read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("runner config JSON must contain an object")
            adapter = SubprocessVerifyAdapter(config)
        result = verify_profile(
            VerifyOptions(
                dsh_home=Path(args.dsh_home).resolve(),
                profile_name=args.profile,
                mode=args.mode,
                current_environment=environment,
                available_secret_names=frozenset(available_secrets),
                adapter=adapter,
                plugin_contracts=contracts,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        payload = {"status": "FAIL", "error": {"message": str(error)}}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"Verify failed: {error}")
        return 1
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Status: {result.status}")
        for step in result.steps:
            print(f"{step.status:9} {step.name}: {step.message}")
    return 0 if result.status == "PASS" else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dsh-crate", description="Portable DSH environment Crate tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _inspect_parser(subparsers)
    _export_parser(subparsers)
    _import_parser(subparsers)
    _delete_parser(subparsers)
    _verify_parser(subparsers)
    args = parser.parse_args(argv)
    return args.handler(args)
