"""
File scanning module for ORBIT.
Uses pathlib.rglob for recursive search and generators for efficiency.
"""

from __future__ import annotations

import logging
from pathlib import Path


class FileScanner:
    """Discovers image files in source directories."""

    SUPPORTED_EXTENSIONS: set[str] = {
        ".jpg",
        ".jpeg",
        ".png",
        ".tiff",
        ".nef",
        ".cr2",
        ".arw",
        ".dng",
        ".raf",
        ".raw",
        ".heic",
        ".heif",
    }

    def __init__(
        self,
        source_dirs: list[Path],
        recursive: bool = False,
        logger: logging.Logger | None = None,
    ):
        self.source_dirs = source_dirs
        self.recursive = recursive
        self.logger = logger or logging.getLogger("orbit.scanner")
        self.missing_dirs: list[Path] = []

    def scan(self) -> list[Path]:
        """
        Scan source directories for supported image files.

        Returns:
            List of Paths to discovered image files.
        """
        self.missing_dirs = []
        files: list[Path] = []

        for source_dir in self.source_dirs:
            if not source_dir.exists():
                self.logger.error(f"Source directory does not exist: {source_dir}")
                self.missing_dirs.append(source_dir)
                continue

            if self.recursive:
                files.extend(
                    p
                    for p in source_dir.rglob("*")
                    if p.is_file() and self._is_supported(p)
                )
            else:
                files.extend(
                    p
                    for p in source_dir.iterdir()
                    if p.is_file() and self._is_supported(p)
                )

        self.logger.info(
            f"Found {len(files)} image files across "
            f"{len(self.source_dirs)} source directories"
        )
        return files

    @classmethod
    def _is_supported(cls, file_path: Path) -> bool:
        """Check if a file has a supported image extension."""
        return file_path.suffix.lower() in cls.SUPPORTED_EXTENSIONS
