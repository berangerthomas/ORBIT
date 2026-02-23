"""
Destination path generation for ORBIT.
Maps source images to structured destination paths based on EXIF dates.
Handles name conflicts using distinctive path elements.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from orbit.exif import DatetimeStrategy


class PathGenerator:
    """Generates destination paths based on EXIF data and strftime patterns."""

    def __init__(
        self,
        destination_dir: Path,
        pattern: str,
        strategy: DatetimeStrategy,
        fallback_pattern: str = "Unknown/%Y%m%d_%H%M%S",
        logger: logging.Logger | None = None,
    ):
        self.destination_dir = destination_dir
        self.pattern = pattern
        self.strategy = strategy
        self.fallback_pattern = fallback_pattern
        self.logger = logger or logging.getLogger("orbit.path")

        # Track pending conflicts: dest_name -> list of (source_path, dest_dir)
        self._pending_conflicts: dict[str, list[tuple[Path, Path]]] = defaultdict(list)
        # Cache of resolved paths: source_path -> dest_path
        self._resolved_paths: dict[Path, Path] = {}

        self._validate_pattern()

    def _validate_pattern(self) -> None:
        """Validate the strftime pattern eagerly at init time."""
        test_dt = datetime(2020, 6, 15, 12, 30, 45)
        try:
            test_dt.strftime(self.pattern)
        except Exception as e:
            raise ValueError(
                f"Invalid strftime pattern '{self.pattern}': {e}"
            ) from e
        try:
            test_dt.strftime(self.fallback_pattern)
        except Exception as e:
            raise ValueError(
                f"Invalid fallback strftime pattern '{self.fallback_pattern}': {e}"
            ) from e

    def prepare(self, image_paths: list[tuple[Path, dict]]) -> None:
        """
        First pass: identify all potential conflicts.

        Args:
            image_paths: List of (source_path, exif_data) tuples.
        """
        self._pending_conflicts.clear()
        self._resolved_paths.clear()

        for image_path, exif_data in image_paths:
            dest_dir = self._get_dest_dir(exif_data)
            dest_name = image_path.name

            # Group by destination name (filename only)
            self._pending_conflicts[dest_name].append((image_path, dest_dir))

        self.logger.debug(
            f"Prepared {len(image_paths)} files, "
            f"{sum(1 for v in self._pending_conflicts.values() if len(v) > 1)} conflicts detected"
        )

    def generate(self, image_path: Path, exif_data: dict) -> Path:
        """
        Generate the destination path for an image.

        Args:
            image_path: Source image path.
            exif_data: Extracted EXIF data dict.

        Returns:
            Full destination path (with conflict resolution).
        """
        # Check if already resolved
        if image_path in self._resolved_paths:
            return self._resolved_paths[image_path]

        dest_dir = self._get_dest_dir(exif_data)
        dest_name = image_path.name

        # Check for conflicts
        conflicts = self._pending_conflicts.get(dest_name, [])

        if len(conflicts) <= 1:
            # No conflict, use original name
            dest_path = dest_dir / dest_name
        else:
            # Resolve conflict using distinctive suffix
            dest_path = self._resolve_conflict_with_suffix(
                dest_dir, image_path, dest_name, conflicts
            )

        # Cache the result
        self._resolved_paths[image_path] = dest_path

        # Handle existing files on disk (edge case for resume)
        dest_path = self._ensure_unique(dest_path)

        self._resolved_paths[image_path] = dest_path
        return dest_path

    def _get_dest_dir(self, exif_data: dict) -> Path:
        """Get destination directory based on EXIF date."""
        dt = self.strategy.extract_datetime(exif_data)

        if dt is None:
            return self.destination_dir / "Unsorted"
        else:
            try:
                rel_path = dt.strftime(self.pattern)
            except Exception:
                rel_path = dt.strftime(self.fallback_pattern)
            return self.destination_dir / rel_path

    def _resolve_conflict_with_suffix(
        self,
        dest_dir: Path,
        image_path: Path,
        dest_name: str,
        conflicts: list[tuple[Path, Path]],
    ) -> Path:
        """
        Resolve name conflict using distinctive path element.

        Uses "remontée distinctive" algorithm:
        - Compare paths from leaf to root
        - Find first differentiating parent directory
        - Use that as suffix
        """
        suffix = self._find_distinctive_suffix(image_path, dest_name, conflicts)

        if suffix:
            new_name = f"{image_path.stem}_{suffix}{image_path.suffix}"
        else:
            # Fallback: use numeric suffix
            new_name = f"{image_path.stem}_1{image_path.suffix}"

        return dest_dir / new_name

    def _find_distinctive_suffix(
        self,
        current_path: Path,
        dest_name: str,
        conflicts: list[tuple[Path, Path]],
    ) -> str | None:
        """
        Find distinctive suffix by walking up paths until finding difference.

        Args:
            current_path: The source path we're resolving.
            dest_name: The destination filename (same for all conflicts).
            conflicts: List of (source_path, dest_dir) tuples with same dest_name.

        Returns:
            Distinctive element (directory name) that differentiates this path.
        """
        # Get all source paths with this destination name
        conflict_sources = [src for src, _ in conflicts]

        # If only one file with this name, no suffix needed
        if len(conflict_sources) <= 1:
            return None

        # Build list of path parts for each conflict (reversed: leaf to root)
        parts_lists: list[list[str]] = []
        for src in conflict_sources:
            parts = list(src.parent.parts)
            parts.reverse()  # Start from immediate parent
            parts_lists.append(parts)

        # Find the index where paths differ
        # We need to find the first position where NOT all paths have the same value
        current_parts = list(current_path.parent.parts)
        current_parts.reverse()

        # Find the index in parts_lists for our current_path
        current_idx = None
        for i, src in enumerate(conflict_sources):
            if src == current_path:
                current_idx = i
                break

        if current_idx is None:
            return None

        # Compare with other paths
        for depth in range(len(current_parts)):
            values_at_depth = set()
            for parts in parts_lists:
                if depth < len(parts):
                    values_at_depth.add(parts[depth])
                else:
                    values_at_depth.add("")

            # If values differ at this depth, use this level
            if len(values_at_depth) > 1:
                # Return the value for current path at this depth
                if depth < len(current_parts):
                    return current_parts[depth]

        # All paths identical - shouldn't happen with different files
        # Fallback: use first different parent if exists
        for depth in range(len(current_parts)):
            for other_parts in parts_lists:
                if current_idx is not None and parts_lists.index(other_parts) != current_idx:
                    if depth < len(other_parts):
                        if current_parts[depth] != other_parts[depth]:
                            return current_parts[depth]

        return None

    def _ensure_unique(self, dest_path: Path) -> Path:
        """Ensure path doesn't exist on disk (for edge cases)."""
        if not dest_path.exists():
            return dest_path

        # Extract base name (could already have a suffix from distinctive resolution)
        stem = dest_path.stem
        suffix = dest_path.suffix

        # Check if stem already ends with _N pattern
        import re
        match = re.match(r"^(.+)_(\d+)$", stem)
        if match:
            base_stem = match.group(1)
            start_counter = int(match.group(2)) + 1
        else:
            base_stem = stem
            start_counter = 1

        # Find next available number
        counter = start_counter
        while True:
            new_name = f"{base_stem}_{counter}{suffix}"
            new_path = dest_path.parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1
