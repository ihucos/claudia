from rich.console import Console
import functools
import os
import sys
import subprocess
from io import StringIO

from .constants import DUMMY_DIR, CODEBLOCK, ESCAPED_CODEBLOCK

console = Console()


def debug(text):
    if os.environ.get("CLAUDIA_DEBUG") in ["1", "true"]:
        console.print(text, style="dim")


def escape_codeblocks(text):
    return text.replace(CODEBLOCK, ESCAPED_CODEBLOCK)


def unescape_codeblocks(text):
    return text.replace(ESCAPED_CODEBLOCK, CODEBLOCK)


def trim_code_blocks_magic(fname, content):
    """Remove surrounding code block markers from content if present."""
    content = content.rstrip("\n`")
    content = content.lstrip("\n")

    content_lines = content.splitlines()
    if content_lines and content_lines[0].startswith("```"):
        content = "\n".join(content_lines[1:])

    if not content.endswith("\n"):
        content += "\n"

    return content


def remove_filename_prefix(filename):
    """Remove the DUMMY_DIR prefix from a filename."""
    if filename.startswith(f"{DUMMY_DIR}/"):
        return filename[len(f"{DUMMY_DIR}/") :]
    return filename


@functools.cache
def get_project_map(prepend_dummy_dir=True):
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
        if "/migrations/" in filename:
            continue
        files.setdefault(filename, []).append(tag)

    files_map = StringIO()
    for filename, tags in files.items():
        if prepend_dummy_dir:
            files_map.write(f"{DUMMY_DIR}/{filename}: ")
        else:
            files_map.write(f"{filename}: ")
        files_map.write(", ".join(tags))
        files_map.write("\n")

    files_map.seek(0)
    return files_map.read()


def files_to_fragments(files):
    """Read files and create fragments for the LLM."""
    fragments = []
    for file in files:
        try:
            with open(remove_filename_prefix(file), "r") as f:
                content = f.read()
        except FileNotFoundError:
            fragments.append(f"# File not found: {file}")
        else:
            fragments.append(f"# {file}\n\n{escape_codeblocks(content)}")
    return fragments
