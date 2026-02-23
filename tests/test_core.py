"""Integration tests for the Orbit facade."""

import pytest

from orbit.core import Orbit


class TestOrbitInit:
    def test_valid_initialization(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
        )
        assert organizer.mode == "normal"
        assert organizer.recursive is False

    def test_invalid_mode_raises(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        with pytest.raises(ValueError, match="Mode must be"):
            Orbit(
                source_dirs=[str(source_dir)],
                destination_dir=str(dest_dir),
                mode="invalid",
            )

    def test_same_source_destination_raises(self, temp_dirs):
        source_dir, _ = temp_dirs
        with pytest.raises(ValueError, match="same directory"):
            Orbit(
                source_dirs=[str(source_dir)],
                destination_dir=str(source_dir),
            )

    def test_destination_inside_source_raises(self, temp_dirs):
        source_dir, _ = temp_dirs
        nested_dest = source_dir / "output"
        nested_dest.mkdir()
        with pytest.raises(ValueError, match="infinite recursion"):
            Orbit(
                source_dirs=[str(source_dir)],
                destination_dir=str(nested_dest),
                recursive=True,
            )

    def test_all_modes_accepted(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        for mode in ("strict", "normal", "flexible"):
            org = Orbit(
                source_dirs=[str(source_dir)],
                destination_dir=str(dest_dir),
                mode=mode,
            )
            assert org.mode == mode


class TestOrbitSimulation:
    def test_simulate_empty_source(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
        )
        result = organizer.simulate()
        assert result.total_files_found == 0
        assert result.processed_files == 0

    def test_simulate_with_files(self, sample_files):
        _, source_dir, dest_dir = sample_files
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
            mode="flexible",
        )
        result = organizer.simulate()

        # Non-recursive: 4 files in root
        assert result.total_files_found == 4
        assert result.processed_files == 4

    def test_simulate_recursive(self, sample_files):
        _, source_dir, dest_dir = sample_files
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
            recursive=True,
            mode="flexible",
        )
        result = organizer.simulate()

        # Recursive: 4 in root + 1 in subdir
        assert result.total_files_found == 5

    def test_simulate_with_report(self, sample_files):
        _, source_dir, dest_dir = sample_files
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
            mode="flexible",
        )
        result = organizer.simulate(report=True)

        assert result.html_report_path is not None
        from pathlib import Path

        assert Path(result.html_report_path).exists()

    def test_simulate_progress_callback(self, sample_files):
        _, source_dir, dest_dir = sample_files
        calls = []

        def callback(current, total, filename):
            calls.append((current, total))

        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
            mode="flexible",
        )
        organizer.simulate(progress_callback=callback)

        assert len(calls) == 4
        assert calls[-1] == (4, 4)

    def test_simulate_missing_source(self, temp_dirs):
        _, dest_dir = temp_dirs
        organizer = Orbit(
            source_dirs=["/nonexistent/path"],
            destination_dir=str(dest_dir),
        )
        result = organizer.simulate()

        assert result.total_files_found == 0
        assert result.has_errors


class TestOrbitExecution:
    def test_execute_copy(self, sample_files):
        _, source_dir, dest_dir = sample_files
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
            pattern="test",
            mode="flexible",
        )
        result = organizer.execute(mode="copy")

        assert result.processed_files == 4
        # Source files still exist
        assert len(list(source_dir.glob("*.jpg"))) > 0

    def test_execute_move(self, sample_files):
        _, source_dir, dest_dir = sample_files
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
            pattern="test",
            mode="flexible",
        )
        result = organizer.execute(mode="move")

        assert result.processed_files == 4
        # Image files should be moved
        remaining_images = [
            f
            for f in source_dir.iterdir()
            if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".nef"}
        ]
        assert len(remaining_images) == 0

    def test_execute_invalid_mode_raises(self, temp_dirs):
        source_dir, dest_dir = temp_dirs
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
        )
        with pytest.raises(ValueError):
            organizer.execute(mode="delete")

    def test_execute_with_workers(self, sample_files):
        _, source_dir, dest_dir = sample_files
        organizer = Orbit(
            source_dirs=[str(source_dir)],
            destination_dir=str(dest_dir),
            pattern="test",
            mode="flexible",
            workers=2,
        )
        result = organizer.execute(mode="copy")

        assert result.processed_files == 4
