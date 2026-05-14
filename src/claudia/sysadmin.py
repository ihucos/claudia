from . import models
from rich.console import Console
import os

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
import subprocess
import sys
import llm


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
    def devbox_read_current_dockerfile(self) -> str:
        try:
            with open("Dockerfile", "r") as f:
                return f.read()
        except FileNotFoundError:
            return "# TODO: Implement"
        except Exception as exc:
            print(exc)
            sys.exit(0)

    def devbox_build(self, dockerfile_text: str):
        try:
            old_dockerfile = self.devbox_read_current_dockerfile()

            with open("Dockerfile", "w") as f:
                f.write(dockerfile_text)
            out, exit_code = run(
                [
                    "docker",
                    "build",
                    "-f",
                    "Dockerfile",
                    "-t",
                    "this-claudia-img",
                    ".",
                ]
            )
            if exit_code != 0:
                # Rollback to working file
                with open("Dockerfile", "w") as f:
                    f.write(old_dockerfile)
                return {"error": "Writing failed, could not build image", "output": out}

            return "Build successful"
        except Exception as exc:
            print(exc)
            sys.exit(0)

    def devbox_run(self, cmd: list):
        input(">")
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
                    # "--read-only",
                    "--entrypoint",
                    "/usr/bin/env",
                    "this-claudia-img",
                ]
                + cmd
            )
        except Exception as exc:
            print(exc)
            sys.exit(0)


# if os.path.exists("Dockerfile"):
#     # Make sure whe are synced with the Dockerfile
#     out, exit_code = run(
#         [
#             "docker",
#             "build",
#             "-f",
#             "Dockerfile",
#             "-t",
#             "this-claudia-img",
#             ".",
#         ]
#     )
#     if exit_code != 0:
#         print(
#             "Current Dockerfile could be bad (Could not build it), you might want to delete it."
#         )
#         print(out)

# print(Toolbox().run_with_dockerfile(["ls", "-la"]))


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
            system="You are a coding agent. Setup the devbox as you want. Use alpine if possible. The app is at the current working directory.",
            before_call=before_call,
            after_call=after_call,
        )

        console.print(f"[cyan]{response.text()}")
