"""
Operation journal for resume and undo support in ORBIT.
Uses append-only JSONL format for crash-safe recording.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path


class Journal:
    """Records file operations for resume and undo capabilities."""

    def __init__(
        self,
        journal_path: Path,
        logger: logging.Logger | None = None,
    ):
        self.journal_path = journal_path
        self.logger = logger or logging.getLogger("orbit.journal")
        self.entries: list[dict] = []

    def record(self, source: Path, destination: Path, mode: str) -> None:
        """Record a file operation (appends immediately to JSONL file)."""
        entry = {
            "source": str(source),
            "destination": str(destination),
            "mode": mode,
        }
        self.entries.append(entry)

        # Append to journal file immediately for crash recovery
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def load(self) -> None:
        """Load entries from an existing journal file (JSONL format)."""
        self.entries = []
        if self.journal_path.exists():
            with open(self.journal_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            self.logger.warning(
                                f"Skipping malformed journal entry: {line}"
                            )

    def get_processed_sources(self) -> set[str]:
        """Return set of source paths already processed."""
        return {e["source"] for e in self.entries}

    def undo(self) -> list[dict]:
        """
        Reverse all recorded operations.

        - copy  → delete the destination file
        - move  → move the file back from destination to source

        Returns:
            List of undo results with status information.
        """
        results: list[dict] = []

        for entry in reversed(self.entries):
            src = Path(entry["source"])
            dst = Path(entry["destination"])
            mode = entry["mode"]

            try:
                if not dst.exists():
                    results.append(
                        {
                            "entry": entry,
                            "status": "skipped",
                            "reason": "destination not found",
                        }
                    )
                    self.logger.warning(f"Cannot undo: {dst} does not exist")
                    continue

                if mode == "move":
                    src.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
                    self.logger.info(f"Undo move: {dst} → {src}")
                elif mode == "copy":
                    dst.unlink()
                    self.logger.info(f"Undo copy: deleted {dst}")

                results.append({"entry": entry, "status": "undone"})

            except Exception as e:
                results.append({"entry": entry, "status": "error", "reason": str(e)})
                self.logger.error(f"Error undoing operation: {e}")

        # Remove journal file after undo
        if self.journal_path.exists():
            self.journal_path.unlink()
            self.logger.info("Journal file removed after undo")

        return results

    def clear(self) -> None:
        """Remove the journal file and reset entries."""
        if self.journal_path.exists():
            self.journal_path.unlink()
        self.entries = []
