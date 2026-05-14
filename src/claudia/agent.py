from rich.console import Console
import os

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
import subprocess
import sys
import llm

from . import utils
from . import models


model = models.DeepSeekChat("deepseek-v4-flash")
model.supports_tools = True

console = Console()


def run(command):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    output = []
    for line in process.stdout:
        sys.stdout.write(line)
        output.append(line)

    returncode = process.wait()
    if len(output) > 512:
        return {"error": "Output too long (you get 512 chars max)"}, returncode
    return "".join(output), returncode


def before_call(tool, tool_call):
    print(f"{tool.name}({tool_call.arguments})")


def after_call(tool, tool_call, tool_result):
    print(f"-> {tool_result.output}")


class Toolbox(llm.Toolbox):
    def __init__(self):
        run(["docker", "run", "-dt", "--name", "claudia", "ubuntu"])

    def write_file(self, filename: str, content: str):
        with open(filename, "w") as f:
            f.write(content)

    def read_file(self, filename: str):
        with open(filename, "r") as f:
            return f.read()

    def run(self, cmd: list):
        input("x")
        if not cmd:
            return {"error": "No command provided"}
        try:
            if not os.path.exists("Dockerfile"):
                return {"error": "Call devbox_build first"}
            current_dir = os.getcwd()
            return run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{current_dir}:{current_dir}:ro",
                    "--workdir",
                    current_dir,
                    "--entrypoint",
                    "/usr/bin/env",
                    "this-claudia-img",
                ]
                + cmd
            )
        except Exception as exc:
            print(exc)
            sys.exit(0)


SYSTEM_PROMPT = """
# Notes
- You are an coding agent.
- Use the tools.

# Application structure
{project_map}
""".strip()


def main():
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
            tools=[Toolbox()],
            system=SYSTEM_PROMPT.format(project_map=utils.get_project_map()),
            before_call=before_call,
            after_call=after_call,
        )

        for token in response:
            console.print(f"[cyan]{token}", end="")
        # console.print(f"[cyan]{response.text()}")
