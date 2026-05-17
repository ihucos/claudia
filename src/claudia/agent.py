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


model = models.DeepSeekChat("deepseek-v4-flash")
model.supports_tools = True

console = Console()

workspace = tempfile.mkdtemp(dir=os.path.expanduser("~/.claudia-workspace"))


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

    def __call__(self, text):
        self.progress.update(self.task_id, description=text)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        self.progress.start()

    def __enter__(self):
        self.progress.stop()


spinner = Spinner()
spinner.start()


def run(command):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=workspace,
    )

    output = []
    for line in process.stdout:
        # sys.stdout.write(line)
        output.append(line)

    returncode = process.wait()
    if len(output) > 512:
        return {"error": "Output too long (you get 512 chars max)"}, returncode
    return "".join(output), returncode


def create_workdir():
    spinner("Creating workdir...")
    try:
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
    except subprocess.CalledProcessError as exc:
        spinner.stop()
        console.print("stodout:", exc.stdout)
        console.print("stderr:", exc.stderr)
        console.print("claudia error:", exc, style="bold red")
        sys.exit(1)


class Toolbox(llm.Toolbox):
    def write_file(self, filename: str, content: str):
        with open(filename, "w") as f:
            f.write(content)

    def read_file(self, filename: str):
        with open(filename, "r") as f:
            return f.read()

    def print(self, message: str):
        print(message)

    def run(self, shell: str, step_description: str):
        try:
            spinner(step_description)
            out = run(
                [
                    "limactl",
                    "--log-level",
                    "error",
                    "shell",
                    "alpine6",
                    "sudo",
                    "sh",
                    "-c",
                    shell,
                ]
            )
            return out
        except Exception as exc:
            print(exc)
            sys.exit(0)


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
