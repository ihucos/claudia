import os
import subprocess
import sys
import time
import tempfile

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console
import llm

from . import utils
from . import models

# DOCKER_EXIT_CODES = [125, 126]


model = models.DeepSeekChat("deepseek-v4-flash")
model.supports_tools = True

console = Console()

workspace = tempfile.mkdtemp(dir=os.path.expanduser("~/.claudia-workspace"))

DEBUG = False


def before_call(tool, tool_call):
    if DEBUG:
        with spinner:
            print(f"{tool.name}: {tool_call.arguments}")


def after_call(tool, tool_call, tool_result):
    if DEBUG:
        with spinner:
            print(f"-> {tool_result.output}")


class ExceptionHandler:
    def __init__(self):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            try:
                raise
            except subprocess.CalledProcessError as exc:
                spinner.stop()
                console.print("stodout:", exc.stdout)
                console.print("stderr:", exc.stderr)
                console.print("claudia error:", exc, style="bold red")
                sys.exit(1)
            except Exception as exc:
                spinner.stop()
                console.print("claudia error:", exc, style="bold red")
                sys.exit(1)


class Spinner:
    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(), TextColumn("{task.description}"), transient=True
        )
        self.task_id = self.progress.add_task("Spinning...", total=None)

    def stop(self):
        self.progress.stop()

    def start(self):
        self.progress.start()

    def __call__(self, text, die_on_error=True):
        self.progress.update(self.task_id, description=f"[cyan]{text}[/cyan]")
        if die_on_error:
            return ExceptionHandler()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        self.progress.start()

    def __enter__(self):
        self.progress.stop()


spinner = Spinner()
spinner.start()


class DevBox:
    def __init__(self, project_name, base_image):
        self.project_name = project_name
        self.base_image = base_image

    @property
    def name(self):
        return f"claudia-{self.project_name}-{self.base_image}"

    def create_if_not_exists(self):
        with spinner("Checking devbox..."):
            existing_containers = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}"],
                text=True,
                check=True,
                capture_output=True,
            ).stdout.splitlines()
        if self.name not in existing_containers:
            self.create()
        self.start()

    def start(self):
        with spinner("Starting devbox..."):
            subprocess.run(
                ["docker", "start", self.name],
                check=True,
                capture_output=True,
            )

    def create(self):
        with spinner("Creating devbox..."):
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-dti",
                    "--name",
                    self.name,
                    self.base_image,
                ],
                check=True,
                capture_output=True,
            )

    def run(self, cmd):
        try:
            r = subprocess.run(
                ["docker", "exec", self.name] + cmd,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            # if exc.returncode in DOCKER_EXIT_CODES:
            #     raise
            return {
                "stdout": exc.stdout.decode(),
                "stderr": exc.stderr.decode(),
                "exit_code": exc.returncode,
            }
        else:
            return {
                "stdout": r.stdout.decode(),
                "stderr": r.stderr.decode(),
                "exit_code": r.returncode,
            }


devbox = DevBox("here", "alpine")
devbox.create_if_not_exists()


def create_workdir():
    with spinner("Creating workdir..."):
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "-f",
                workspace,
                "-b",
                "new-branch-" + str(time.time()),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "stash", "-u"], check=True, capture_output=True)
        subprocess.run(
            ["git", "stash", "apply", "--index"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "stash", "apply", "--index"],
            check=True,
            cwd=workspace,
            capture_output=True,
        )


class Toolbox(llm.Toolbox):
    def write_file(self, filename: str, content: str, step_description: str):
        with spinner(step_description, die_on_error=False):
            with open(filename, "w") as f:
                f.write(content)

    def read_file(self, filename: str, step_description: str):
        with spinner(step_description, die_on_error=False):
            with open(filename, "r") as f:
                return f.read()

    def print(self, message: str):
        print(message)

    def run(self, shell: str, step_description: str):
        with spinner(step_description):
            return devbox.run(["/bin/sh", "-c", shell])


SYSTEM_PROMPT = """
# Notes
- You are an coding agent.
- Use the tools.
- Install any software you need to accomplish the task.

# Application structure
{project_map}
""".strip()


def main():
    create_workdir()
    spinner("Clouding...")
    conversation = model.conversation()
    history = FileHistory(os.path.expanduser("~/.klaus_history"))
    with spinner:
        console.print("[cyan]Claudia> Hello, here to help.")
    while True:
        with spinner:
            user_input = prompt(
                "You> ",
                history=history,
                prompt_continuation="... ",
            )

        response = conversation.chain(
            user_input,
            after_call=after_call,
            before_call=before_call,
            tools=[Toolbox()],
            system=SYSTEM_PROMPT.format(
                project_map=utils.get_project_map(prepend_dummy_dir=False)
            ),
        )

        for token in response:
            pass
            # console.print(f"[cyan]{token}", end="")

        last_response = response._responses[-1]
        with spinner:
            if not last_response.text():
                console.print("[cyan]Claudia> ...")
            else:
                console.print(f"[cyan]Claudia> {last_response.text()}", end="")
