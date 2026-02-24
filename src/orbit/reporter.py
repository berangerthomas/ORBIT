"""
HTML report generation for ORBIT simulation results.
Generates an interactive tree view comparing source and destination structures.
Includes duplicate detection tab when applicable.
"""

from __future__ import annotations

import html as html_module
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit.duplicate import DuplicateResult


class HtmlReporter:
    """Generates HTML reports showing file organization simulation results."""

    def __init__(
        self,
        destination_dir: Path,
        logger: logging.Logger | None = None,
    ):
        self.destination_dir = destination_dir
        self.logger = logger or logging.getLogger("orbit.reporter")

    def generate(
        self,
        file_mappings: list[tuple[Path, Path]],
        stats: dict,
        duplicate_result: DuplicateResult | None = None,
        duplicate_csv_path: Path | None = None,
    ) -> Path:
        """
        Generate an HTML report showing current and future file structures.

        Args:
            file_mappings: List of (source, destination) tuples.
            stats: Statistics dictionary.
            duplicate_result: Optional duplicate detection result.
            duplicate_csv_path: Path to duplicate CSV file.

        Returns:
            Path to the generated HTML report.
        """
        source_structure = self._build_tree([src for src, _ in file_mappings])
        dest_structure = self._build_tree(
            [dst for _, dst in file_mappings],
            base_dir=self.destination_dir,
        )

        html_content = self._render_page(
            source_structure,
            dest_structure,
            stats,
            duplicate_result=duplicate_result,
            duplicate_csv_path=duplicate_csv_path,
        )

        self.destination_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.destination_dir / "orbit_simulation_report.html"
        report_path.write_text(html_content, encoding="utf-8")

        self.logger.info(f"HTML report generated: {report_path}")
        return report_path

    # ------------------------------------------------------------------
    # Tree building
    # ------------------------------------------------------------------

    def _build_tree(
        self,
        paths: list[Path],
        base_dir: Path | None = None,
    ) -> dict:
        """Build a nested dict representing a file tree."""
        tree: dict = {}

        for full_path in paths:
            if base_dir:
                try:
                    rel = full_path.relative_to(base_dir)
                except ValueError:
                    rel = full_path
            else:
                rel = full_path

            parts = rel.parts
            current = tree
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            if "_files" not in current:
                current["_files"] = []
            current["_files"].append(
                {
                    "name": parts[-1] if parts else full_path.name,
                    "path": str(full_path),
                }
            )

        return tree

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    def _render_file(self, file_info: dict, linkify: bool) -> str:
        safe_name = html_module.escape(file_info["name"])
        if linkify:
            safe_path = html_module.escape(file_info["path"]).replace("\\", "/")
            return (
                f"<li class='file'>"
                f"<a href='file:///{safe_path}' target='_blank'>{safe_name}</a>"
                f"</li>"
            )
        return f"<li class='file'>{safe_name}</li>"

    def _render_tree_items(self, structure: dict, linkify: bool) -> str:
        html = ""

        # Subdirectories first
        for key in sorted(k for k in structure if k != "_files"):
            safe_key = html_module.escape(str(key))
            html += f"<li><span class='folder'>{safe_key}</span><ul>"

            sub = structure[key]
            if isinstance(sub, dict):
                # Files at this level
                if "_files" in sub:
                    for f in sorted(sub["_files"], key=lambda x: x["name"]):
                        html += self._render_file(f, linkify)
                # Recurse into subdirectories
                sub_dirs = {k: v for k, v in sub.items() if k != "_files"}
                if sub_dirs:
                    html += self._render_tree_items(sub_dirs, linkify)

            html += "</ul></li>"

        # Root-level files
        if "_files" in structure:
            for f in sorted(structure["_files"], key=lambda x: x["name"]):
                html += self._render_file(f, linkify)

        return html

    def _render_tree(self, structure: dict, linkify: bool) -> str:
        if not structure:
            return "<p>No files found.</p>"
        return f"<ul class='tree'>{self._render_tree_items(structure, linkify)}</ul>"

    def _render_duplicates_table(
        self,
        duplicate_result: DuplicateResult,
        duplicate_csv_path: Path | None,
    ) -> str:
        """Render the duplicates table for the second tab."""
        if not duplicate_result or not duplicate_result.duplicate_groups:
            return "<p>No duplicates detected.</p>"

        rows = ""
        for group in duplicate_result.duplicate_groups:
            if not group.is_duplicate:
                continue

            safe_name = html_module.escape(group.representative.name)
            safe_hash = html_module.escape(group.checksum[:12] + "...")
            size_kb = group.size / 1024

            sources_html = ""
            for i, file_path in enumerate(group.files):
                safe_path = html_module.escape(str(file_path)).replace("\\", "/")
                sources_html += f"<a href='file:///{safe_path}' class='source-link' title='{safe_path}'>{html_module.escape(file_path.name)}</a>"
                if i < len(group.files) - 1:
                    sources_html += "<br>"

            rows += f"""
                <tr>
                    <td>{safe_name}</td>
                    <td><code>{safe_hash}</code></td>
                    <td>{size_kb:.1f} KB</td>
                    <td>{group.count}</td>
                    <td class='sources'>{sources_html}</td>
                </tr>
            """

        csv_link = ""
        if duplicate_csv_path:
            csv_link = f"<a href='file:///{html_module.escape(str(duplicate_csv_path)).replace(chr(92), '/')}' class='csv-link'>📄 Export CSV</a>"

        return f"""
        <div class="duplicates-info">
            <p><strong>{duplicate_result.groups_count}</strong> duplicate groups found</p>
            <p><strong>{duplicate_result.total_duplicates}</strong> duplicate files</p>
            <p>Space recoverable: <strong>{duplicate_result.total_wasted_space / (1024*1024):.1f} MB</strong></p>
            {csv_link}
        </div>
        <table class="duplicates-table">
            <thead>
                <tr>
                    <th>Filename</th>
                    <th>Hash</th>
                    <th>Size</th>
                    <th>Count</th>
                    <th>Source Files</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """

    def _render_page(
        self,
        source: dict,
        dest: dict,
        stats: dict,
        duplicate_result: DuplicateResult | None = None,
        duplicate_csv_path: Path | None = None,
    ) -> str:
        def s(k: str, default: str = "0") -> str:
            return html_module.escape(str(stats.get(k, default)))

        def format_size(size_bytes: int) -> str:
            """Format size in bytes to human readable format."""
            if size_bytes >= 1024**3:
                return f"{size_bytes / (1024**3):.2f} GB"
            elif size_bytes >= 1024**2:
                return f"{size_bytes / (1024**2):.1f} MB"
            elif size_bytes >= 1024:
                return f"{size_bytes / 1024:.1f} KB"
            else:
                return f"{size_bytes} B"

        source_html = self._render_tree(source, linkify=True)
        dest_html = self._render_tree(dest, linkify=False)

        # Calculate sizes
        total_size = int(stats.get("total_size", 0))
        processed_size = int(stats.get("processed_size", 0))
        skipped_size = int(stats.get("skipped_size", 0))
        duplicate_size = int(stats.get("duplicate_size", 0))

        # Check if duplicates tab is needed
        duplicates_tab_button = ""
        duplicates_tab_content = ""

        if duplicate_result:
            duplicates_tab_button = f"""
            <button class="tab-btn" onclick="showTab('duplicates')">Duplicates ({duplicate_result.groups_count})</button>
            """
            duplicates_tab_content = f"""
            <div id="duplicates-tab" class="tab-content">
                <h2>Duplicate Files Detected</h2>
                {self._render_duplicates_table(duplicate_result, duplicate_csv_path)}
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ORBIT Simulation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 20px;
            background: #f5f5f5;
            color: #333;
        }}
        .container {{ display: flex; gap: 20px; }}
        .tree-container {{
            flex: 1;
            background: #fff;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,.1);
            overflow-x: auto;
        }}
        h1, h2 {{ color: #333; }}
        ul.tree, ul.tree ul {{ list-style: none; padding-left: 20px; }}
        ul.tree {{ padding-left: 0; }}
        .folder {{
            cursor: pointer;
            color: #0055aa;
            font-weight: bold;
            user-select: none;
        }}
        .folder::before {{ content: "📁 "; }}
        .folder.open::before {{ content: "📂 "; }}
        .file {{ margin-left: 20px; }}
        .file::before {{ content: "🖼️ "; }}
        .file a {{ color: #333; text-decoration: none; }}
        .file a:hover {{ text-decoration: underline; }}
        .hidden {{ display: none; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }}
        .stat-card {{
            background: #fff;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,.05);
            border-left: 4px solid #0055aa;
        }}
        .stat-card.secondary {{ border-left-color: #6c757d; }}
        .stat-card.warning {{ border-left-color: #ffc107; }}
        .stat-card.success {{ border-left-color: #28a745; }}
        .stat-label {{
            font-size: 12px;
            text-transform: uppercase;
            color: #666;
            margin-bottom: 5px;
            font-weight: 600;
        }}
        .stat-value {{
            font-size: 20px;
            font-weight: bold;
            color: #333;
        }}
        
        /* Tabs */
        .tabs {{ margin-bottom: 20px; }}
        .tab-btn {{
            background: #fff;
            border: 1px solid #ddd;
            padding: 10px 20px;
            cursor: pointer;
            border-radius: 8px 8px 0 0;
            margin-right: 5px;
            font-size: 14px;
            transition: background 0.2s;
        }}
        .tab-btn:hover {{ background: #e9e9e9; }}
        .tab-btn.active {{
            background: #0055aa;
            color: white;
            border-color: #0055aa;
        }}
        .tab-content {{
            background: #fff;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,.1);
            display: none;
        }}
        .tab-content.active {{ display: block; }}
        
        /* Duplicates table */
        .duplicates-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .duplicates-table th,
        .duplicates-table td {{
            padding: 10px;
            border: 1px solid #ddd;
            text-align: left;
        }}
        .duplicates-table th {{
            background: #f5f5f5;
            font-weight: bold;
        }}
        .duplicates-table tr:hover {{
            background: #f9f9f9;
        }}
        .duplicates-table code {{
            font-family: monospace;
            font-size: 12px;
            color: #666;
        }}
        .duplicates-info {{
            margin-bottom: 15px;
            padding: 10px;
            background: #fff3cd;
            border-radius: 4px;
        }}
        .duplicates-info p {{ margin: 5px 0; }}
        .source-link {{
            color: #0055aa;
            text-decoration: none;
            font-size: 12px;
        }}
        .source-link:hover {{ text-decoration: underline; }}
        .csv-link {{
            display: inline-block;
            margin-top: 10px;
            padding: 5px 10px;
            background: #28a745;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 12px;
        }}
        .csv-link:hover {{ background: #218838; }}
    </style>
</head>
<body>
    <h1>ORBIT Simulation Report</h1>
    
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-label">Files Found</div>
            <div class="stat-value">{s("total_files_found")}</div>
            <div style="font-size: 11px; color: #888; margin-top: 4px;">{format_size(total_size)} total</div>
        </div>
        <div class="stat-card success">
            <div class="stat-label">To Process</div>
            <div class="stat-value">{s("processed_files")}</div>
            <div style="font-size: 11px; color: #888; margin-top: 4px;">{format_size(processed_size)}</div>
        </div>
        <div class="stat-card secondary">
            <div class="stat-label">Skipped / Excluded</div>
            <div class="stat-value">{s("skipped_files")}</div>
            <div style="font-size: 11px; color: #888; margin-top: 4px;">{format_size(skipped_size)}</div>
        </div>
        <div class="stat-card warning">
            <div class="stat-label">Action Plan</div>
            <div class="stat-value">{s("created_directories_count")}</div>
            <div style="font-size: 11px; color: #888; margin-top: 4px;">Dirs to create ({s("mode", "N/A")})</div>
        </div>
        {f'''
        <div class="stat-card warning">
            <div class="stat-label">Duplicates</div>
            <div class="stat-value">{duplicate_result.groups_count}</div>
            <div style="font-size: 11px; color: #888; margin-top: 4px;">{format_size(duplicate_size)} recoverable</div>
        </div>
        ''' if duplicate_result else ""}
    </div>
    
    <div class="tabs">
        <button class="tab-btn active" onclick="showTab('structure')">File Structure</button>
        {duplicates_tab_button}
    </div>
    
    <div id="structure-tab" class="tab-content active">
        <div class="container">
            <div class="tree-container">
                <h2>Current Structure</h2>
                {source_html}
            </div>
            <div class="tree-container">
                <h2>Future Structure</h2>
                {dest_html}
            </div>
        </div>
    </div>
    
    {duplicates_tab_content}
    
    <script>
        function showTab(tabName) {{
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {{
                tab.classList.remove('active');
            }});
            document.querySelectorAll('.tab-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            
            // Show selected tab
            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
        }}
        
        document.addEventListener('DOMContentLoaded', function() {{
            document.querySelectorAll('.folder').forEach(folder => {{
                folder.addEventListener('click', function(e) {{
                    e.stopPropagation();
                    this.classList.toggle('open');
                    let sub = this.nextElementSibling;
                    if (sub) sub.classList.toggle('hidden');
                }});
            }});
            document.querySelectorAll('ul.tree > li > ul').forEach(ul => {{
                ul.classList.add('hidden');
            }});
        }});
    </script>
</body>
</html>"""