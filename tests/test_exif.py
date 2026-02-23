"""Tests for the ExifExtractor and DatetimeStrategy modules."""

from datetime import datetime

from orbit.exif import (
    ExifExtractor,
    FlexibleStrategy,
    NormalStrategy,
    StrictStrategy,
)


class TestStrictStrategy:
    def test_returns_original_when_present(self):
        dt = datetime(2023, 7, 15, 14, 30)
        data = {"exif_datetime_original": dt, "image_datetime": datetime.now()}
        assert StrictStrategy().extract_datetime(data) == dt

    def test_returns_none_without_original(self):
        data = {"image_datetime": datetime.now(), "file_datetime": datetime.now()}
        assert StrictStrategy().extract_datetime(data) is None

    def test_returns_none_for_empty_data(self):
        assert StrictStrategy().extract_datetime({}) is None


class TestNormalStrategy:
    def test_prefers_original(self):
        dt_orig = datetime(2023, 7, 15)
        dt_img = datetime(2023, 8, 1)
        data = {"exif_datetime_original": dt_orig, "image_datetime": dt_img}
        assert NormalStrategy().extract_datetime(data) == dt_orig

    def test_falls_back_to_image_datetime(self):
        dt_img = datetime(2023, 8, 1)
        data = {"image_datetime": dt_img}
        assert NormalStrategy().extract_datetime(data) == dt_img

    def test_ignores_file_datetime(self):
        data = {"file_datetime": datetime.now()}
        assert NormalStrategy().extract_datetime(data) is None


class TestFlexibleStrategy:
    def test_prefers_exif_original(self):
        dt_orig = datetime(2023, 7, 15)
        dt_file = datetime(2023, 9, 1)
        data = {"exif_datetime_original": dt_orig, "file_datetime": dt_file}
        assert FlexibleStrategy().extract_datetime(data) == dt_orig

    def test_falls_back_to_image_datetime(self):
        dt_img = datetime(2023, 8, 1)
        dt_file = datetime(2023, 9, 1)
        data = {"image_datetime": dt_img, "file_datetime": dt_file}
        assert FlexibleStrategy().extract_datetime(data) == dt_img

    def test_uses_file_datetime_as_last_resort(self):
        dt_file = datetime(2023, 9, 1)
        data = {"file_datetime": dt_file}
        assert FlexibleStrategy().extract_datetime(data) == dt_file

    def test_returns_none_for_empty_data(self):
        assert FlexibleStrategy().extract_datetime({}) is None


class TestExifExtractor:
    def test_extract_from_non_image_file(self, sample_files):
        """Extracting from a fake file should still return file_datetime."""
        files, _, _ = sample_files
        extractor = ExifExtractor()
        result = extractor.extract(files[0])

        assert "file_datetime" in result
        assert isinstance(result["file_datetime"], datetime)

    def test_extract_from_missing_file(self, temp_dirs):
        """Extracting from a nonexistent file returns empty dict quietly."""
        source_dir, _ = temp_dirs
        extractor = ExifExtractor()
        result = extractor.extract(source_dir / "nonexistent.jpg")

        assert isinstance(result, dict)
        assert "exif_datetime_original" not in result

    def test_extract_always_returns_dict(self, sample_files):
        """Extractor always returns a dict, never raises."""
        files, _, _ = sample_files
        extractor = ExifExtractor()

        for f in files:
            result = extractor.extract(f)
            assert isinstance(result, dict)
