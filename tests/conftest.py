"""Shared test fixtures for ORBIT tests."""

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dirs():
    """Create temporary source and destination directories."""
    temp_dir = tempfile.mkdtemp()
    source_dir = Path(temp_dir) / "source"
    dest_dir = Path(temp_dir) / "destination"
    source_dir.mkdir()
    dest_dir.mkdir()

    yield source_dir, dest_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_files(temp_dirs):
    """Create sample image files (text content, no real EXIF)."""
    source_dir, dest_dir = temp_dirs

    files = []
    for name in ["photo1.jpg", "photo2.jpeg", "image.png", "raw.nef"]:
        path = source_dir / name
        path.write_text("fake image content")
        files.append(path)

    # Non-image file
    (source_dir / "readme.txt").write_text("not an image")

    # Subdirectory with image
    sub = source_dir / "subdir"
    sub.mkdir()
    sub_img = sub / "nested.jpg"
    sub_img.write_text("nested image content")
    files.append(sub_img)

    return files, source_dir, dest_dir
