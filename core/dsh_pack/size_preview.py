"""Measure a temporary export using exactly the normal exporter; never retain it."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from .export import ExportOptions, export_profile


def build_preview(profile: Path, *, options: ExportOptions, frozen_output: Path | None = None) -> dict:
    # Keep this outside build_plan: export_profile itself uses that pure plan helper.
    # Errors deliberately propagate through the existing structured CLI diagnostic.
    with TemporaryDirectory(prefix="dsh-crate-preview-") as directory:
        result = export_profile(profile, frozen_output or Path(directory) / "preview.dshcrate", options=options)
        categories = {name: 0 for name in ("plugins", "profile", "userData", "metadata")}
        entries = []
        with ZipFile(result.path) as archive:
            for entry in archive.infolist():
                category = ("plugins" if entry.filename.startswith("plugins/") else
                            "profile" if entry.filename.startswith("profile/") else
                            "userData" if entry.filename.startswith("user-data/") else "metadata")
                categories[category] += entry.compress_size
                entries.append({"path": entry.filename, "category": category,
                                "compressedBytes": entry.compress_size, "uncompressedBytes": entry.file_size})
        total = result.path.stat().st_size
        overhead = total - sum(categories.values())
        return {**result.plan, "sizePreview": {
            "status": "measured", "basis": "temporary-export", "archiveBytes": total,
            "categories": categories, "containerBytes": overhead,
            "uncompressedBytes": sum(item["uncompressedBytes"] for item in entries),
            "largestEntries": sorted(entries, key=lambda item: (-item["compressedBytes"], item["path"]))[:5],
            "referenceOnlyCount": len(result.plan["completeness"]["referenceOnly"]),
            "finalSizeMayChange": frozen_output is None,
        }}
