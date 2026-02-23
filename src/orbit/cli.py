"""
Command-line interface for ORBIT.
Uses rich for progress bars, tables, and colored output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from orbit.core import Orbit
from orbit.errors import OrbitResult

console = Console()


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="orbit",
        description="ORBIT — Organized Repositories Based on Images Timing",
        epilog=(
            "Examples:\n"
            "  orbit -s ./photos -d ./organized --dry-run\n"
            "  orbit -s ./photos -d ./organized -m copy -r\n"
            "  orbit -s ./photos -d ./organized -m move --report\n"
            "  orbit -s ./photos -d ./organized --undo\n"
            "  orbit -s ./photos -d ./organized -m copy --detect-duplicates skip\n"
            "  orbit -d ./organized --generate-report\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--sources",
        "-s",
        nargs="+",
        required=False,
        help="Source directories containing photos",
    )
    parser.add_argument(
        "--destination",
        "-d",
        required=True,
        help="Destination directory for organized photos",
    )
    parser.add_argument(
        "--pattern",
        "-p",
        default="%Y/%m/%d",
        help="strftime pattern for directory structure (default: %%Y/%%m/%%d)",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        default=False,
        help="Recursively explore subdirectories",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["copy", "move"],
        default=None,
        help="Execution mode: copy or move (omit for dry-run simulation)",
    )
    parser.add_argument(
        "--extraction",
        "-e",
        choices=["strict", "normal", "flexible"],
        default="normal",
        help="EXIF extraction mode (default: normal)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without copying or moving (default if --mode is omitted)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate an HTML simulation report",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previously interrupted operation",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Undo the last journaled operation",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify file integrity with checksums after copy",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=None,
        help="Number of threads for parallel EXIF extraction",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--detect-duplicates",
        nargs="?",
        const="all",
        choices=["all", "skip"],
        default=None,
        help=(
            "Detect duplicate files by content hash. "
            "Values: 'all' (copy all with renaming, default), "
            "'skip' (keep only first occurrence). "
            "If flag is present without value, defaults to 'all'."
        ),
    )
    parser.add_argument(
        "--generate-report",
        action="store_true",
        help="Regenerate HTML report from saved trace (no rescan needed)",
    )

    return parser.parse_args(args)


def main(args: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parsed = parse_args(args)

    try:
        # --generate-report mode: regenerate report from trace
        if parsed.generate_report:
            return _generate_report(parsed)

        # Require sources for other operations
        if not parsed.sources:
            console.print("[bold red]Error:[/bold red] --sources is required unless --generate-report is specified")
            return 1

        organizer = Orbit(
            source_dirs=parsed.sources,
            destination_dir=parsed.destination,
            pattern=parsed.pattern,
            recursive=parsed.recursive,
            verbose=parsed.verbose,
            mode=parsed.extraction,
            workers=parsed.workers,
            verify=parsed.verify,
            detect_duplicates=parsed.detect_duplicates,
        )

        # --undo mode
        if parsed.undo:
            console.print("\n[bold yellow]Undoing last operation...[/bold yellow]")
            results = organizer.undo()

            if not results:
                console.print("[yellow]No operations to undo.[/yellow]")
            else:
                for r in results:
                    status = r["status"]
                    color = "green" if status == "undone" else "red"
                    entry = r["entry"]
                    console.print(
                        f"  [{color}]{status}[/{color}]: {entry['source']}"
                    )
                console.print(
                    f"\n[bold]Undo complete: "
                    f"{len(results)} operations processed.[/bold]"
                )
            return 0

        # Determine simulation vs execution
        is_simulation = parsed.mode is None or parsed.dry_run

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Scanning...", total=None)

            def update_progress(current: int, total: int, filename: str) -> None:
                progress.update(
                    task,
                    total=total,
                    completed=current,
                    description=f"[cyan]{Path(filename).name}[/cyan]",
                )

            if is_simulation:
                result = organizer.simulate(
                    progress_callback=update_progress,
                    report=parsed.report,
                )
            else:
                result = organizer.execute(
                    mode=parsed.mode,
                    progress_callback=update_progress,
                    report=parsed.report,
                    resume=parsed.resume,
                )

        # Display results table
        _display_result(result, is_simulation, parsed.mode)

        return 1 if result.has_errors else 0

    except ValueError as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        return 130
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        return 1


def _generate_report(parsed: argparse.Namespace) -> int:
    """Regenerate HTML report from saved trace."""
    dest_dir = Path(parsed.destination)
    trace_path = dest_dir / ".orbit_trace.json"

    if not trace_path.exists():
        console.print(f"[bold red]Error:[/bold red] No trace file found at {trace_path}")
        console.print("Run a simulation first to create the trace.")
        return 1

    console.print(f"[cyan]Loading trace from {trace_path}...[/cyan]")
    result = OrbitResult.load_trace(trace_path)

    # Create organizer just for report generation
    organizer = Orbit(
        source_dirs=["."],  # Dummy, won't be used
        destination_dir=parsed.destination,
        verbose=parsed.verbose,
    )

    report_path = organizer.generate_report()
    console.print(f"[green]Report generated: {report_path}[/green]")

    return 0


def _display_result(result: OrbitResult, is_simulation: bool, mode: str | None) -> None:
    """Display results in a formatted table."""
    console.print()
    title = (
        "Simulation Results"
        if is_simulation
        else f"Execution Results ({mode})"
    )
    table = Table(title=title, show_header=False, border_style="blue")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    # File counts
    table.add_row("Files found", str(result.total_files_found))
    table.add_row(
        "Files processed", f"[green]{result.processed_files}[/green]"
    )
    table.add_row("Files skipped", str(result.skipped_files))
    table.add_row("Directories", str(result.created_directories_count))

    # Size information
    if result.total_size > 0:
        table.add_row("Total size", _format_size(result.total_size))
        table.add_row("Size processed", _format_size(result.processed_size))
        if result.skipped_size > 0:
            table.add_row("Size skipped", _format_size(result.skipped_size))

    # Duplicate information
    if result.has_duplicates and result.duplicate_result:
        table.add_row(
            "Duplicate groups",
            f"[yellow]{result.duplicate_result.groups_count}[/yellow]",
        )
        table.add_row(
            "Duplicate files",
            f"[yellow]{result.duplicate_files_count}[/yellow]",
        )
        if result.duplicate_size > 0:
            table.add_row("Duplicate size", _format_size(result.duplicate_size))
        if result.duplicate_csv_path:
            table.add_row("Duplicates CSV", result.duplicate_csv_path)

    # Trace and report paths
    if result.trace_path:
        table.add_row("Trace", result.trace_path)
    if result.html_report_path:
        table.add_row("Report", result.html_report_path)

    console.print(table)

    # Display errors
    if result.has_errors:
        console.print(
            f"\n[bold red]Errors ({len(result.errors)}):[/bold red]"
        )
        for error in result.errors:
            console.print(f"  [red]•[/red] {error}")


def _format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable format."""
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} B"


if __name__ == "__main__":
    sys.exit(main())