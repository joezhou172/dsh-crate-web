"""Ordered Bundle patch checks shared by Export, Preflight, Import and Verify."""
from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Any, Mapping

from .errors import ExportError, SchemaValidationError
from .validation import bundle_patch_paths


def check_patch_content(content: bytes, label: str) -> None:
    # This validates text/privacy; it deliberately does not interpret YAML or
    # claim the Loader can execute the patch. Runtime composition is separate.
    from .portability import assert_private_values_absent
    assert_private_values_absent(content, label)


def check_patch_declaration(manifest: Mapping[str, Any], expected: Any) -> None:
    dsh = manifest.get("dsh")
    bundle = dsh.get("bundle") if isinstance(dsh, Mapping) else None
    declared = bundle.get("patch") if isinstance(bundle, Mapping) else None
    if bundle_patch_paths(declared) != bundle_patch_paths(expected):
        raise SchemaValidationError("installed Bundle patch declaration differs from Crate (including order)")


def read_bundle_patches(package_root: Path, declaration: Any) -> tuple[tuple[str, bytes], ...]:
    root = package_root.resolve()
    patches = []
    for relative in bundle_patch_paths(declaration):
        path = package_root.joinpath(*relative.split("/"))
        try:
            path.resolve().relative_to(root)
            if not path.is_file() or path.is_symlink():
                raise ValueError("patch is not a regular file")
            content = path.read_bytes()
        except (ValueError, OSError) as error:
            raise ExportError(f"Bundle patch file is missing or escapes its package: {relative}") from error
        check_patch_content(content, relative)
        patches.append((relative, content))
    return tuple(patches)


def check_bundle_artifact(content: bytes, declaration: Any) -> None:
    """Check every declared patch and its package declaration without extraction."""
    paths = bundle_patch_paths(declaration)
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise SchemaValidationError("Bundle artifact contains duplicate members")
            package_member = archive.getmember("package/package.json")
            if not package_member.isfile():
                raise SchemaValidationError("Bundle artifact package.json must be a regular file")
            package_file = archive.extractfile(package_member)
            if package_file is None:
                raise SchemaValidationError("Bundle artifact package.json cannot be read")
            manifest = json.loads(package_file.read().decode("utf-8"))
            if not isinstance(manifest, Mapping):
                raise SchemaValidationError("Bundle artifact package.json must be an object")
            check_patch_declaration(manifest, declaration)
            for relative in paths:
                member = archive.getmember("package/" + relative)
                if not member.isfile():
                    raise SchemaValidationError(f"Bundle artifact patch must be a regular file: {relative}")
                source = archive.extractfile(member)
                if source is None:
                    raise SchemaValidationError(f"Bundle artifact patch cannot be read: {relative}")
                check_patch_content(source.read(), relative)
    except (OSError, tarfile.TarError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SchemaValidationError("Bundle artifact is invalid or a declared patch is missing") from error
