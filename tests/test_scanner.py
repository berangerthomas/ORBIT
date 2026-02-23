"""Tests for the FileScanner module."""

from pathlib import Path

from orbit.scanner import FileScanner


class TestFileScanner:
    def test_scan_finds_images(self, sample_files):
        _, source_dir, _ = sample_files
        scanner = FileScanner([source_dir], recursive=False)
        found = scanner.scan()

        # Should find 4 images in root (photo1.jpg, photo2.jpeg, image.png, raw.nef)
        assert len(found) == 4
        assert all(
            f.suffix.lower() in FileScanner.SUPPORTED_EXTENSIONS for f in found
        )

    def test_scan_recursive(self, sample_files):
        _, source_dir, _ = sample_files
        scanner = FileScanner([source_dir], recursive=True)
        found = scanner.scan()

        # Should find 5 images (4 in root + 1 in subdir)
        assert len(found) == 5

    def test_scan_excludes_non_images(self, sample_files):
        _, source_dir, _ = sample_files
        scanner = FileScanner([source_dir], recursive=True)
        found = scanner.scan()

        names = [f.name for f in found]
        assert "readme.txt" not in names

    def test_scan_missing_directory(self, temp_dirs):
        source_dir, _ = temp_dirs
        fake_dir = source_dir / "nonexistent"
        scanner = FileScanner([fake_dir])
        found = scanner.scan()

        assert len(found) == 0
        assert fake_dir in scanner.missing_dirs

    def test_scan_multiple_sources(self, temp_dirs):
        source_dir, _ = temp_dirs
        dir_a = source_dir / "a"
        dir_b = source_dir / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "img1.jpg").write_text("test")
        (dir_b / "img2.png").write_text("test")

        scanner = FileScanner([dir_a, dir_b])
        found = scanner.scan()

        assert len(found) == 2

    def test_is_supported(self):
        assert FileScanner._is_supported(Path("photo.jpg"))
        assert FileScanner._is_supported(Path("photo.JPEG"))
        assert FileScanner._is_supported(Path("raw.NEF"))
        assert not FileScanner._is_supported(Path("doc.pdf"))
        assert not FileScanner._is_supported(Path("video.mp4"))

    def test_scan_empty_directory(self, temp_dirs):
        source_dir, _ = temp_dirs
        scanner = FileScanner([source_dir])
        found = scanner.scan()

        assert len(found) == 0
        assert len(scanner.missing_dirs) == 0
