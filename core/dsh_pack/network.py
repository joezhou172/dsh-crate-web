"""Network source resolution shared by Preflight and Import.

This module only turns Pack source metadata into an npm install argument. It
does not resolve versions itself and never invokes a shell. npm remains the
resolver for registry, GitHub/Git and tarball sources.
"""

from __future__ import annotations

import re

from collections.abc import Mapping
from typing import Any


NETWORK_SOURCE_TYPES = frozenset({"registry", "git", "tarball", "alias"})


def network_source_details(plugin: Mapping[str, Any]) -> dict[str, str] | None:
    """Return the recorded network source, or ``None`` for local-only sources."""

    requested = plugin.get("requested")
    if not isinstance(requested, Mapping):
        return None
    source_type = requested.get("sourceType")
    specifier = requested.get("specifier")
    if not isinstance(source_type, str) or source_type not in NETWORK_SOURCE_TYPES:
        return None
    if not isinstance(specifier, str) or not specifier.strip() or specifier == "unknown":
        resolved = plugin.get("resolved")
        locator = resolved.get("locator") if isinstance(resolved, Mapping) else None
        if isinstance(locator, str) and locator.startswith("registry:"):
            specifier = locator.removeprefix("registry:")
        elif isinstance(locator, str) and locator.strip():
            specifier = locator
        else:
            return None
    return {"sourceType": source_type, "specifier": specifier.strip()}


def npm_install_specifier(plugin: Mapping[str, Any]) -> str | None:
    """Build one positional npm package spec from a Pack plugin entry.

    ``git:owner/repo`` is normalized to npm's GitHub shorthand. Other Git,
    tarball and alias forms are passed through to npm unchanged. The caller
    must pass the argument after ``--`` so a malicious Pack cannot turn it
    into an npm option.
    """

    details = network_source_details(plugin)
    if details is None:
        return None
    name = plugin.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    source_type = details["sourceType"]
    specifier = details["specifier"]
    if source_type in {"registry", "alias"}:
        resolved = plugin.get("resolved")
        exact_version = resolved.get("version") if isinstance(resolved, Mapping) else None
        if (
            source_type == "registry"
            and isinstance(exact_version, str)
            and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.\-]+)?", exact_version)
        ):
            # Install the exact version recorded at export time.  Using the
            # requested range alone lets npm resolve to a different (older)
            # version when the target Profile already declares the same range.
            return f"{name}@={exact_version}"
        return f"{name}@{specifier}"
    if source_type == "git" and specifier.startswith("git:"):
        value = specifier[4:]
        if value.startswith(("http://", "https://", "ssh://", "git+")):
            return value if value.startswith("git+") else f"git+{value}"
        return f"github:{value}"
    return specifier

