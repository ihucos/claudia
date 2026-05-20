from time import sleep

from ... import utils
import re
import os
import tempfile
import subprocess
from collections import defaultdict


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


def remove_marker_dir(filename):
    """Remove the DUMMY_DIR prefix from a filename."""
    if filename.startswith(MARKER_DIR):
        return filename[len(MARKER_DIR) :]
    return filename


def get_context_files(model, task):
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


def files_to_fragments(files):
    """Read files and create fragments for the LLM."""
    fragments = []
    for file in files:
        try:
            with open(remove_marker_dir(file), "r") as f:
                content = f.read()
        except FileNotFoundError:
            fragments.append(f"# File not found: {file}")
        else:
            fragments.append(f"# {file}\n\n{escape_codeblocks(content)}")
    return fragments


def implement(*, task, context_files, model, progress_cb):
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

    return line_handler.get_files()


class LineHandler:
    """Handle streaming lines from LLM output, collecting file changes."""

    def __init__(self, progress_cb):
        self.current_file = None
        self.contents = defaultdict(list)
        self.progress = None
        self.task_id = None
        self.progress_cb = progress_cb

    def _get_total_lines(self, fname):
        try:
            with open(fname, "r") as f:
                return len(f.readlines())
        except FileNotFoundError:
            return 0

    def handle_line(self, line):
        print(f"LineHandler: {repr(line)}")

        # Does the line contain a filename containing the MARKER_DIR?
        if match := re.search(FILE_PATH_PATTERN, line):
            fname = remove_marker_dir(match.group(1))
            self.current_file = fname
            return

        if self.current_file:
            self.contents[self.current_file].append(line)
            self.progress_cb(f"Editing {self.current_file}")

    def get_files(self):
        stripped_contents = {}
        for fname, lines in self.contents.items():
            content = "\n".join(lines)
            content = unescape_codeblocks(content)
            content = trim_code_blocks_magic(fname, content)
            stripped_contents[fname] = content

        return stripped_contents


def run(model, ui):
    ui.hello()
    while True:
        task = ui.prompt()
        if task is None:
            break

        with ui.loading("Get context files"):
            context_files = get_context_files(model, task)
            ui.info("Context files", "\n".join(context_files))

        with ui.loading("Implementing"):
            files = implement(
                task=task,
                context_files=context_files,
                model=model,
                progress_cb=ui.loading,
            )
            for fname, content in files.items():
                ui.info(fname, content)

        ui.loading("calculating...")
        sleep(1)
        ui.answer("Done")
    ui.bye()


#
# import sys
# import re
# import os
# import tempfile
# from collections import defaultdict
# import subprocess
#
# from rich.console import Console
# from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
# import questionary
#
# from . import utils
# from . import constants
# from . import models
#
#
# model = models.DeepSeekChat("deepseek-v4-flash")
#
# console = Console()
#
#
#
#
#
#
# def interactive_mode():
#     """Interactive REPL mode for continuous code generation."""
#     # Import here for better startup time
#     from prompt_toolkit import prompt
#     from prompt_toolkit.history import FileHistory
#
#     history = FileHistory(os.path.expanduser("~/.klaus_history"))
#
#     console.print("Hi, specify your desired code changes (return with alt-enter)")
#     while True:
#         try:
#             user_input = prompt(
#                 "> ",
#                 multiline=True,
#                 history=history,
#                 prompt_continuation="... ",
#             )
#             implement(user_input)
#         except (EOFError, KeyboardInterrupt):
#             break
#
#
# def main():
#     if not os.environ.get("DEEPSEEK_API_KEY"):
#         console.print(
#             "claudia error: Please set the environment variable DEEPSEEK_API_KEY to your DeepSeek API key.",
#             style="bold red",
#         )
#         sys.exit(1)
#     if len(sys.argv) > 1:
#         task = " ".join(sys.argv[1:])
#         implement(task)
#     else:
#         interactive_mode()
#
#
# if __name__ == "__main__":
#     main()


#
# import sys
# import re
# import os
# import tempfile
# from collections import defaultdict
# import subprocess
#
# from rich.console import Console
# from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
# import questionary
#
# from . import utils
# from . import constants
# from . import models
#
#
# model = models.DeepSeekChat("deepseek-v4-flash")
#
# console = Console()
#
#
# class LineHandler:
#     """Handle streaming lines from LLM output, collecting file changes."""
#
#     def __init__(self):
#         self.current_file = None
#         self.contents = defaultdict(list)
#         self.progress = None
#         self.task_id = None
#
#     def get_total_lines(self, fname):
#         try:
#             with open(fname, "r") as f:
#                 return len(f.readlines())
#         except FileNotFoundError:
#             return 0
#
#     def __enter__(self):
#         return self
#
#     def __call__(self, line):
#         utils.debug(f"LineHandler: {repr(line)}")
#
#         # Does the line contain a filename containing the MARKER_DIR?
#         if match := re.search(constants.FILE_PATH_PATTERN, line):
#             fname = utils.remove_filename_prefix(match.group(1))
#             if self.current_file:
#                 self.finish_current_file()
#             self.current_file = fname
#
#             if self.progress is None:
#                 self.progress = Progress(
#                     TextColumn("[progress.description]{task.description}"),
#                     BarColumn(),
#                     TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
#                     transient=True,
#                 )
#                 self.progress.start()
#
#             total = self.get_total_lines(fname)
#             self.task_id = self.progress.add_task(
#                 f"[cyan]{fname}[/cyan]", total=total if total > 0 else None
#             )
#             return
#
#         if self.current_file and self.progress and self.task_id is not None:
#             self.contents[self.current_file].append(line)
#             self.progress.update(self.task_id, advance=1)
#
#     def finish_current_file(self):
#         """Close the current progress bar and reset state."""
#         if self.task_id is not None and self.progress:
#             self.progress.update(self.task_id, visible=False)
#             self.task_id = None
#         self.current_file = None
#
#     def write_changes(self, dir):
#         """Write accumulated changes to the specified directory."""
#         for fname, lines in self.contents.items():
#             fname = os.path.join(dir, fname)
#             if os.sep in fname:
#                 os.makedirs(os.path.dirname(fname), exist_ok=True)
#             assert ".." not in fname
#             with open(fname, "w") as f:
#                 content = "\n".join(lines)
#                 content = utils.unescape_codeblocks(content)
#                 content = utils.trim_code_blocks_magic(fname, content)
#                 f.write(content)
#
#     def preview_changes(self):
#         tmpdir = tempfile.mkdtemp(
#             suffix="  .",  # for better UX
#         )
#         self.write_changes(tmpdir)
#         subprocess.call(
#             [
#                 "git",
#                 "diff",
#                 "--no-index",
#                 ".",
#                 tmpdir,
#                 "--diff-filter=AM",
#             ]
#         )
#
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         if exc_type is not None:
#             return False
#
#         # Finish any remaining progress bar
#         if self.progress:
#             self.progress.stop()
#             self.progress = None
#
#         if self.contents:
#             self.preview_changes()
#             if questionary.confirm("\nWrite the files?", default=True).ask():
#                 self.write_changes(".")
#                 console.print(f"Files changed: {', '.join(self.contents.keys())}")
#             else:
#                 console.print("Changes discarded")
#         else:
#             console.print("No changes")
#
#
#
#
# def implement(task):
#     """Main implementation flow: get context, generate code, apply changes."""
#     files = get_context_files(task)
#     fragments = utils.files_to_fragments(sorted(files))
#
#     response = model.prompt(
#         constants.PROMPT_IMPLEMENT_TEMPLATE.format(
#             task=task, project_map=utils.get_project_map()
#         ),
#         fragments=fragments,
#     )
#
#     with LineHandler() as line_handler:
#         changes = ""
#         for chunk in response:
#             changes += chunk
#             while "\n" in changes:
#                 line, newline, changes = changes.partition("\n")
#                 line_handler(line)
#         if changes:
#             line_handler(changes)
#
#
# def interactive_mode():
#     """Interactive REPL mode for continuous code generation."""
#     # Import here for better startup time
#     from prompt_toolkit import prompt
#     from prompt_toolkit.history import FileHistory
#
#     history = FileHistory(os.path.expanduser("~/.klaus_history"))
#
#     console.print("Hi, specify your desired code changes (return with alt-enter)")
#     while True:
#         try:
#             user_input = prompt(
#                 "> ",
#                 multiline=True,
#                 history=history,
#                 prompt_continuation="... ",
#             )
#             implement(user_input)
#         except (EOFError, KeyboardInterrupt):
#             break
#
#
# def main():
#     if not os.environ.get("DEEPSEEK_API_KEY"):
#         console.print(
#             "claudia error: Please set the environment variable DEEPSEEK_API_KEY to your DeepSeek API key.",
#             style="bold red",
#         )
#         sys.exit(1)
#     if len(sys.argv) > 1:
#         task = " ".join(sys.argv[1:])
#         implement(task)
#     else:
#         interactive_mode()
#
#
# if __name__ == "__main__":
#     main()
