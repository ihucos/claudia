from time import sleep

from .. import utils
import re
import os
from collections import defaultdict
from io import StringIO
import difflib
import subprocess
from time import sleep


MARKER_DIR = "github_repository/"
FILE_PATH_PATTERN = re.compile(rf"({MARKER_DIR}[\w/.-]+)")
CODEBLOCK = "\n```"
ESCAPED_CODEBLOCK = "\n ```"

PROMPT_RELEVANT_FILES = """
# Task
List files thath are relevant to the task.

## Task
{task}

## Project overview
```
{project_map}
```

## Notes
- Emit the full file path including the '{marker_dir}' prefix.
"""

PROMPT_IMPLEMENT = """
# Persona
You are a senior software developer.

# Project overview
```
{project_map}
```

# Implement
{task}

# Notes
- Emit the whole file contents of files you want to edit as their content will be directly replaced with your content.
- Always emmit the full file path containing the '{marker_dir}' prefix.
- Only emmit the file path and the file contents, don't reason.
"""


def escape_codeblocks(text: str) -> str:
    return text.replace(CODEBLOCK, ESCAPED_CODEBLOCK)


def unescape_codeblocks(text: str) -> str:
    return text.replace(ESCAPED_CODEBLOCK, CODEBLOCK)


def trim_code_blocks_magic(fname: str, content: str) -> str:
    """Remove surrounding code block markers from content if present."""
    content = content.rstrip("\n`")
    content = content.lstrip("\n")

    content_lines = content.splitlines()
    if content_lines and content_lines[0].startswith("```"):
        content = "\n".join(content_lines[1:])

    if not content.endswith("\n"):
        content += "\n"

    return content


def remove_marker_dir(filename: str) -> str:
    """Remove the DUMMY_DIR prefix from a filename."""
    if filename.startswith(MARKER_DIR):
        return filename[len(MARKER_DIR) :]
    return filename


def get_context_files(model, task: str) -> list:
    """Get relevant context files for a given task from the LLM."""
    prompt = PROMPT_RELEVANT_FILES.format(
        project_map=utils.get_project_map(prepend_to_files=MARKER_DIR),
        task=task,
        marker_dir=MARKER_DIR,
    )

    response = model.prompt(prompt)
    files = FILE_PATH_PATTERN.findall(response.text())
    fs_files = [remove_marker_dir(f) for f in files]
    return fs_files


def make_diff(contents: dict[str, str], dir: str) -> str:
    diff = StringIO()
    for fname, content in contents.items():
        try:
            with open(os.path.join(dir, fname), "r") as f:
                original_lines = f.readlines()
        except FileNotFoundError:
            original_lines = []

        # Fix: Keep the trailing newlines on the new content lines
        # so they match the format returned by f.readlines()
        new_lines = [line + "\n" for line in content.splitlines()]

        file_diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{fname}",
            tofile=f"b/{fname}",
        )
        diff.write("\n".join(i.strip("\n") for i in file_diff))
    return diff.getvalue()


def apply_diff(diff: str, dir: str) -> None:
    subprocess.run(
        ["patch", "-p1"],
        cwd=dir,
        check=True,
        capture_output=True,
        text=True,
        input=diff,
    )


def get_diff_shortstat(diff: str) -> str:
    """Get a git-style shortstat summary for the given diff."""
    try:
        result = subprocess.run(
            ["git", "apply", "--stat", "--summary", "/dev/stdin"],
            check=True,
            capture_output=True,
            text=True,
            input=diff,
        )
        # The last line of git apply --stat output is the shortstat
        lines = result.stdout.strip().splitlines()
        if lines:
            return lines[-1]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    # Fallback: manual computation
    added = 0
    removed = 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1

    fcount = len({l.split()[-1] for l in diff.splitlines() if l.startswith("diff --git ")})
    return f"{fcount} file(s) changed, {added} insertions(+), {removed} deletions(-)"


def files_to_fragments(files: list) -> list:
    """Read files and create fragments for the LLM."""
    fragments = []
    for file in files:
        try:
            with open(remove_marker_dir(file), "r") as f:
                content = f.read()
        except FileNotFoundError:
            fragments.append(f"# File not found: {file}")
        except IsADirectoryError:
            continue
        else:
            fragments.append(f"# {file}\n\n{escape_codeblocks(content)}")
    return fragments


def implement(*, task: str, context_files: list, model, progress_cb) -> dict:
    response = model.prompt(
        PROMPT_IMPLEMENT.format(
            task=task,
            project_map=utils.get_project_map(prepend_to_files=MARKER_DIR),
            marker_dir=MARKER_DIR,
        ),
        fragments=files_to_fragments(sorted(context_files)),
    )
    line_handler = LineHandler(progress_cb=progress_cb)

    changes = ""
    for chunk in response:
        changes += chunk
        while "\n" in changes:
            line, newline, changes = changes.partition("\n")
            line_handler.handle_line(line)
    if changes:
        line_handler.handle_line(changes)

    files = line_handler.get_files()

    # Hack
    if list(files.keys()) == [""] and len(context_files) == 1:
        files = {context_files[0]: files[""]}

    return files


class LineHandler:
    """Handle streaming lines from LLM output, collecting file changes."""

    def __init__(self, progress_cb):
        self.current_file = None
        self.contents = defaultdict(list)
        self.progress = None
        self.task_id = None
        self.progress_cb = progress_cb

    def _get_total_lines(self, fname: str) -> int:
        try:
            with open(fname, "r") as f:
                return len(f.readlines())
        except FileNotFoundError:
            return 0

    def handle_line(self, line: str) -> None:
        # print(f"LineHandler: {repr(line)}")

        # Does the line contain a filename containing the MARKER_DIR?
        if match := re.search(FILE_PATH_PATTERN, line):
            fname = remove_marker_dir(match.group(1))
            self.current_file = fname
            return

        if self.current_file:
            self.contents[self.current_file].append(line)
            self.progress_cb(f"Editing {self.current_file}")

    def get_files(self) -> dict:
        stripped_contents = {}
        for fname, lines in self.contents.items():
            content = "\n".join(lines)
            content = unescape_codeblocks(content)
            content = trim_code_blocks_magic(fname, content)
            stripped_contents[fname] = content

        return stripped_contents


def run(model, ui) -> None:
    app_dir = os.getcwd()
    ui.hello()
    while True:
        task = ui.prompt()
        if task is None:
            break

        with ui.loading("Get context files"):
            context_files = get_context_files(model, task)
        with ui.loading(f"Implement with: {', '.join(context_files)}"):
            # UI Hack: The context files are important info, let the user see it.
            sleep(3)

            files: dict[str, str] = implement(
                task=task,
                context_files=context_files,
                model=model,
                progress_cb=ui.loading,
            )

        diff = make_diff(files, app_dir)
        stat = get_diff_shortstat(diff)
        if ui.ask_diff(diff, stat=stat):
            with ui.catch():
                apply_diff(diff, app_dir)
            ui.diff_applied_msg(cmd="patch -p1")
    ui.bye()
