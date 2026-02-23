"""Tests for the PathGenerator module."""

from datetime import datetime
from pathlib import Path

from orbit.exif import FlexibleStrategy, NormalStrategy, StrictStrategy
from orbit.path_generator import PathGenerator


class TestPathGenerator:
    def test_valid_pattern(self, temp_dirs):
        _, dest_dir = temp_dirs
        gen = PathGenerator(dest_dir, "%Y/%m/%d", NormalStrategy())
        assert gen is not None

    def test_generate_with_date(self, temp_dirs):
        _, dest_dir = temp_dirs
        gen = PathGenerator(dest_dir, "%Y/%m", NormalStrategy())

        exif = {"exif_datetime_original": datetime(2023, 7, 15)}
        result = gen.generate(Path("photo.jpg"), exif)

        expected = dest_dir / "2023" / "07" / "photo.jpg"
        assert result == expected

    def test_generate_unsorted_when_no_date(self, temp_dirs):
        _, dest_dir = temp_dirs
        gen = PathGenerator(dest_dir, "%Y/%m", StrictStrategy())

        exif = {"file_datetime": datetime.now()}  # No EXIF date
        result = gen.generate(Path("photo.jpg"), exif)

        assert "Unsorted" in result.parts

    def test_generate_flexible_uses_file_date(self, temp_dirs):
        _, dest_dir = temp_dirs
        gen = PathGenerator(dest_dir, "%Y/%m", FlexibleStrategy())

        exif = {"file_datetime": datetime(2024, 1, 15)}
        result = gen.generate(Path("photo.jpg"), exif)

        expected = dest_dir / "2024" / "01" / "photo.jpg"
        assert result == expected

    def test_conflict_resolution(self, temp_dirs):
        _, dest_dir = temp_dirs
        gen = PathGenerator(dest_dir, "test", NormalStrategy())

        # Create a conflicting file
        (dest_dir / "test").mkdir(parents=True)
        (dest_dir / "test" / "photo.jpg").write_text("existing")

        exif = {"exif_datetime_original": datetime(2023, 7, 15)}
        result = gen.generate(Path("photo.jpg"), exif)

        assert result.name == "photo_1.jpg"

    def test_multiple_conflicts(self, temp_dirs):
        _, dest_dir = temp_dirs
        gen = PathGenerator(dest_dir, "test", NormalStrategy())

        test_dir = dest_dir / "test"
        test_dir.mkdir(parents=True)
        (test_dir / "photo.jpg").write_text("existing")
        (test_dir / "photo_1.jpg").write_text("existing")
        (test_dir / "photo_2.jpg").write_text("existing")

        exif = {"exif_datetime_original": datetime(2023, 7, 15)}
        result = gen.generate(Path("photo.jpg"), exif)

        assert result.name == "photo_3.jpg"

    def test_preserves_extension(self, temp_dirs):
        _, dest_dir = temp_dirs
        gen = PathGenerator(dest_dir, "%Y", FlexibleStrategy())

        exif = {"file_datetime": datetime(2023, 1, 1)}
        result = gen.generate(Path("image.nef"), exif)

        assert result.suffix == ".nef"

    def test_unsorted_for_empty_exif(self, temp_dirs):
        _, dest_dir = temp_dirs
        gen = PathGenerator(dest_dir, "%Y/%m", StrictStrategy())

        result = gen.generate(Path("photo.jpg"), {})

        assert "Unsorted" in result.parts
        assert result.name == "photo.jpg"
