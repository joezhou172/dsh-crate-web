"""Resolve an explicit export draft; never change the source Profile."""
from __future__ import annotations
import json
from .errors import ExportError
from .registry import package_name, exact_version, fetch
from .bundle import check_bundle_artifact, read_bundle_patches

def resolve(profile, options, dependencies, bundles, profile_files):
    from .export import _installed_package, _registry_spec_satisfies, PluginExportOptions
    original = set(dependencies) | set(bundles)
    rows = options.selections
    if not isinstance(rows, tuple) or not rows or len(rows) > 500:
        raise ExportError("Export selection must contain 1 to 500 entries")
    selected, packages, remote, choices, seen = [], {}, {}, {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "included", "selection", "artifactMode", "activateOnImport"}:
            raise ExportError("Invalid export selection fields")
        name = package_name(row["name"])
        if name in seen:
            raise ExportError("Duplicate selected package: " + name)
        seen.add(name)
        if type(row["included"]) is not bool or type(row["activateOnImport"]) is not bool:
            raise ExportError("Invalid export selection boolean")
        if name.startswith("@deepseek-ai/") and name in original and (
                not row["included"] or row["selection"] != {"kind": "installed"} or (name in bundles and not row["activateOnImport"])):
            raise ExportError("Keep the installed host Bundle: " + name)
        if not row["included"]:
            continue
        selection = row["selection"]
        if not isinstance(selection, dict):
            raise ExportError("Invalid package selection")
        if selection == {"kind": "installed"}:
            if name not in original:
                raise ExportError("Installed selection absent from source Profile: " + name)
            _, manifest = _installed_package(profile, name, bundle=name in bundles)
        elif set(selection) == {"kind", "version"} and selection["kind"] == "registry":
            version = exact_version(selection["version"])
            manifest, content, integrity, source_url = fetch(profile, name, version, options.npm_command)
            remote[name] = (content, integrity, source_url)
        else:
            raise ExportError("Unsupported package selection")
        patch = manifest.get("dsh", {}).get("bundle", {}).get("patch")
        if row["activateOnImport"] and not patch:
            raise ExportError("Package has no Bundle declaration; add as dependency instead: " + name)
        if row["activateOnImport"] and name in remote:
            check_bundle_artifact(remote[name][0], patch)
        selected.append(row)
        packages[name] = manifest
        choices[name] = PluginExportOptions(mode=row["artifactMode"])
    if original - seen:
        raise ExportError("Selection omitted source packages; refresh inventory")
    if not selected:
        raise ExportError("Select at least one plugin")
    names = [r["name"] for r in selected]
    enabled = {r["name"] for r in selected if r["activateOnImport"]}
    target_bundles = [n for n in bundles if n in enabled] + [n for n in names if n in enabled and n not in bundles]
    excluded = original - set(names)
    changed = excluded | set(remote) | (set(bundles) - enabled)
    # Stop on config references whose ownership cannot be safely determined.
    for path, content in profile_files.items():
        if path in {"package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock"}:
            continue
        text = content.decode("utf-8", errors="replace")
        if changed and (path.endswith((".js", ".mjs", ".cjs", ".ts")) or (("$" + "{") in text and path.endswith((".yaml", ".yml")))):
            raise ExportError("Dynamic Profile configuration requires review before changing plugins: " + path)
        for name in changed:
            if name in text:
                raise ExportError("Configuration references changed plugin; adjust the export config first: " + path + " -> " + name)
    registered = {}
    for name, manifest in packages.items():
        for field in ("dependencies", "peerDependencies"):
            for dep, spec in manifest.get(field, {}).items():
                optional = field == "peerDependencies" and manifest.get("peerDependenciesMeta", {}).get(dep, {}).get("optional") is True
                if dep in excluded and not optional:
                    raise ExportError(name + " requires excluded plugin " + dep)
                if dep in packages and _registry_spec_satisfies(spec, packages[dep]["version"]) is False and not optional:
                    raise ExportError(name + " requires " + dep + "@" + spec + "; selected version does not satisfy it")
        if name in target_bundles:
            if name in remote:
                import io, tarfile
                from .validation import bundle_patch_paths
                with tarfile.open(fileobj=io.BytesIO(remote[name][0]), mode="r:gz") as archive:
                    patches = [(path, archive.extractfile("package/" + path).read()) for path in bundle_patch_paths(manifest["dsh"]["bundle"]["patch"])]
            else:
                root, _ = _installed_package(profile, name, bundle=True)
                patches = read_bundle_patches(root, manifest["dsh"]["bundle"]["patch"])
            from .export import _bundle_inserted_loader_ids
            for path, content in patches:
                text = content.decode("utf-8")
                for dep in excluded:
                    if dep in text:
                        raise ExportError("Retained Bundle references excluded plugin: " + name + " -> " + dep)
                for row_id in _bundle_inserted_loader_ids(text):
                    if row_id in registered:
                        raise ExportError("Duplicate loader row " + row_id + ": " + registered[row_id] + " and " + name)
                    registered[row_id] = name
    target = json.loads(profile_files["package.json"])
    target["dependencies"] = {n: (packages[n]["version"] if n in remote else dependencies.get(n, packages[n]["version"])) for n in names}
    target.setdefault("dsh", {}).setdefault("profile", {})["bundles"] = target_bundles
    profile_files["package.json"] = (json.dumps(target, ensure_ascii=False, indent=2) + "\n").encode()
    if changed or set(names) != original:
        for key in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock"):
            profile_files.pop(key, None)
    return names, target_bundles, target["dependencies"], choices, packages, remote, excluded
