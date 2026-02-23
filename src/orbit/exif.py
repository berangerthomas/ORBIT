"""
EXIF metadata extraction and datetime strategy for ORBIT.

Strategies:
  - StrictStrategy:   only EXIF DateTimeOriginal
  - NormalStrategy:   EXIF DateTimeOriginal, then Image DateTime
  - FlexibleStrategy: any available datetime including file modification time
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import exifread


# ---------------------------------------------------------------------------
# Datetime extraction strategies
# ---------------------------------------------------------------------------


class DatetimeStrategy(ABC):
    """Abstract strategy for selecting a datetime from EXIF data."""

    @abstractmethod
    def extract_datetime(self, exif_data: dict) -> datetime | None:
        """Return the most appropriate datetime, or None."""
        ...


class StrictStrategy(DatetimeStrategy):
    """Only uses EXIF DateTimeOriginal."""

    def extract_datetime(self, exif_data: dict) -> datetime | None:
        return exif_data.get("exif_datetime_original")


class NormalStrategy(DatetimeStrategy):
    """Uses EXIF DateTimeOriginal, falls back to Image DateTime."""

    def extract_datetime(self, exif_data: dict) -> datetime | None:
        return exif_data.get("exif_datetime_original") or exif_data.get(
            "image_datetime"
        )


class FlexibleStrategy(DatetimeStrategy):
    """Uses any available datetime source, including file modification time."""

    def extract_datetime(self, exif_data: dict) -> datetime | None:
        return (
            exif_data.get("exif_datetime_original")
            or exif_data.get("image_datetime")
            or exif_data.get("file_datetime")
        )


STRATEGIES: dict[str, type[DatetimeStrategy]] = {
    "strict": StrictStrategy,
    "normal": NormalStrategy,
    "flexible": FlexibleStrategy,
}


# ---------------------------------------------------------------------------
# EXIF extractor
# ---------------------------------------------------------------------------


class ExifExtractor:
    """Extracts datetime-related EXIF metadata from image files."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("orbit.exif")

    def extract(self, image_path: Path) -> dict:
        """
        Extract datetime-related EXIF data from an image.

        Returns a dict with possible keys:
            - exif_datetime_original: datetime from EXIF DateTimeOriginal
            - image_datetime:         datetime from Image DateTime
            - file_datetime:          datetime from file modification time
        """
        exif_data: dict = {}

        try:
            with open(image_path, "rb") as f:
                tags = exifread.process_file(
                    f, details=False, stop_tag="Image DateTime"
                )

            if "EXIF DateTimeOriginal" in tags:
                try:
                    exif_data["exif_datetime_original"] = datetime.strptime(
                        str(tags["EXIF DateTimeOriginal"]), "%Y:%m:%d %H:%M:%S"
                    )
                except ValueError:
                    self.logger.warning(
                        f"Non-standard EXIF DateTimeOriginal in {image_path}: "
                        f"{tags['EXIF DateTimeOriginal']}"
                    )

            if "Image DateTime" in tags:
                try:
                    exif_data["image_datetime"] = datetime.strptime(
                        str(tags["Image DateTime"]), "%Y:%m:%d %H:%M:%S"
                    )
                except ValueError:
                    self.logger.warning(
                        f"Non-standard Image DateTime in {image_path}: "
                        f"{tags['Image DateTime']}"
                    )

        except Exception as e:
            self.logger.error(f"Error extracting EXIF from {image_path}: {e}")

        # Always try to get file datetime as ultimate fallback
        try:
            exif_data["file_datetime"] = datetime.fromtimestamp(
                image_path.stat().st_mtime
            )
        except OSError as e:
            self.logger.error(f"Cannot read file timestamp for {image_path}: {e}")

        return exif_data
