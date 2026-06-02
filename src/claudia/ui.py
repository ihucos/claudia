import sys
import os
import subprocess

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
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
        if exc_type is not None:
            try:
                raise
            except subprocess.CalledProcessError as exc:
                self.ui.progress.stop()
                self.ui.console.print(
                    f"claudia error: {exc}", style="bold red", markup=False
                )
                if exc.stdout.strip():
                    self.ui.console.print(
                        Panel.fit(Text.from_ansi(exc.stdout.strip()), title="stdout"),
                        markup=True,
                    )
                if exc.stderr.strip():
                    self.ui.console.print(
                        Panel.fit(Text.from_ansi(exc.stderr.strip()), title="stderr"),
                        markup=True,
                    )
                sys.exit(1)
            except Exception as exc:
                self.ui.progress.stop()
                self.ui.console.print(
                    f"claudia error: {exc}", style="bold red", markup=False
                )
                sys.exit(1)


class LoadingCtx:
    def __init__(self, exit_cb):
        self.exit_cb = exit_cb

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        # self.exit_cb()


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

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        self.progress.stop()

    @classmethod
    def from_env(cls):
        return cls(
            history_file=os.environ.get(
                "CLAUDIA_HISTORY", os.path.expanduser("~/.claudia_history")
            ),
            debug=os.environ.get("CLAUDIA_DEBUG") in ["1", "true"],
        )

    def loading(self, text):
        self.progress.update(self.task_id, description=text)
        return LoadingCtx(self.progress.stop)

    def debug(self, text):
        if self._debug:
            self.progress.stop()
            self.console.print(text, style="dim")
            self.progress.start()

    def info(self, header, text):
        self.progress.stop()
        self.console.print(Panel.fit(Text.from_markup(text), title=header))
        self.progress.start()

    def catch(self):
        return UICatch(ui=self)

    def ask_diff(self, diff):
        # Show the diff in a pager, with synatax hilighting
        # and line numbers
        self.progress.stop()
        with self.console.pager(styles=True):
            self.console.print(Syntax(diff, "diff", theme="ansi_dark"))

        self.answer(r"Apply diff? \[y/n] (n)")
        inp = self.prompt()
        self.progress.start()
        apply = inp in ["y", "Y", "yes", "Yes"]
        if not apply:
            self.answer("Diff not applied.")

    def diff_applied_msg(self):
        self.answer("Diff applied.")

    def answer(self, answer):
        self.progress.stop()
        self.console.print(f"[magenta]Claudia >[/magenta] {answer}")
        self.progress.start()

    def prompt(self):
        self.progress.stop()
        try:
            from prompt_toolkit.formatted_text import HTML

            p = prompt(HTML("<ansiblue>You > </ansiblue>"), history=self.history)
        except (EOFError, KeyboardInterrupt):
            return None
        self.loading("")
        self.progress.start()
        return p

    def bye(self):
        self.answer("Goodbye!")

    def hello(self):
        self.answer("Hello, how can I help?")
