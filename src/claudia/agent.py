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


class Toolbox(llm.Toolbox):
    def __init__(self, status_cb):
        self.status_cb = status_cb

    def _create_workdir(self):
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
        )
        subprocess.run(["git", "stash", "-u"], check=True)
        subprocess.run(["git", "stash", "apply", "--index"], check=True)
        subprocess.run(["git", "stash", "apply", "--index"], check=True, cwd=workspace)

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
            self.status_cb(step_description)
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
    conversation = model.conversation()
    history = FileHistory(os.path.expanduser("~/.klaus_history"))
    console.print("[cyan]Claudia> Hello, here to help.")
    while True:
        user_input = prompt(
            "You> ",
            history=history,
            prompt_continuation="... ",
        )

        progress = Progress(
            SpinnerColumn(), TextColumn("{task.description}"), transient=True
        )
        update_progress = lambda x: progress.update(task_id, description=x)
        task_id = progress.add_task("Spinning...", total=None)
        toolbox = Toolbox(update_progress)
        toolbox._create_workdir()
        update_progress("Spinning...")
        progress.start()

        response = conversation.chain(
            user_input,
            tools=[toolbox],
            system=SYSTEM_PROMPT.format(project_map=utils.get_project_map()),
        )

        for token in response:
            pass
            # console.print(f"[cyan]{token}", end="")
        progress.stop()

        last_response = response._responses[-1]
        console.print(f"[cyan]Claudia> {last_response.text()}", end="")
