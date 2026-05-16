from rich.console import Console
import os

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
import subprocess
import sys
import llm
import time
import tempfile

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


def before_call(tool, tool_call):
    pass
    # print(f"{tool.name}({tool_call.arguments})")


def after_call(tool, tool_call, tool_result):
    pass
    # print(f"-> {tool_result.output}")


class Toolbox(llm.Toolbox):
    def __init__(self):
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
            print(step_description)
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
            subprocess.check_call(["docker", "commit", "claudia", "claudia"])
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
    toolbox = Toolbox()
    conversation = model.conversation()
    history = FileHistory(os.path.expanduser("~/.klaus_history"))
    while True:
        user_input = prompt(
            "> ",
            history=history,
            prompt_continuation="... ",
        )
        response = conversation.chain(
            user_input,
            tools=[toolbox],
            system=SYSTEM_PROMPT.format(project_map=utils.get_project_map()),
            before_call=before_call,
            after_call=after_call,
        )

        for token in response:
            pass
            # console.print(f"[cyan]{token}", end="")
        # console.print(f"[cyan]{response.text()}")
