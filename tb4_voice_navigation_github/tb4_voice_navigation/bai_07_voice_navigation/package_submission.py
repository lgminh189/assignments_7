#!/usr/bin/env python3
"""Package source, map, reports and Nav2 support without local environments."""
from pathlib import Path
import re
import zipfile


def main():
    workspace = Path(__file__).resolve().parents[1]
    output = workspace / "tb4_voice_navigation_github.zip"
    project = Path("tb4_voice_navigation")
    ignored = {".venv", "__pycache__", ".pytest_cache", ".git", "models"}
    sources = [workspace / ".gitignore", workspace / "requirements-voice.txt"]
    for folder in [workspace / "bai_07_voice_navigation", workspace / "src/tb4_assignment"]:
        sources.extend(p for p in folder.rglob("*") if p.is_file()
                       and not ignored.intersection(p.relative_to(workspace).parts)
                       and p.suffix not in {".pyc", ".pyo", ".zip"})
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # Like the gesture submission: a complete README at project root.
        # Rebase the lesson README's local links without changing code paths.
        detailed = (workspace / "bai_07_voice_navigation/README.md").read_text(encoding="utf-8")
        def root_link(match):
            target = match[1]
            if target.startswith(("http://", "https://", "#")):
                return match[0]
            return "](" + "bai_07_voice_navigation/" + target + ")"
        detailed = re.sub(r"\]\(([^)]+)\)", root_link, detailed)
        archive.writestr(str(project / "README.md"), detailed)
        for path in sorted(set(sources)):
            archive.write(path, project / path.relative_to(workspace))
    with zipfile.ZipFile(output) as archive:
        error = archive.testzip()
        if error:
            raise RuntimeError(f"ZIP corrupted: {error}")
        print(f"{output}\nFiles: {len(archive.namelist())}\nSize: {output.stat().st_size / 1024**2:.2f} MiB")


if __name__ == "__main__":
    main()
