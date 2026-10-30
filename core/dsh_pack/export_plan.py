"""Read-only Export preview shared by CLI and Web."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from .errors import ExportError
from .portability import collect, discover


def build_plan(profile: Path, *, options, portable_items=None) -> dict[str, Any]:
    from .export import (EMBEDDED, REFERENCE_ONLY, PluginExportOptions,
                         _installed_package, _profile_bundles, _profile_dependencies,
                         _read_json_file, _imported_required_secrets)
    if options.export_mode not in {"share", "freeze", "custom"}:
        raise ExportError("invalid export mode")
    profile = Path(profile).resolve()
    manifest = _read_json_file(profile / "package.json", "Profile package.json")
    dependencies = _profile_dependencies(manifest)
    bundles = _profile_bundles(manifest)
    names = list(dict.fromkeys([*bundles, *dependencies]))
    if options.include_installation_bundles:
        from .export import _installed_bundle_inventory
        for name, *_ in _installed_bundle_inventory(profile):
            if name in options.plugin_options and name not in bundles:
                bundles.append(name)
            if name in options.plugin_options and name not in names:
                names.append(name)
    if not names:
        raise ExportError("Profile has no dependencies or bundles")
    unknown = set(options.plugin_options) - set(names)
    if unknown:
        raise ExportError("plugin selections refer to packages absent from Profile")
    plugins = []
    dependency_requirements = [
        {"name": "Node.js", "version": options.environment.get("node", {}).get("version", "unknown"),
         "kind": "runtime-host", "hostProvided": True, "peer": False, "bundled": False,
         "reason": "Node.js 运行环境不包含在 Crate 中，需要接收方提供并验证。"},
        {"name": "DSH runtime", "version": options.environment.get("dsh", {}).get("version", "unknown"),
         "kind": "runtime-host", "hostProvided": True, "peer": False, "bundled": False,
         "reason": "DSH 运行环境不包含在 Crate 中，需要接收方提供并验证。"},
    ]
    for name in names:
        _, package = _installed_package(profile, name, bundle=name in bundles)
        selected = options.plugin_options.get(name, PluginExportOptions(
            mode=EMBEDDED if options.export_mode == "freeze" else REFERENCE_ONLY))
        plugins.append({"name": name, "version": package.get("version", "unknown"),
                        "mode": selected.mode, "required": selected.required})
        bundled = package.get("bundleDependencies", package.get("bundledDependencies", []))
        for field, kind, peer in (("dependencies", "package-dependency", False),
                                  ("optionalDependencies", "optional-dependency", False),
                                  ("peerDependencies", "peer-dependency", True)):
            requirements = package.get(field, {})
            if not isinstance(requirements, dict):
                continue
            for dependency, version in requirements.items():
                if dependency in names:
                    continue
                is_bundled = not peer and (bundled is True or isinstance(bundled, list) and dependency in bundled)
                reason = ("包声明 bundled dependency；是否包含在实际制品中仍需检查，不能据此认定离线恢复成功。"
                          if is_bundled else
                          "包声明 peer dependency；需由目标组合满足并真实验证。" if peer else
                          "普通安装依赖不等于宿主已提供；需按来源解析、安装并验证。")
                dependency_requirements.append({"name": dependency, "version": version, "requiredBy": name,
                                          "kind": kind, "hostProvided": False, "peer": peer,
                                          "bundled": is_bundled, "reason": reason})
    if portable_items is None:
        _, portable_items = collect(profile, options.data_selection, set(names))
    inventory = list(portable_items)
    selected_paths = {item["path"] for item in portable_items}
    if profile.parent.name == "profiles":
        inventory.extend(item for item in discover(profile) if item["path"] not in selected_paths)
    secrets = list(tuple(options.required_secrets) or _imported_required_secrets(profile))
    inventory.extend({"name": name, "classification": "secret-name-only"} for name in secrets)
    inventory.extend([
        {"name": "credentials", "classification": "excluded", "reason": "Secret values never belong in a Crate"},
        {"name": "runtime state", "classification": "excluded", "reason": "node_modules, cache, logs and temporary files are not portable"},
    ])
    references = [p["name"] for p in plugins if p["mode"] == REFERENCE_ONLY]
    unsupported = [item["path"] for item in inventory if item["classification"] == "unsupported"]
    completeness = {
        "embedded": [p["name"] for p in plugins if p["mode"] == EMBEDDED],
        "referenceOnly": references, "secretNameOnly": secrets,
        "excluded": [item.get("path", item.get("name")) for item in inventory if item["classification"] == "excluded"],
        "unsupported": unsupported, "hostDependencies": [
            {"name": row["name"], "version": row["version"]}
            for row in dependency_requirements if row["hostProvided"]
        ],
        "offlineRestorable": "NO" if references else "UNPROVEN",
        "verification": "UNTESTED",
        "reason": "Export is not an offline restore test. Verify the exact artifact in a fresh isolated Home.",
    }
    return {"status": "plan", "readOnly": True, "profile": profile.name,
            "exportMode": options.export_mode, "plugins": plugins,
            "bundleOrder": bundles, "dataInventory": inventory,
            "requiredSecrets": secrets, "dependencyRequirements": dependency_requirements,
            "completeness": completeness}
