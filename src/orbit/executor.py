"""
File execution module for ORBIT (copy/move operations).
Supports checksum verification and journal-based resume.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from orbit.errors import ProcessingError
from orbit.journal import Journal


class FileExecutor:
    """Executes file copy/move operations with optional verification."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        journal: Journal | None = None,
        verify: bool = False,
    ):
        self.logger = logger or logging.getLogger("orbit.executor")
        self.journal = journal
        self.verify = verify

    def execute(
        self,
        file_mappings: list[tuple[Path, Path]],
        mode: str = "copy",
        progress_callback=None,
    ) -> tuple[int, int, list[ProcessingError]]:
        """
        Execute file operations.

        Args:
            file_mappings: List of (source, destination) tuples.
            mode: "copy" or "move".
            progress_callback: Optional callback(current, total, filename).

        Returns:
            Tuple of (processed_count, skipped_count, errors).
        """
        if mode not in ("copy", "move"):
            raise ValueError(f"Mode must be 'copy' or 'move', got '{mode}'")

        processed = 0
        skipped = 0
        errors: list[ProcessingError] = []
        total = len(file_mappings)

        # Load journal for resume support
        already_processed: set[str] = set()
        if self.journal:
            self.journal.load()
            already_processed = self.journal.get_processed_sources()

        for i, (source, destination) in enumerate(file_mappings):
            # Skip already processed files (resume support)
            if str(source) in already_processed:
                self.logger.info(f"Skipping (already processed): {source}")
                skipped += 1
                if progress_callback:
                    progress_callback(i + 1, total, str(source))
                continue

            try:
                destination.parent.mkdir(parents=True, exist_ok=True)

                if mode == "copy":
                    shutil.copy2(source, destination)
                    self.logger.info(f"Copied: {source} → {destination}")
                else:
                    shutil.move(str(source), str(destination))
                    self.logger.info(f"Moved: {source} → {destination}")

                # Verify integrity if requested
                if self.verify and destination.exists():
                    if not self._verify_checksum(source, destination):
                        error = ProcessingError(
                            source, "checksum", "Checksum mismatch after copy"
                        )
                        errors.append(error)
                        self.logger.error(f"Checksum mismatch: {source}")
                        destination.unlink(missing_ok=True)
                        skipped += 1
                        if progress_callback:
                            progress_callback(i + 1, total, str(source))
                        continue

                # Record in journal
                if self.journal:
                    self.journal.record(source, destination, mode)

                processed += 1

            except Exception as e:
                errors.append(ProcessingError(source, "execution", str(e)))
                self.logger.error(f"Error processing {source}: {e}")
                skipped += 1

            if progress_callback:
                progress_callback(i + 1, total, str(source))

        return processed, skipped, errors

    @staticmethod
    def compute_checksum(file_path: Path, algorithm: str = "sha256") -> str:
        """Compute file checksum."""
        h = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _verify_checksum(self, source: Path, destination: Path) -> bool:
        """Verify that source and destination files are identical."""
        try:
            return self.compute_checksum(source) == self.compute_checksum(destination)
        except Exception as e:
            self.logger.error(f"Checksum verification failed: {e}")
            return False
