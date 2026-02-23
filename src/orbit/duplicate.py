"""
Duplicate detection module for ORBIT.
Detects perfect duplicates using file hash (SHA-256).
"""

from __future__ import annotations

import csv
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class DuplicateGroup:
    """Represents a group of identical files (same hash)."""

    checksum: str
    files: list[Path]
    size: int

    @property
    def count(self) -> int:
        """Number of files in this group."""
        return len(self.files)

    @property
    def is_duplicate(self) -> bool:
        """True if more than one file shares this hash."""
        return self.count > 1

    @property
    def representative(self) -> Path:
        """Return the first file as representative (kept with 'skip' strategy)."""
        return self.files[0]

    @property
    def duplicates(self) -> list[Path]:
        """Return all files except the representative."""
        return self.files[1:]

    @property
    def wasted_space(self) -> int:
        """Space that would be saved by keeping only one copy."""
        return self.size * (self.count - 1)


@dataclass
class DuplicateResult:
    """Result of duplicate detection analysis."""

    total_files_scanned: int = 0
    duplicate_groups: list[DuplicateGroup] = field(default_factory=list)
    csv_path: str | None = None

    @property
    def total_duplicates(self) -> int:
        """Total number of duplicate files (excluding representatives)."""
        return sum(g.count - 1 for g in self.duplicate_groups if g.is_duplicate)

    @property
    def total_wasted_space(self) -> int:
        """Total space that would be saved with 'skip' strategy."""
        return sum(g.wasted_space for g in self.duplicate_groups if g.is_duplicate)

    @property
    def groups_count(self) -> int:
        """Number of duplicate groups found."""
        return len([g for g in self.duplicate_groups if g.is_duplicate])

    def get_files_to_skip(self) -> set[Path]:
        """Return set of files to skip with 'skip' strategy."""
        to_skip: set[Path] = set()
        for group in self.duplicate_groups:
            if group.is_duplicate:
                # Keep only the representative, skip the rest
                to_skip.update(group.duplicates)
        return to_skip

    def get_file_mapping(self) -> dict[Path, Path]:
        """Return mapping: duplicate -> representative (for reference)."""
        mapping: dict[Path, Path] = {}
        for group in self.duplicate_groups:
            if group.is_duplicate:
                for dup in group.duplicates:
                    mapping[dup] = group.representative
        return mapping


class DuplicateDetector:
    """Detects perfect duplicate files using SHA-256 hash."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        buffer_size: int = 65536,
    ):
        self.logger = logger or logging.getLogger("orbit.duplicate")
        self.buffer_size = buffer_size

    def compute_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(self.buffer_size), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            self.logger.error(f"Error computing hash for {file_path}: {e}")
            raise

    def scan(
        self,
        files: list[Path],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> DuplicateResult:
        """
        Scan files and detect duplicates.

        Args:
            files: List of file paths to scan.
            progress_callback: Optional callback(current, total, filename).

        Returns:
            DuplicateResult with all duplicate groups.
        """
        self.logger.info(f"Scanning {len(files)} files for duplicates...")

        # Group files by hash
        hash_groups: dict[str, list[Path]] = {}
        file_sizes: dict[str, int] = {}
        total = len(files)

        for i, file_path in enumerate(files):
            try:
                file_hash = self.compute_hash(file_path)

                if file_hash not in hash_groups:
                    hash_groups[file_hash] = []
                    file_sizes[file_hash] = file_path.stat().st_size

                hash_groups[file_hash].append(file_path)

            except Exception as e:
                self.logger.warning(f"Skipping file {file_path}: {e}")

            if progress_callback:
                progress_callback(i + 1, total, str(file_path))

        # Build duplicate groups (only those with duplicates)
        duplicate_groups: list[DuplicateGroup] = []
        for file_hash, paths in hash_groups.items():
            group = DuplicateGroup(
                checksum=file_hash,
                files=paths,
                size=file_sizes[file_hash],
            )
            duplicate_groups.append(group)

        result = DuplicateResult(
            total_files_scanned=len(files),
            duplicate_groups=duplicate_groups,
        )

        self.logger.info(
            f"Found {result.groups_count} duplicate groups "
            f"({result.total_duplicates} duplicate files)"
        )

        return result

    def export_csv(
        self,
        result: DuplicateResult,
        output_path: Path,
    ) -> Path:
        """
        Export duplicate report to CSV.

        Args:
            result: DuplicateResult from scan().
            output_path: Path to output CSV file.

        Returns:
            Path to the created CSV file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Find max number of sources in any group for column count
        max_sources = max((g.count for g in result.duplicate_groups), default=0)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header
            header = ["hash", "filename", "size_bytes"] + [
                f"source_{i+1}" for i in range(max_sources)
            ]
            writer.writerow(header)

            # Rows (only groups with duplicates)
            for group in result.duplicate_groups:
                if not group.is_duplicate:
                    continue

                row = [
                    group.checksum,
                    group.representative.name,
                    group.size,
                ]
                # Add all source paths
                for file_path in group.files:
                    row.append(str(file_path))
                # Pad with empty strings if needed
                while len(row) < len(header):
                    row.append("")

                writer.writerow(row)

        result.csv_path = str(output_path)
        self.logger.info(f"Duplicates CSV exported to {output_path}")

        return output_path