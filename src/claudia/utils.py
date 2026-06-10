import functools
import subprocess
from io import StringIO


from rich.console import Console

console = Console()


@functools.cache
def get_project_map():
    """Generate a map of project files and their tags using ctags.

    Returns a string mapping filenames to their ctags symbols.
    If ctags is not available or git fails, returns an empty string
    so the calling code can degrade gracefully.
    """
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
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

    if not all_git_files:
        return ""

    try:
        ctags = subprocess.check_output(
            ["ctags", "-f-"] + all_git_files, stderr=subprocess.DEVNULL
        ).decode("utf-8")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

    for line in ctags.splitlines():
        if not line:
            continue
        tag, filename, *rest = line.split("\t")
        files.setdefault(filename, []).append(tag)

    files_map = StringIO()
    for filename, tags in files.items():
        files_map.write(f"{filename}: ")
        files_map.write(", ".join(tags))
        files_map.write("\n")

    files_map.seek(0)
    return files_map.read()
