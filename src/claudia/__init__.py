from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile

from . import tools
from . import utils
from .models import DeepSeekChat
from .ui import UI
from functools import wraps


SYSTEM_PROMPT = """
# Task
You re a Senior Software Architect. Use the provided tools in order to fulfill the requested task.

## Application structure
{project_map}
""".strip()


class ClaudiaPatchMixin:
    def patch(self):
        """
        Utility decorator for hacking
        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(self, *args, **kwargs)

            setattr(self, func.__name__, wrapper)

            return wrapper

        return decorator


class ClaudiaToolDebugMixin:
    def before_call(self, tool, tool_call):
        self.ui.debug(f"{tool.name}({tool_call.arguments})")
        super().before_call(tool, tool_call)

    def after_call(self, tool, tool_call, tool_result):
        self.ui.debug(f"-> {tool_result.output}")
        super().after_call(tool, tool_call, tool_result)


class ClaudiaCoderToolMixin:
    def get_tools(self):
        return [
            tools.CoderToolbox(
                ui=self.ui,
                workdir=self.app_dir,
            )
        ] + super().get_tools()


class ClaudiaDevBoxToolMixin:
    def warmup(self):
        super().warmup()
        with self.ui.loading("Starting devbox"):
            self.devbox = tools.DevBoxToolbox(
                volume=self.app_dir,
                base_image="alpine",
                ui=self.ui,
            )

    def get_tools(self):
        return [self.devbox] + super().get_tools()

    def on_stop(self):
        """Shut down the devbox container deterministically on exit."""
        if hasattr(self, "devbox") and self.devbox is not None:
            self.devbox.close()
            self.devbox = None
        super().on_stop()


class ClaudiaProjectCopyMixin:
    def warmup(self):
        """Set up a sandboxed copy of the project for the LLM to work in."""
        super().warmup()
        self._setup_sandbox()

    def _setup_sandbox(self):
        """Create a temporary copy of the project directory with its own git history.

        The LLM writes to this isolated copy. On approval, changes are
        synced back to the real directory as a diff.
        """
        self.real_app_dir = self.app_dir
        sandbox = tempfile.mkdtemp()
        try:
            with self.ui.catch(), self.ui.loading("Syncing dir"):
                subprocess.run(
                    [
                        "rsync",
                        "--archive",
                        "--filter=:- .gitignore",
                        "--exclude",
                        ".git",
                        "--exclude",
                        ".claudia",
                        f"{self.real_app_dir}/.",
                        sandbox,
                    ],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        "git",
                        "init",
                        "--initial-branch=main",
                    ],
                    cwd=sandbox,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "add", "."],
                    cwd=sandbox,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit", "--allow-empty"],
                    cwd=sandbox,
                    check=True,
                    capture_output=True,
                )
            self.app_dir = Path(sandbox)
            self.copied_app_dir = Path(sandbox)
        except BaseException:
            # Clean up the temp dir if anything goes wrong during setup
            subprocess.run(["rm", "-rf", sandbox], capture_output=True)
            raise

    def ask_diff(self, diff, stat=None):
        return self.ui.ask_diff(diff, stat=stat)

    @contextmanager
    def _reset_on_error(self):
        """Context manager that discards changes if any step fails.

        Wraps the apply-and-commit phase so that if any step raises,
        the copied directory is reset to a clean state before the
        exception propagates. This keeps the logic in one place
        instead of repeating try/except/raise blocks for each step.
        """
        try:
            yield
        except Exception:
            self._discard_changes()
            raise

    def after_response(self):
        """Process changes made by the LLM in the copied directory.

        Computes the diff, asks the user whether to apply it, and either
        applies it to the real directory or discards the changes.

        On failure the copied directory is always reset to a clean state
        so the next prompt cycle can start fresh regardless of what went
        wrong.
        """
        with self.ui.catch(), self.ui.loading("Cleaning up"):
            diff, stat = self.get_diff()
            if not diff:
                return

            if not self.ask_diff(diff, stat=stat):
                self._discard_changes()
                return

            # User approved: apply the diff to the real directory and
            # commit in the sandbox. If either step fails, the context
            # manager resets the sandbox automatically.
            with self._reset_on_error():
                self.apply_diff(diff)
                subprocess.run(
                    ["git", "commit", "-m", "Update"],
                    cwd=self.copied_app_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )

    def _discard_changes(self):
        """Discard all uncommitted changes in the copied directory.

        Reverts both staged and unstaged modifications, and removes
        untracked files and directories. After this the working tree
        matches the last commit exactly, so the next call to
        ``get_diff`` starts fresh regardless of what the LLM did.
        """
        subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            cwd=self.copied_app_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=self.copied_app_dir,
            check=True,
            capture_output=True,
            text=True,
        )

    def get_diff(self):
        """Compute staged diff and shortstat from the copied app directory.

        Stages all changes first, then captures the diff.

        Returns a tuple of (diff_text, shortstat_text).
        """
        subprocess.run(
            ["git", "add", "."],
            cwd=self.copied_app_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            ["git", "diff", "--staged"],
            cwd=self.copied_app_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        diff = result.stdout
        # Only run shortstat if there are changes
        if diff:
            stat_result = subprocess.run(
                ["git", "diff", "--staged", "--shortstat"],
                cwd=self.copied_app_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            stat = stat_result.stdout.strip()
        else:
            stat = ""

        return diff, stat

    def apply_diff(self, diff):
        subprocess.run(
            ["git", "apply"],
            cwd=self.real_app_dir,
            check=True,
            capture_output=True,
            text=True,
            input=diff,
        )


class BaseClaudia:
    def __init__(
        self,
        *,
        system_prompt=None,
        ui=None,
        model=None,
        app_dir=None,
    ):
        self.system_prompt = system_prompt or self.get_system_prompt()
        self.ui = ui or self.get_ui()
        self.model = model or self.get_model()
        self._app_dir = app_dir

    def get_app_dir(self):
        if self._app_dir is not None:
            return self._app_dir
        return Path.cwd().resolve()

    def on_response(self, response):
        self.ui.answer(response)

    def get_ui(self):
        return UI.from_env()

    def get_model(self):
        return DeepSeekChat("deepseek-v4-flash")

    def get_system_prompt(self):
        return SYSTEM_PROMPT.format(project_map=utils.get_project_map())

    def get_prompts(self):
        while True:
            prompt = self.ui.prompt()
            # None signals the user wishes to exit (e.g. Ctrl+D)
            if prompt is None:
                break
            yield prompt

    def warmup(self):
        self.app_dir = Path(self.get_app_dir())

    def on_stop(self):
        self.ui.bye()

    def get_tools(self):
        return []

    def get_conversation(self):
        return self.model.conversation()

    def answer(self, prompt):
        response = self.conversation.chain(
            prompt,
            tools=self.tools,
            system=self.system_prompt,
            before_call=self.before_call,
            after_call=self.after_call,
        )
        return response.text()

    def start(self):
        try:
            self.ui.start()
            self.warmup()
            self.tools = self.get_tools()
            self.conversation = self.get_conversation()
            self.ui.hello()
            for prompt in self.get_prompts():
                response = self.answer(prompt)
                self.on_response(response)
                self.after_response()
        except KeyboardInterrupt:
            pass
        self.on_stop()

    def _tool_display_name(self, tool):
        """Extract a user-friendly short name from a tool.

        Each toolbox class can define a ``tool_prefix`` class attribute
        (e.g. 'coder', 'shell') to provide a concise display name.
        Falls back to the tool name as-is if no prefix is defined.
        """
        implementation = getattr(tool, "implementation", None)
        if implementation is not None:
            prefix = getattr(implementation, "tool_prefix", None)
            if prefix:
                return prefix
        return tool.name

    def before_call(self, tool, tool_call):
        name = self._tool_display_name(tool)
        descr = tool_call.arguments.get("step_description", "No description")
        self.ui.show_loading(f"\\[{name}] {descr}")

    def after_call(self, tool, tool_call, tool_result):
        self.ui.clear_loading()


class Claudia(
    ClaudiaToolDebugMixin,
    ClaudiaDevBoxToolMixin,
    ClaudiaCoderToolMixin,
    ClaudiaProjectCopyMixin,
    ClaudiaPatchMixin,
    BaseClaudia,
):
    pass


def main():
    Claudia().start()
