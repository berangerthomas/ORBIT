# ORBIT

<img src="src/orbit/assets/image/logo.jpg" alt="ORBIT Logo" width="200"/>

**O**rganized **R**epositories **B**ased on **I**mages **T**iming — Organize photos into a structured directory tree based on their EXIF metadata.

[![Python](https://img.shields.io/pypi/pyversions/orbit-photos.svg)](https://pypi.org/project/orbit-photos/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](licence.md)

## Features

- Sort photos by date using EXIF metadata (DateTimeOriginal, Image DateTime, or file timestamp)
- Three extraction modes: `strict`, `normal`, `flexible`
- Customizable directory structure using `strftime` patterns
- Supports JPEG, PNG, TIFF, RAW (NEF, CR2, ARW, DNG, RAF), and HEIC/HEIF
- Dry-run simulation with optional HTML report
- Copy or move operations with checksum verification (`--verify`)
- Automatic name conflict resolution using distinctive path elements
- Duplicate detection by content hash (`--detect-duplicates`)
- File size tracking in reports (total, processed, skipped, duplicates)
- Automatic trace file for report regeneration (`--generate-report`)
- Parallel EXIF extraction via `--workers`
- Resume interrupted operations (`--resume`) via crash-safe JSONL journal
- Undo last operation (`--undo`)
- Recursive or flat directory scanning

## Installation

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv add orbit-photos
```

Or install from source:

```bash
git clone https://github.com/berangerthomas/ORBIT.git
cd ORBIT
uv sync
```

## Usage

### Command Line

```bash
# Dry-run simulation (default — no files are copied or moved)
orbit -s /path/to/photos -d /organized/photos

# Simulation with HTML report
orbit -s /path/to/photos -d /organized/photos --report

# Copy photos into organized structure
orbit -s /path/to/photos -d /organized/photos -m copy

# Move photos (recursive scan)
orbit -s /path/to/photos -d /organized/photos -m move -r

# Custom directory pattern
orbit -s /path/to/photos -d /organized/photos -m copy -p "%Y/%B/%d"

# Multiple source directories with parallel extraction
orbit -s /photos1 /photos2 -d /organized -m copy -r -w 8

# Strict EXIF mode + checksum verification
orbit -s /path/to/photos -d /organized/photos -m copy -e strict --verify

# Detect duplicates, keep only first occurrence
orbit -s /path/to/photos -d /organized/photos -m copy --detect-duplicates skip

# Detect duplicates, copy all with renaming
orbit -s /path/to/photos -d /organized/photos -m copy --detect-duplicates all

# Resume an interrupted operation
orbit -s /path/to/photos -d /organized/photos -m copy --resume

# Undo the last operation
orbit -s /path/to/photos -d /organized/photos --undo

# Regenerate HTML report from saved trace (no rescan)
orbit -d /organized/photos --generate-report

# Verbose logging
orbit -s /path/to/photos -d /organized/photos -m copy -v
```

### As a Python Module

```python
from orbit import Orbit

organizer = Orbit(
    source_dirs=["/path/to/photos"],
    destination_dir="/organized/photos",
    pattern="%Y/%m/%d",
    recursive=True,
    mode="flexible",
    workers=4,
    verbose=True,
)

# Dry-run simulation
result = organizer.simulate()
print(f"Files found: {result.total_files_found}")
print(f"Directories to create: {result.created_directories_count}")
print(f"Total size: {result.total_size_gb:.2f} GB")

# Simulation with HTML report
result = organizer.simulate(report=True)
print(f"Report: {result.html_report_path}")
print(f"Trace: {result.trace_path}")

# Execute copy or move
result = organizer.execute(mode="copy")  # or "move"
print(f"Processed: {result.processed_files}")
print(f"Processed size: {result.processed_size_gb:.2f} GB")
print(f"Skipped: {result.skipped_files}")

# With duplicate detection
organizer = Orbit(
    source_dirs=["/path/to/photos"],
    destination_dir="/organized/photos",
    detect_duplicates="skip",  # or "all"
)
result = organizer.simulate(report=True)
if result.has_duplicates:
    print(f"Duplicates found: {result.duplicate_files_count}")
    print(f"Duplicate size: {result.duplicate_size_gb:.2f} GB")
    print(f"CSV report: {result.duplicate_csv_path}")

# Regenerate report from trace (no rescan needed)
organizer = Orbit(
    source_dirs=["/path/to/photos"],  # Not used, but required
    destination_dir="/organized/photos",
)
report_path = organizer.generate_report()
print(f"Report regenerated: {report_path}")

# Undo last operation
organizer.undo()
```

## Extraction Modes

The `--extraction` / `-e` option controls which datetime source is used:

| Mode | Sources used (priority order) |
|------|-------------------------------|
| `strict` | EXIF DateTimeOriginal only — files without it go to `Unsorted/` |
| `normal` | EXIF DateTimeOriginal → Image DateTime — files without either go to `Unsorted/` |
| `flexible` | EXIF DateTimeOriginal → Image DateTime → file modification time |

## Directory Pattern

The `--pattern` / `-p` option accepts Python `strftime` format codes:

| Code | Meaning | Example |
|------|---------|---------|
| `%Y` | Year | 2025 |
| `%m` | Month (zero-padded) | 01–12 |
| `%d` | Day (zero-padded) | 01–31 |
| `%B` | Month name | January |
| `%A` | Weekday name | Monday |
| `%H` | Hour | 00–23 |
| `%M` | Minute | 00–59 |

Examples:
- `%Y/%m/%d` → `2025/05/21/`
- `%Y/%B` → `2025/May/`
- `%Y/%m - %B` → `2025/05 - May/`

## Name Conflict Resolution

When multiple source files have the same destination filename, ORBIT applies a "distinctive path" algorithm:

1. Compare source paths from parent to root
2. Find the first differentiating directory name
3. Append that name as a suffix

Example:
```
/vacances/2023/photo.jpg  → 2024/05/photo_2023.jpg
/travail/2023/photo.jpg   → 2024/05/photo_2023.jpg
/vacances/2024/photo.jpg  → 2024/05/photo_2024.jpg
```

If directories are also identical, a numeric suffix is used:
```
/photos/A/photo.jpg  → 2024/05/photo_A.jpg
/photos/B/photo.jpg  → 2024/05/photo_B.jpg
```

This resolution is always active, regardless of duplicate detection settings.

## Duplicate Detection

The `--detect-duplicates` option enables detection of identical files by content hash (SHA-256):

| Strategy | Behavior |
|----------|----------|
| `all` | Copy all files with name conflict resolution. Generate duplicate report. |
| `skip` | Keep only the first occurrence of each duplicate. Skip subsequent copies. |

Detection criteria:
- Files are compared by SHA-256 hash of their binary content
- Only bit-identical files are considered duplicates
- Filename, EXIF metadata, and timestamps are ignored

Output:
- CSV report: `<destination>/.orbit_duplicates.csv`
- HTML report: "Duplicates" tab when `--report` is used

## Report Generation

### HTML Report

The HTML report provides a visual comparison of current and future file structures:

```bash
orbit -s /photos -d /organized --report
```

Features:
- File structure tree (current vs. future)
- Statistics with file counts and sizes
- Duplicate detection tab (when applicable)
- Interactive folder navigation

### Report Regeneration

A trace file is automatically saved during simulation. Use `--generate-report` to regenerate the HTML report without rescanning:

```bash
# First run creates the trace
orbit -s /photos -d /organized --report

# Later, regenerate from trace (fast, no I/O)
orbit -d /organized --generate-report
```

Trace file location: `<destination>/.orbit_trace.json`

### Size Statistics

The report includes size information:

| Metric | Description |
|--------|-------------|
| Total size | Size of all files found |
| Size to be processed | Size of files that will be copied/moved |
| Size skipped | Size of skipped files (errors, duplicates with "skip") |
| Duplicate size | Size of duplicate files (when detection enabled) |

## Execution Modes

The `--mode` / `-m` option controls the execution behavior:

| Mode | Description |
|------|-------------|
| (omitted) | Dry-run simulation only |
| `copy` | Copy files to destination |
| `move` | Move files to destination |

The `--dry-run` flag forces simulation mode even when `--mode` is specified.

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/berangerthomas/ORBIT.git
cd ORBIT
uv sync --extra dev

# Run tests
uv run pytest -v

# Run linter
uv run ruff check src/ tests/
```

## Architecture

```
src/orbit/
    __init__.py          # Public API exports
    core.py              # Orbit facade
    scanner.py           # File discovery (rglob)
    exif.py              # EXIF extraction + datetime strategies
    path_generator.py    # Destination path mapping + conflict resolution
    executor.py          # Copy/move with checksum support
    journal.py           # JSONL journal for resume & undo
    reporter.py          # HTML simulation report
    duplicate.py         # Duplicate detection (SHA-256)
    errors.py            # Typed error & result dataclasses
    cli.py               # Rich CLI (argparse + progress bar)
```

## Output Files

| File | Location | Description |
|------|----------|-------------|
| `orbit_simulation_report.html` | `<destination>/` | HTML visualization of simulation |
| `.orbit_trace.json` | `<destination>/` | JSON trace for report regeneration |
| `.orbit_duplicates.csv` | `<destination>/` | CSV list of duplicate files |
| `.orbit_journal.jsonl` | `<destination>/` | Journal for resume/undo operations |

## Requirements

- Python ≥ 3.10
- [ExifRead](https://pypi.org/project/ExifRead/)
- [Rich](https://pypi.org/project/rich/)

## License

MIT — see [LICENSE](licence.md) for details.