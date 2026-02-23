"""
Core facade for ORBIT (Organized Repositories Based on Images Timing).

Orchestrates scanning, EXIF extraction, path generation, execution,
and reporting through dedicated component modules.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from orbit.duplicate import DuplicateDetector, DuplicateResult
from orbit.errors import OrbitResult, ProcessingError
from orbit.exif import STRATEGIES, ExifExtractor
from orbit.executor import FileExecutor
from orbit.journal import Journal
from orbit.path_generator import PathGenerator
from orbit.reporter import HtmlReporter
from orbit.scanner import FileScanner

ProgressCallback = Callable[[int, int, str], None] | None


class Orbit:
    """
    Main facade for organizing photos based on EXIF metadata.

    Provides simulation, copy, move, and undo operations with configurable
    datetime extraction strategies and directory patterns.
    """

    def __init__(
        self,
        source_dirs: list[str],
        destination_dir: str,
        pattern: str = "%Y/%m/%d",
        recursive: bool = False,
        fallback_pattern: str = "Unknown/%Y%m%d_%H%M%S",
        verbose: bool = False,
        mode: str = "normal",
        workers: int | None = None,
        verify: bool = False,
        detect_duplicates: str | None = None,  # None, "all", or "skip"
    ):
        """
        Initialize the photo organizer.

        Args:
            source_dirs: List of source directory paths.
            destination_dir: Destination directory path.
            pattern: strftime pattern for directory structure.
            recursive: If True, scan subdirectories recursively.
            fallback_pattern: Pattern used when datetime is partial.
            verbose: If True, enable detailed logging.
            mode: Extraction mode — "strict", "normal", or "flexible".
            workers: Number of threads for parallel EXIF extraction (None = sequential).
            verify: If True, verify checksums after copy.
            detect_duplicates: Duplicate handling strategy — None (disabled), "all", or "skip".
        """
        if mode not in STRATEGIES:
            raise ValueError(
                f"Mode must be one of {list(STRATEGIES.keys())}, got '{mode}'"
            )

        if detect_duplicates is not None and detect_duplicates not in ("all", "skip"):
            raise ValueError(
                f"detect_duplicates must be None, 'all', or 'skip', got '{detect_duplicates}'"
            )

        self.source_dirs = [Path(d) for d in source_dirs]
        self.destination_dir = Path(destination_dir)
        self.pattern = pattern
        self.recursive = recursive
        self.verbose = verbose
        self.mode = mode
        self.workers = workers
        self.verify = verify
        self.detect_duplicates = detect_duplicates

        # Validate paths before anything else
        self._validate_paths()

        # Isolated logger (does not pollute root logger)
        self.logger = self._create_logger()

        # Compose components
        self.scanner = FileScanner(self.source_dirs, recursive, self.logger)
        self.exif_extractor = ExifExtractor(self.logger)
        self.duplicate_detector = DuplicateDetector(self.logger)

        strategy = STRATEGIES[mode]()
        self.path_generator = PathGenerator(
            self.destination_dir, pattern, strategy, fallback_pattern, self.logger
        )
        self.reporter = HtmlReporter(self.destination_dir, self.logger)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_paths(self) -> None:
        """Ensure source and destination directories don't overlap."""
        dest_resolved = self.destination_dir.resolve()

        for source_dir in self.source_dirs:
            src_resolved = source_dir.resolve()

            if src_resolved == dest_resolved:
                raise ValueError(
                    f"Source and destination cannot be the same directory: {source_dir}"
                )

            if self.recursive:
                try:
                    dest_resolved.relative_to(src_resolved)
                except ValueError:
                    pass  # Not relative — this is fine
                else:
                    raise ValueError(
                        f"Destination '{self.destination_dir}' is inside source "
                        f"'{source_dir}', which would cause infinite recursion."
                    )

    def _create_logger(self) -> logging.Logger:
        """Create an isolated logger for this Orbit instance."""
        logger = logging.getLogger(f"orbit.{id(self)}")
        logger.setLevel(logging.DEBUG if self.verbose else logging.WARNING)
        logger.propagate = False

        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            handler.setLevel(logging.DEBUG if self.verbose else logging.WARNING)
            logger.addHandler(handler)

        return logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(
        self,
        progress_callback: ProgressCallback = None,
        report: bool = False,
    ) -> OrbitResult:
        """
        Simulate photo organization without moving or copying files.

        Args:
            progress_callback: Optional callback(current, total, filename).
            report: If True, generate an HTML report.

        Returns:
            OrbitResult with simulation details.
        """
        self.logger.info("Starting simulation...")

        # 1. Scan
        image_files = self.scanner.scan()
        total = len(image_files)

        # 2. Calculate total size
        total_size = 0
        file_sizes: dict[Path, int] = {}
        for image_path in image_files:
            try:
                size = image_path.stat().st_size
                file_sizes[image_path] = size
                total_size += size
            except OSError:
                file_sizes[image_path] = 0

        # 3. Extract EXIF in parallel (I/O-bound)
        exif_results = self._extract_exif_parallel(image_files)

        # 4. Detect duplicates if enabled
        duplicate_result: DuplicateResult | None = None
        files_to_skip: set[Path] = set()
        duplicate_csv_path: Path | None = None
        duplicate_size = 0

        if self.detect_duplicates:
            self.logger.info("Detecting duplicates...")
            duplicate_result = self.duplicate_detector.scan(image_files, progress_callback)

            if self.detect_duplicates == "skip":
                files_to_skip = duplicate_result.get_files_to_skip()
                # Calculate size of skipped duplicates
                for f in files_to_skip:
                    duplicate_size += file_sizes.get(f, 0)
                self.logger.info(
                    f"Skipping {len(files_to_skip)} duplicate files (strategy: skip)"
                )

            # Export CSV to destination directory
            duplicate_csv_path = self.destination_dir / ".orbit_duplicates.csv"
            self.duplicate_detector.export_csv(duplicate_result, duplicate_csv_path)

        # 5. Prepare path generator with all files (for conflict detection)
        all_path_exif_pairs = [
            (image_path, exif_data)
            for image_path, exif_data in zip(image_files, exif_results)
            if image_path not in files_to_skip
        ]
        self.path_generator.prepare(all_path_exif_pairs)

        # 6. Generate destination paths (sequential for conflict resolution)
        result = OrbitResult(
            total_files_found=total,
            mode=self.mode,
            duplicate_result=duplicate_result,
            duplicate_csv_path=str(duplicate_csv_path) if duplicate_csv_path else None,
            duplicate_strategy=self.detect_duplicates,
            total_size=total_size,
            duplicate_size=duplicate_size,
        )
        directories: set[str] = set()
        processed_size = 0
        skipped_size = 0

        for i, (image_path, exif_data) in enumerate(zip(image_files, exif_results)):
            file_size = file_sizes.get(image_path, 0)

            # Skip duplicates if strategy is "skip"
            if image_path in files_to_skip:
                result.skipped_files += 1
                skipped_size += file_size
                if progress_callback:
                    progress_callback(i + 1, total, str(image_path))
                continue

            try:
                dest_path = self.path_generator.generate(image_path, exif_data)
                result.file_mappings.append((image_path, dest_path))
                directories.add(str(dest_path.parent))
                result.processed_files += 1
                processed_size += file_size
            except Exception as e:
                result.errors.append(
                    ProcessingError(image_path, "path_generation", str(e))
                )
                result.skipped_files += 1
                skipped_size += file_size

            if progress_callback:
                progress_callback(i + 1, total, str(image_path))

        # Record missing-directory errors
        for missing_dir in self.scanner.missing_dirs:
            result.errors.append(
                ProcessingError(
                    missing_dir, "scan", f"Directory does not exist: {missing_dir}"
                )
            )

        result.created_directories = sorted(directories)
        result.processed_size = processed_size
        result.skipped_size = skipped_size

        # 7. Save trace automatically for report regeneration
        trace_path = self.destination_dir / ".orbit_trace.json"
        result.save_trace(trace_path)

        # 8. Optional HTML report
        if report:
            report_path = self._generate_report(result, duplicate_result, duplicate_csv_path)
            result.html_report_path = str(report_path)

        self.logger.info(
            f"Simulation complete: {result.processed_files} files processed"
        )
        return result

    def execute(
        self,
        mode: str = "copy",
        progress_callback: ProgressCallback = None,
        report: bool = False,
        resume: bool = False,
    ) -> OrbitResult:
        """
        Execute photo organization (copy or move).

        Args:
            mode: "copy" or "move".
            progress_callback: Optional callback(current, total, filename).
            report: If True, generate an HTML report.
            resume: If True, skip already-processed files (from journal).

        Returns:
            OrbitResult with execution details.
        """
        if mode not in ("copy", "move"):
            raise ValueError(f"Mode must be 'copy' or 'move', got '{mode}'")

        self.logger.info(f"Starting execution in '{mode}' mode...")

        # 1. Simulate to get mappings (single pass — no double processing)
        sim_result = self.simulate(report=report)

        # 2. Journal for resume / undo support
        journal = (
            Journal(self.destination_dir / ".orbit_journal.jsonl", self.logger)
            if resume
            else None
        )

        # 3. Execute file operations
        executor = FileExecutor(self.logger, journal, self.verify)
        processed, skipped, exec_errors = executor.execute(
            sim_result.file_mappings, mode, progress_callback
        )

        # 4. Build result
        result = OrbitResult(
            total_files_found=sim_result.total_files_found,
            processed_files=processed,
            skipped_files=skipped + sim_result.skipped_files,
            created_directories=sim_result.created_directories,
            errors=sim_result.errors + exec_errors,
            file_mappings=sim_result.file_mappings,
            mode=mode,
            html_report_path=sim_result.html_report_path,
            duplicate_result=sim_result.duplicate_result,
            duplicate_csv_path=sim_result.duplicate_csv_path,
            duplicate_strategy=sim_result.duplicate_strategy,
            total_size=sim_result.total_size,
            processed_size=sim_result.processed_size,
            skipped_size=sim_result.skipped_size,
            duplicate_size=sim_result.duplicate_size,
            trace_path=sim_result.trace_path,
        )

        self.logger.info(
            f"Execution complete: {processed} files {mode}d, {skipped} skipped"
        )
        return result

    def generate_report(self) -> str:
        """
        Regenerate HTML report from saved trace.

        Returns:
            Path to the generated HTML report.
        """
        trace_path = self.destination_dir / ".orbit_trace.json"

        if not trace_path.exists():
            raise FileNotFoundError(
                f"No trace file found at {trace_path}. "
                "Run a simulation first to create the trace."
            )

        result = OrbitResult.load_trace(trace_path)

        # Load duplicate result if available
        duplicate_result = None
        duplicate_csv_path = None
        if result.duplicate_csv_path:
            duplicate_csv_path = Path(result.duplicate_csv_path)
            # Note: We don't reload DuplicateResult from CSV as it's exported only

        report_path = self._generate_report(result, duplicate_result, duplicate_csv_path)
        result.html_report_path = str(report_path)

        return str(report_path)

    def _generate_report(
        self,
        result: OrbitResult,
        duplicate_result: DuplicateResult | None,
        duplicate_csv_path: Path | None,
    ) -> Path:
        """Generate HTML report from result."""
        return self.reporter.generate(
            result.file_mappings,
            {
                "total_files_found": result.total_files_found,
                "processed_files": result.processed_files,
                "skipped_files": result.skipped_files,
                "created_directories_count": result.created_directories_count,
                "mode": self.mode,
                "duplicate_strategy": self.detect_duplicates,
                "duplicate_groups": duplicate_result.groups_count if duplicate_result else 0,
                "duplicate_files": duplicate_result.total_duplicates if duplicate_result else 0,
                "total_size": result.total_size,
                "processed_size": result.processed_size,
                "skipped_size": result.skipped_size,
                "duplicate_size": result.duplicate_size,
            },
            duplicate_result=duplicate_result,
            duplicate_csv_path=duplicate_csv_path,
        )

    def undo(self) -> list[dict]:
        """
        Undo the last journaled operation.

        Returns:
            List of undo results with status for each entry.
        """
        journal = Journal(
            self.destination_dir / ".orbit_journal.jsonl", self.logger
        )
        journal.load()

        if not journal.entries:
            self.logger.warning("No journal entries found. Nothing to undo.")
            return []

        return journal.undo()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_exif_parallel(self, image_files: list[Path]) -> list[dict]:
        """Extract EXIF data, optionally using a thread pool."""
        if self.workers and self.workers > 1 and len(image_files) > 1:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                return list(pool.map(self.exif_extractor.extract, image_files))
        return [self.exif_extractor.extract(f) for f in image_files]