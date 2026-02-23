"""Tests for the FileExecutor module."""

import pytest

from orbit.executor import FileExecutor
from orbit.journal import Journal


class TestFileExecutor:
    def test_copy_files(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        src_file = source_dir / "photo.jpg"
        src_file.write_text("image data")
        dst_file = dest_dir / "organized" / "photo.jpg"

        executor = FileExecutor()
        processed, skipped, errors = executor.execute(
            [(src_file, dst_file)], mode="copy"
        )

        assert processed == 1
        assert skipped == 0
        assert len(errors) == 0
        assert src_file.exists()  # Source preserved
        assert dst_file.exists()  # Destination created
        assert dst_file.read_text() == "image data"

    def test_move_files(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        src_file = source_dir / "photo.jpg"
        src_file.write_text("image data")
        dst_file = dest_dir / "organized" / "photo.jpg"

        executor = FileExecutor()
        processed, skipped, errors = executor.execute(
            [(src_file, dst_file)], mode="move"
        )

        assert processed == 1
        assert not src_file.exists()  # Source removed
        assert dst_file.exists()

    def test_invalid_mode_raises(self):
        executor = FileExecutor()
        with pytest.raises(ValueError, match="'copy' or 'move'"):
            executor.execute([], mode="delete")

    def test_creates_parent_directories(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        src_file = source_dir / "photo.jpg"
        src_file.write_text("data")
        dst_file = dest_dir / "a" / "b" / "c" / "photo.jpg"

        executor = FileExecutor()
        processed, _, _ = executor.execute([(src_file, dst_file)], mode="copy")

        assert processed == 1
        assert dst_file.exists()

    def test_checksum_verification(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        src_file = source_dir / "photo.jpg"
        src_file.write_bytes(b"real image data bytes")
        dst_file = dest_dir / "photo.jpg"

        executor = FileExecutor(verify=True)
        processed, skipped, errors = executor.execute(
            [(src_file, dst_file)], mode="copy"
        )

        assert processed == 1
        assert len(errors) == 0

    def test_compute_checksum(self, temp_dirs):
        source_dir, _ = temp_dirs
        f = source_dir / "test.bin"
        f.write_bytes(b"hello world")

        checksum = FileExecutor.compute_checksum(f)
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA-256 hex digest

    def test_multiple_files(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        mappings = []
        for i in range(5):
            src = source_dir / f"photo_{i}.jpg"
            src.write_text(f"content {i}")
            dst = dest_dir / "out" / f"photo_{i}.jpg"
            mappings.append((src, dst))

        executor = FileExecutor()
        processed, skipped, errors = executor.execute(mappings, mode="copy")

        assert processed == 5
        assert skipped == 0
        assert len(errors) == 0

    def test_progress_callback(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        src_file = source_dir / "photo.jpg"
        src_file.write_text("data")
        dst_file = dest_dir / "photo.jpg"

        calls = []

        def callback(current, total, filename):
            calls.append((current, total, filename))

        executor = FileExecutor()
        executor.execute([(src_file, dst_file)], mode="copy", progress_callback=callback)

        assert len(calls) == 1
        assert calls[0] == (1, 1, str(src_file))

    def test_journal_recording(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        src_file = source_dir / "photo.jpg"
        src_file.write_text("data")
        dst_file = dest_dir / "photo.jpg"
        journal_path = dest_dir / "test_journal.jsonl"

        journal = Journal(journal_path)
        executor = FileExecutor(journal=journal)
        executor.execute([(src_file, dst_file)], mode="copy")

        assert journal_path.exists()
        assert len(journal.entries) == 1
        assert journal.entries[0]["mode"] == "copy"
