"""Published artifact locations for each independently auditable route profile."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactPaths:
    """The complete route artifact set for one route profile."""

    geojson: Path
    summary: Path
    review: Path
    manifest: Path

    @classmethod
    def for_profile(cls, output_dir: Path, profile: str) -> "ArtifactPaths":
        """Return the fixed publication names for a supported route profile."""
        if profile == "coastal":
            return cls(
                output_dir / "coastal-route.geojson",
                output_dir / "summary.json",
                output_dir / "review.md",
                output_dir / "route-manifest.json",
            )
        if profile == "inland":
            return cls(
                output_dir / "inland-route.geojson",
                output_dir / "inland-summary.json",
                output_dir / "inland-review.md",
                output_dir / "inland-route-manifest.json",
            )
        raise ValueError(f"unsupported route profile: {profile}")
