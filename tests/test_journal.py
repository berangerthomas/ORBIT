"""Tests for the Journal module (resume / undo)."""

import json

from orbit.journal import Journal


class TestJournal:
    def test_record_creates_file(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        journal_path = dest_dir / "journal.jsonl"
        journal = Journal(journal_path)

        src = source_dir / "photo.jpg"
        dst = dest_dir / "2023" / "photo.jpg"

        journal.record(src, dst, "copy")

        assert journal_path.exists()
        assert len(journal.entries) == 1

    def test_load_entries(self, temp_dirs):
        _, dest_dir = temp_dirs
        journal_path = dest_dir / "journal.jsonl"

        # Write two entries manually
        entries = [
            {"source": "/a/1.jpg", "destination": "/b/1.jpg", "mode": "copy"},
            {"source": "/a/2.jpg", "destination": "/b/2.jpg", "mode": "move"},
        ]
        with open(journal_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        journal = Journal(journal_path)
        journal.load()

        assert len(journal.entries) == 2
        assert journal.entries[0]["source"] == "/a/1.jpg"

    def test_get_processed_sources(self, temp_dirs):
        _, dest_dir = temp_dirs
        journal_path = dest_dir / "journal.jsonl"

        journal = Journal(journal_path)
        journal.entries = [
            {"source": "/a/1.jpg", "destination": "/b/1.jpg", "mode": "copy"},
            {"source": "/a/2.jpg", "destination": "/b/2.jpg", "mode": "copy"},
        ]

        sources = journal.get_processed_sources()
        assert sources == {"/a/1.jpg", "/a/2.jpg"}

    def test_undo_copy(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        src = source_dir / "photo.jpg"
        dst = dest_dir / "photo.jpg"

        # Simulate a copy
        src.write_text("data")
        dst.write_text("data")

        journal_path = dest_dir / "journal.jsonl"
        with open(journal_path, "w") as f:
            f.write(json.dumps({
                "source": str(src),
                "destination": str(dst),
                "mode": "copy",
            }) + "\n")

        journal = Journal(journal_path)
        journal.load()
        results = journal.undo()

        assert len(results) == 1
        assert results[0]["status"] == "undone"
        assert not dst.exists()  # Copy was deleted
        assert src.exists()  # Source untouched

    def test_undo_move(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        src = source_dir / "photo.jpg"
        dst = dest_dir / "photo.jpg"

        # Simulate a move (file only in destination)
        dst.write_text("data")

        journal_path = dest_dir / "journal.jsonl"
        with open(journal_path, "w") as f:
            f.write(json.dumps({
                "source": str(src),
                "destination": str(dst),
                "mode": "move",
            }) + "\n")

        journal = Journal(journal_path)
        journal.load()
        results = journal.undo()

        assert len(results) == 1
        assert results[0]["status"] == "undone"
        assert src.exists()  # Moved back
        assert not dst.exists()

    def test_undo_removes_journal(self, temp_dirs):
        _, dest_dir = temp_dirs
        journal_path = dest_dir / "journal.jsonl"
        journal_path.write_text("")

        journal = Journal(journal_path)
        journal.load()
        journal.undo()

        assert not journal_path.exists()

    def test_clear(self, temp_dirs):
        _, dest_dir = temp_dirs
        journal_path = dest_dir / "journal.jsonl"
        journal_path.write_text('{"test": true}\n')

        journal = Journal(journal_path)
        journal.entries = [{"test": True}]
        journal.clear()

        assert not journal_path.exists()
        assert journal.entries == []

    def test_load_skips_malformed_lines(self, temp_dirs):
        _, dest_dir = temp_dirs
        journal_path = dest_dir / "journal.jsonl"
        journal_path.write_text(
            '{"source": "/a.jpg", "destination": "/b.jpg", "mode": "copy"}\n'
            'THIS IS NOT JSON\n'
            '{"source": "/c.jpg", "destination": "/d.jpg", "mode": "move"}\n'
        )

        journal = Journal(journal_path)
        journal.load()

        assert len(journal.entries) == 2
