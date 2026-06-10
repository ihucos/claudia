import sys
import os
import subprocess
from contextlib import contextmanager

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax


class UICatch:
    def __init__(self, *, ui):
        self.ui = ui

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return None

        # Handle called process errors first (most specific)
        if issubclass(exc_type, subprocess.CalledProcessError):
            self.ui.progress.stop()
            self.ui.console.print(
                f"claudia error: {exc_val}", style="bold red", markup=False
            )
            if exc_val.stdout.strip():
                self.ui.console.print(
                    Panel.fit(Text.from_ansi(exc_val.stdout.strip()), title="stdout"),
                    markup=True,
                )
            if exc_val.stderr.strip():
                self.ui.console.print(
                    Panel.fit(Text.from_ansi(exc_val.stderr.strip()), title="stderr"),
                    markup=True,
                )
            sys.exit(1)

        # Fallback for any other exception
        if issubclass(exc_type, Exception):
            self.ui.progress.stop()
            self.ui.console.print(
                f"claudia error: {exc_val}", style="bold red", markup=False
            )
            sys.exit(1)

        # Don't suppress non-Exception exceptions (e.g. BaseException subclasses)
        return False


class UI:
    def __init__(self, *, history_file, debug=False):
        self.progress = Progress(
            TextColumn("Claudia >", style="magenta"),
            TextColumn("{task.description}", style="cyan"),
            SpinnerColumn("simpleDots", style="cyan"),
            transient=True,
        )
        self.task_id = self.progress.add_task("", total=None)
        self.console = Console()
        self.history = FileHistory(history_file)
        self._debug = debug

    def start(self):
        self.progress.start()

    @classmethod
    def from_env(cls):
        return cls(
            history_file=os.environ.get(
                "CLAUDIA_HISTORY", os.path.expanduser("~/.claudia_history")
            ),
            debug=os.environ.get("CLAUDIA_DEBUG") in ["1", "true"],
        )

    def show_loading(self, text):
        """Set the spinner description text immediately.

        Unlike the ``loading`` context manager, this sets the text and
        keeps it visible until ``clear_loading`` is called. Useful for
        callback-based patterns where the caller controls timing.
        """
        self.progress.update(self.task_id, description=text)

    def clear_loading(self):
        """Clear the spinner description text."""
        self.progress.update(self.task_id, description="")

    @contextmanager
    def loading(self, text):
        """Show a spinner with the given description while the context is active.

        The description is cleared when the context exits, so the spinner
        returns to a clean state between operations.
        """
        self.show_loading(text)
        try:
            yield
        finally:
            self.clear_loading()

    def debug(self, text):
        if self._debug:
            self.progress.stop()
            self.console.print(text, style="dim")
            self.progress.start()

    def info(self, header, text):
        self.progress.stop()
        self.console.print(Panel.fit(Text(text, no_wrap=False), title=header))
        self.progress.start()

    def catch(self):
        return UICatch(ui=self)

    def ask_diff(self, diff, stat=None):
        self.progress.stop()
        self.console.print(
            f"{stat}.", style="magenta"
        )

        # Loop until the user makes a decision (y/n).
        # 'o' opens the diff in a pager and then re-prompts.
        while True:
            bindings = KeyBindings()
            result = {"apply": False, "done": False}

            @bindings.add("y")
            def _(event):
                result["apply"] = True
                result["done"] = True
                event.app.exit()

            @bindings.add("n")
            def _(event):
                result["apply"] = False
                result["done"] = True
                event.app.exit()

            @bindings.add("o")
            def _(event):
                event.app.exit()

            try:
                prompt("Apply? [y/n/o] ", key_bindings=bindings)
            except (EOFError, KeyboardInterrupt):
                result["done"] = True
                result["apply"] = False

            if result["done"]:
                break

            # User pressed 'o': show the diff in a pager, then loop back
            with self.console.pager(styles=True):
                self.console.print(Syntax(diff, "diff", theme="ansi_dark"))

        self.progress.start()
        return result["apply"]

    def diff_applied_msg(self, cmd, dir):
        self.answer(f"{dir}$ {cmd}")

    def answer(self, answer):
        self.progress.stop()
        self.console.print(
            Text.assemble(("Claudia > ", "bold magenta"), (answer, ""))
        )
        self.progress.start()

    def prompt(self):
        self.progress.stop()
        try:
            from prompt_toolkit.formatted_text import HTML

            p = prompt(HTML("<ansiblue>You > </ansiblue>"), history=self.history)
        except (EOFError, KeyboardInterrupt):
            return None
        self.progress.start()
        return p

    def bye(self):
        self.answer("Goodbye!")
        self.progress.stop()

    def hello(self):
        self.answer("Hello, how can I help?")
