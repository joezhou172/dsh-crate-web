"""Installation checks without conflating recorded resolution and runtime."""
from __future__ import annotations

from typing import Any, Mapping


def expected_install_version(plugin: Mapping[str, Any]) -> str | None:
    """Use legacy resolution, or runtime only for an explicit unknown sentinel.

    Export has no pnpm resolution evidence. Its runtime identity can still
    constrain a supplied artifact or local package without inventing RESOLUTION.
    Missing/invalid legacy fields do not silently acquire a fallback.
    """
    resolved = plugin.get("resolved")
    version = resolved.get("version") if isinstance(resolved, Mapping) else None
    if version == "unknown":
        runtime = plugin.get("runtime")
        version = runtime.get("version") if isinstance(runtime, Mapping) else None
    return version if isinstance(version, str) and version.strip() and version != "unknown" else None


def unknown_source(plugin: Mapping[str, Any]) -> bool:
    requested = plugin.get("requested")
    return (not isinstance(requested, Mapping) or requested.get("sourceType") == "unknown"
            or requested.get("specifier") == "unknown")
