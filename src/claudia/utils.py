import functools
import os
import subprocess
import sys
from io import StringIO


from rich.console import Console

console = Console()


@functools.cache
def get_project_files(workdir):
    return subprocess.run(
        ["git", "ls-files", "--modified", "--cached", "--others", "--exclude-standard"],
        text=True,
        capture_output=True,
        cwd=workdir,
    )


@functools.cache
def get_project_map(prepend_to_files=""):
    """Generate a map of project files and their tags using ctags."""
    files = {}
    try:
        all_git_files = (
            subprocess.check_output(
                [
                    "git",
                    "ls-files",
                    "--modified",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
            )
            .decode("utf-8")
            .splitlines()
        )
    except subprocess.CalledProcessError as exc:
        console.print("claudia error:", exc, style="bold red")
        sys.exit(1)

    # Ctags fails if a file does not exist
    for file in list(all_git_files):
        if not os.path.exists(file):
            all_git_files.remove(file)

    try:
        ctags = subprocess.check_output(
            ["ctags", "-f-"] + all_git_files, stderr=subprocess.DEVNULL
        ).decode("utf-8")
    except subprocess.CalledProcessError as exc:
        console.print("claudia error:", exc, style="bold red")
        sys.exit(1)

    for line in ctags.splitlines():
        tag, filename, *rest = line.split("\t")
        files.setdefault(filename, []).append(tag)

    files_map = StringIO()
    for filename, tags in files.items():
        files_map.write(f"{prepend_to_files}{filename}: ")
        files_map.write(", ".join(tags))
        files_map.write("\n")

    files_map.seek(0)
    return files_map.read()
