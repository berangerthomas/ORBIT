"""
Error types and result dataclasses for ORBIT.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orbit.duplicate import DuplicateResult


@dataclass
class ProcessingError:
    """Represents an error that occurred during file processing."""

    file_path: Path
    error_type: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        return f"[{self.error_type}] {self.file_path}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "file_path": str(self.file_path),
            "error_type": self.error_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessingError":
        return cls(
            file_path=Path(data["file_path"]),
            error_type=data["error_type"],
            message=data["message"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class OrbitResult:
    """Result of an ORBIT operation (simulation or execution)."""

    total_files_found: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    created_directories: list[str] = field(default_factory=list)
    errors: list[ProcessingError] = field(default_factory=list)
    file_mappings: list[tuple[Path, Path]] = field(default_factory=list)
    mode: str | None = None
    html_report_path: str | None = None
    duplicate_result: "DuplicateResult | None" = None
    duplicate_csv_path: str | None = None
    duplicate_strategy: str | None = None  # "all" or "skip"

    # Size tracking
    total_size: int = 0  # Total size of all files found (bytes)
    processed_size: int = 0  # Size of processed files (bytes)
    skipped_size: int = 0  # Size of skipped files (bytes)
    duplicate_size: int = 0  # Size of duplicate files (bytes)

    # Trace file path for report regeneration
    trace_path: str | None = None

    @property
    def created_directories_count(self) -> int:
        return len(self.created_directories)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_duplicates(self) -> bool:
        """True if duplicates were detected."""
        return self.duplicate_result is not None and self.duplicate_result.groups_count > 0

    @property
    def duplicate_files_count(self) -> int:
        """Number of duplicate files found."""
        if self.duplicate_result:
            return self.duplicate_result.total_duplicates
        return 0

    @property
    def total_size_gb(self) -> float:
        """Total size in GB."""
        return self.total_size / (1024**3)

    @property
    def processed_size_gb(self) -> float:
        """Processed size in GB."""
        return self.processed_size / (1024**3)

    @property
    def skipped_size_gb(self) -> float:
        """Skipped size in GB."""
        return self.skipped_size / (1024**3)

    @property
    def duplicate_size_gb(self) -> float:
        """Duplicate size in GB."""
        return self.duplicate_size / (1024**3)

    def to_dict(self) -> dict:
        """Serialize result to dictionary for JSON export."""
        return {
            "total_files_found": self.total_files_found,
            "processed_files": self.processed_files,
            "skipped_files": self.skipped_files,
            "created_directories": self.created_directories,
            "errors": [e.to_dict() for e in self.errors],
            "file_mappings": [[str(src), str(dst)] for src, dst in self.file_mappings],
            "mode": self.mode,
            "duplicate_strategy": self.duplicate_strategy,
            "total_size": self.total_size,
            "processed_size": self.processed_size,
            "skipped_size": self.skipped_size,
            "duplicate_size": self.duplicate_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrbitResult":
        """Deserialize result from dictionary."""
        return cls(
            total_files_found=data.get("total_files_found", 0),
            processed_files=data.get("processed_files", 0),
            skipped_files=data.get("skipped_files", 0),
            created_directories=data.get("created_directories", []),
            errors=[ProcessingError.from_dict(e) for e in data.get("errors", [])],
            file_mappings=[
                (Path(src), Path(dst)) for src, dst in data.get("file_mappings", [])
            ],
            mode=data.get("mode"),
            duplicate_strategy=data.get("duplicate_strategy"),
            total_size=data.get("total_size", 0),
            processed_size=data.get("processed_size", 0),
            skipped_size=data.get("skipped_size", 0),
            duplicate_size=data.get("duplicate_size", 0),
        )

    def save_trace(self, path: Path) -> Path:
        """Save result to JSON trace file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        self.trace_path = str(path)
        return path

    @classmethod
    def load_trace(cls, path: Path) -> "OrbitResult":
        """Load result from JSON trace file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        result = cls.from_dict(data)
        result.trace_path = str(path)
        return result