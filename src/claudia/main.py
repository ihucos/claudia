import sys
import re
import os
import tempfile
from collections import defaultdict
import subprocess

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import questionary

from . import utils
from . import constants
from . import models


model = models.DeepSeekChat("deepseek-v4-flash")

console = Console()


class LineHandler:
    """Handle streaming lines from LLM output, collecting file changes."""

    def __init__(self):
        self.current_file = None
        self.contents = defaultdict(list)
        self.progress = None
        self.task_id = None

    def get_total_lines(self, fname):
        try:
            with open(fname, "r") as f:
                return len(f.readlines())
        except FileNotFoundError:
            return 0

    def __enter__(self):
        return self

    def __call__(self, line):
        utils.debug(f"LineHandler: {repr(line)}")

        # Does the line contain a filename containing the DUMMY_DIR?
        if match := re.search(constants.FILE_PATH_PATTERN, line):
            fname = utils.remove_filename_prefix(match.group(1))
            if self.current_file:
                self.finish_current_file()
            self.current_file = fname
            
            if self.progress is None:
                self.progress = Progress(
                    TextColumn("[progress.description]{task.description}"),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    transient=True,
                )
                self.progress.start()
            
            total = self.get_total_lines(fname)
            self.task_id = self.progress.add_task(
                f"[cyan]{fname}[/cyan]",
                total=total if total > 0 else None
            )
            return

        if self.current_file and self.progress and self.task_id is not None:
            self.contents[self.current_file].append(line)
            self.progress.update(self.task_id, advance=1)

    def finish_current_file(self):
        """Close the current progress bar and reset state."""
        if self.task_id is not None and self.progress:
            self.progress.update(self.task_id, visible=False)
            self.task_id = None
        self.current_file = None

    def write_changes(self, dir):
        """Write accumulated changes to the specified directory."""
        for fname, lines in self.contents.items():
            fname = os.path.join(dir, fname)
            if os.sep in fname:
                os.makedirs(os.path.dirname(fname), exist_ok=True)
            assert ".." not in fname
            with open(fname, "w") as f:
                content = "\n".join(lines)
                content = utils.unescape_codeblocks(content)
                content = utils.trim_code_blocks_magic(fname, content)
                f.write(content)

    def preview_changes(self):
        tmpdir = tempfile.mkdtemp(
            suffix="  .",  # for better UX
        )
        self.write_changes(tmpdir)
        subprocess.call(
            [
                "git",
                "diff",
                "--no-index",
                ".",
                tmpdir,
                "--diff-filter=AM",
            ]
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False

        # Finish any remaining progress bar
        if self.progress:
            self.progress.stop()
            self.progress = None

        if self.contents:
            self.preview_changes()
            if questionary.confirm("\nWrite the files?", default=True).ask():
                self.write_changes(".")
                console.print(f"Files changed: {', '.join(self.contents.keys())}")
            else:
                console.print("Changes discarded")
        else:
            console.print("No changes")


def get_context_files(task):
    """Get relevant context files for a given task from the LLM."""
    prompt = constants.PROMPT_CONTEXT_TEMPLATE.format(
        project_map=utils.get_project_map(),
        task=task,
        dummy_dir=constants.DUMMY_DIR,
    )

    response = model.prompt(prompt)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("[cyan]Getting context files...", total=None)
        for chunk in response:
            pass

    files = constants.FILE_PATH_PATTERN.findall(response.text())
    fs_files = [utils.remove_filename_prefix(f) for f in files]
    console.print(f"Context: {', '.join(fs_files)}")
    return files


def implement(task):
    """Main implementation flow: get context, generate code, apply changes."""
    files = get_context_files(task)
    fragments = utils.files_to_fragments(sorted(files))

    response = model.prompt(
        constants.PROMPT_IMPLEMENT_TEMPLATE.format(
            task=task, project_map=utils.get_project_map()
        ),
        fragments=fragments,
    )

    with LineHandler() as line_handler:
        changes = ""
        for chunk in response:
            changes += chunk
            while "\n" in changes:
                line, newline, changes = changes.partition("\n")
                line_handler(line)
        if changes:
            line_handler(changes)


def interactive_mode():
    """Interactive REPL mode for continuous code generation."""
    # Import here for better startup time
    from prompt_toolkit import prompt
    from prompt_toolkit.history import FileHistory

    history = FileHistory(os.path.expanduser("~/.klaus_history"))

    console.print("Hi, specify your desired code changes (return with alt-enter)")
    while True:
        try:
            user_input = prompt(
                "> ",
                multiline=True,
                history=history,
                prompt_continuation="... ",
            )
            implement(user_input)
        except (EOFError, KeyboardInterrupt):
            break


def main():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        console.print(
            "claudia error: Please set the environment variable DEEPSEEK_API_KEY to your DeepSeek API key.",
            style="bold red",
        )
        sys.exit(1)
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        implement(task)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
