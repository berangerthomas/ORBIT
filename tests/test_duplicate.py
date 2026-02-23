"""Tests for the duplicate detection module."""

import tempfile
from pathlib import Path

import pytest

from orbit.duplicate import DuplicateDetector, DuplicateGroup, DuplicateResult


@pytest.fixture
def temp_files():
    """Create temporary files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create identical files
        file1 = tmpdir / "photo1.jpg"
        file2 = tmpdir / "photo2.jpg"
        file1.write_bytes(b"identical content")
        file2.write_bytes(b"identical content")

        # Create different file
        file3 = tmpdir / "photo3.jpg"
        file3.write_bytes(b"different content")

        # Create another identical pair
        file4 = tmpdir / "image1.png"
        file5 = tmpdir / "image2.png"
        file4.write_bytes(b"same image data")
        file5.write_bytes(b"same image data")

        yield {
            "tmpdir": tmpdir,
            "identical_pair": [file1, file2],
            "different": file3,
            "another_pair": [file4, file5],
            "all_files": [file1, file2, file3, file4, file5],
        }


class TestDuplicateGroup:
    """Tests for DuplicateGroup dataclass."""

    def test_is_duplicate_true(self):
        """Test is_duplicate returns True for groups with multiple files."""
        group = DuplicateGroup(
            checksum="abc123",
            files=[Path("/a/photo.jpg"), Path("/b/photo.jpg")],
            size=1000,
        )
        assert group.is_duplicate is True
        assert group.count == 2

    def test_is_duplicate_false(self):
        """Test is_duplicate returns False for single-file groups."""
        group = DuplicateGroup(
            checksum="abc123",
            files=[Path("/a/photo.jpg")],
            size=1000,
        )
        assert group.is_duplicate is False
        assert group.count == 1

    def test_wasted_space(self):
        """Test wasted_space calculation."""
        group = DuplicateGroup(
            checksum="abc123",
            files=[Path("/a/photo.jpg"), Path("/b/photo.jpg"), Path("/c/photo.jpg")],
            size=1000,
        )
        # 3 files, 1000 bytes each -> 2 extra copies = 2000 bytes wasted
        assert group.wasted_space == 2000

    def test_representative_and_duplicates(self):
        """Test representative and duplicates properties."""
        files = [Path("/a/photo.jpg"), Path("/b/photo.jpg"), Path("/c/photo.jpg")]
        group = DuplicateGroup(checksum="abc123", files=files, size=1000)

        assert group.representative == files[0]
        assert group.duplicates == files[1:]


class TestDuplicateResult:
    """Tests for DuplicateResult dataclass."""

    def test_empty_result(self):
        """Test empty result properties."""
        result = DuplicateResult()
        assert result.total_duplicates == 0
        assert result.groups_count == 0
        assert result.total_wasted_space == 0

    def test_total_duplicates(self):
        """Test total_duplicates calculation."""
        groups = [
            DuplicateGroup("a", [Path("/1"), Path("/2")], 100),  # 1 duplicate
            DuplicateGroup("b", [Path("/3"), Path("/4"), Path("/5")], 200),  # 2 duplicates
            DuplicateGroup("c", [Path("/6")], 300),  # 0 duplicates
        ]
        result = DuplicateResult(duplicate_groups=groups)
        assert result.total_duplicates == 3  # 1 + 2 + 0

    def test_groups_count(self):
        """Test groups_count only counts groups with duplicates."""
        groups = [
            DuplicateGroup("a", [Path("/1"), Path("/2")], 100),
            DuplicateGroup("b", [Path("/3")], 200),
            DuplicateGroup("c", [Path("/4"), Path("/5")], 300),
        ]
        result = DuplicateResult(duplicate_groups=groups)
        assert result.groups_count == 2  # Only groups with > 1 file

    def test_get_files_to_skip(self):
        """Test get_files_to_skip returns correct files."""
        files_a = [Path("/a/1.jpg"), Path("/a/2.jpg")]
        files_b = [Path("/b/1.jpg"), Path("/b/2.jpg"), Path("/b/3.jpg")]
        groups = [
            DuplicateGroup("a", files_a, 100),
            DuplicateGroup("b", files_b, 200),
        ]
        result = DuplicateResult(duplicate_groups=groups)

        to_skip = result.get_files_to_skip()
        assert len(to_skip) == 3  # 1 from group a, 2 from group b
        assert files_a[0] not in to_skip  # Representative kept
        assert files_a[1] in to_skip
        assert files_b[0] not in to_skip  # Representative kept
        assert files_b[1] in to_skip
        assert files_b[2] in to_skip


class TestDuplicateDetector:
    """Tests for DuplicateDetector class."""

    def test_compute_hash_identical(self, temp_files):
        """Test that identical files produce the same hash."""
        detector = DuplicateDetector()
        hash1 = detector.compute_hash(temp_files["identical_pair"][0])
        hash2 = detector.compute_hash(temp_files["identical_pair"][1])
        assert hash1 == hash2

    def test_compute_hash_different(self, temp_files):
        """Test that different files produce different hashes."""
        detector = DuplicateDetector()
        hash1 = detector.compute_hash(temp_files["identical_pair"][0])
        hash3 = detector.compute_hash(temp_files["different"])
        assert hash1 != hash3

    def test_scan_no_duplicates(self):
        """Test scanning files without duplicates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            for i in range(3):
                (tmpdir / f"file{i}.jpg").write_bytes(f"unique content {i}".encode())

            detector = DuplicateDetector()
            result = detector.scan(list(tmpdir.glob("*.jpg")))

            assert result.total_files_scanned == 3
            assert result.groups_count == 0

    def test_scan_with_duplicates(self, temp_files):
        """Test scanning files with duplicates."""
        detector = DuplicateDetector()
        result = detector.scan(temp_files["all_files"])

        assert result.total_files_scanned == 5
        assert result.groups_count == 2  # Two groups of duplicates

    def test_scan_progress_callback(self, temp_files):
        """Test that progress callback is called."""
        detector = DuplicateDetector()
        calls = []

        def callback(current, total, filename):
            calls.append((current, total, filename))

        result = detector.scan(temp_files["all_files"], progress_callback=callback)

        assert len(calls) == 5
        assert calls[-1][0] == 5  # Last call should be current=total
        assert calls[-1][1] == 5

    def test_export_csv(self, temp_files):
        """Test CSV export functionality."""
        detector = DuplicateDetector()
        result = detector.scan(temp_files["all_files"])

        csv_path = temp_files["tmpdir"] / "duplicates.csv"
        output_path = detector.export_csv(result, csv_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "hash" in content
        assert "filename" in content
        assert "size_bytes" in content
        assert "source_1" in content

    def test_export_csv_only_duplicates(self, temp_files):
        """Test that CSV only contains duplicate groups."""
        detector = DuplicateDetector()
        result = detector.scan(temp_files["all_files"])

        csv_path = temp_files["tmpdir"] / "duplicates.csv"
        detector.export_csv(result, csv_path)

        content = csv_path.read_text()
        lines = content.strip().split("\n")
        # Header + 2 duplicate groups
        assert len(lines) == 3


class TestDuplicateDetectorIntegration:
    """Integration tests for duplicate detection."""

    def test_skip_strategy(self, temp_files):
        """Test that skip strategy returns correct files to skip."""
        detector = DuplicateDetector()
        result = detector.scan(temp_files["all_files"])

        to_skip = result.get_files_to_skip()

        # Should skip 1 from first pair + 1 from second pair = 2 total
        assert len(to_skip) == 2

        # Representatives should not be skipped
        assert temp_files["identical_pair"][0] not in to_skip
        assert temp_files["another_pair"][0] not in to_skip

        # Duplicates should be skipped
        assert temp_files["identical_pair"][1] in to_skip
        assert temp_files["another_pair"][1] in to_skip

        # Different file should not be in skip list
        assert temp_files["different"] not in to_skip

    def test_file_mapping(self, temp_files):
        """Test file mapping for duplicate reference."""
        detector = DuplicateDetector()
        result = detector.scan(temp_files["all_files"])

        mapping = result.get_file_mapping()

        # Each duplicate should map to its representative
        assert temp_files["identical_pair"][1] in mapping
        assert mapping[temp_files["identical_pair"][1]] == temp_files["identical_pair"][0]

        assert temp_files["another_pair"][1] in mapping
        assert mapping[temp_files["another_pair"][1]] == temp_files["another_pair"][0]

        # Representatives should not be in mapping
        assert temp_files["identical_pair"][0] not in mapping
        assert temp_files["another_pair"][0] not in mapping