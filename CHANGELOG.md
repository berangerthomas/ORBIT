# Changelog

## [0.1.0] - 2026-02-23

### Added

- Photo organization based on EXIF metadata (DateTimeOriginal, Image DateTime, file timestamp)
- Three extraction modes: `strict`, `normal`, `flexible`
- Customizable directory structure using `strftime` patterns
- Support for JPEG, PNG, TIFF, RAW (NEF, CR2, ARW, DNG, RAF), HEIC/HEIF
- Dry-run simulation with HTML report generation
- Copy and move operations with checksum verification (`--verify`)
- Automatic name conflict resolution using distinctive path elements
- Duplicate detection by SHA-256 content hash (`--detect-duplicates`)
- Duplicate strategies: `all` (copy all with renaming), `skip` (keep first only)
- CSV export for duplicate reports
- Parallel EXIF extraction via `--workers`
- Resume interrupted operations (`--resume`) via JSONL journal
- Undo last operation (`--undo`)
- Recursive and flat directory scanning
- Multiple source directories support
- Progress bar and colored CLI output via Rich

### Architecture

- `core.py`: Orbit facade orchestrating all components
- `scanner.py`: File discovery using pathlib.rglob
- `exif.py`: EXIF extraction with datetime strategies
- `path_generator.py`: Destination path mapping with conflict resolution
- `executor.py`: File copy/move with checksum support
- `journal.py`: JSONL journal for crash recovery
- `reporter.py`: HTML report generation with tabs
- `duplicate.py`: Duplicate detection using SHA-256
- `errors.py`: Typed error and result dataclasses
- `cli.py`: Command-line interface with argparse and Rich