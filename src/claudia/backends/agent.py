import difflib
import subprocess
import os
import llm
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax

from .. import utils

SYSTEM_PROMPT = """
# Task
You are a coding agent.

## Notes
- Use the tools.
- Install any software you need to accomplish the requested task.

## Application structure
{project_map}
""".strip()


class DevBox:
    def __init__(self, *, volume, base_image):
        self.volume = volume
        self.base_image = base_image

    @property
    def name(self):
        return f"claudia-{self.volume.replace('/', '_')}-{self.base_image}"

    def start_or_create(self):
        if not self.exists():
            self.create()
        else:
            self.start()

    def exists(self):
        existing_containers = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            text=True,
            check=True,
            capture_output=True,
        ).stdout.splitlines()
        return self.name in existing_containers

    def start(self):
        subprocess.run(
            ["docker", "start", self.name],
            check=True,
            capture_output=True,
        )

    def create(self):
        subprocess.run(
            [
                "docker",
                "run",
                "-dti",
                "--volume",
                f"{self.volume}:{self.volume}",
                "--name",
                self.name,
                self.base_image,
            ],
            check=True,
            capture_output=True,
        )

    def run(self, cmd):
        return subprocess.run(
            ["docker", "exec", "--workdir", self.volume, self.name] + cmd,
            capture_output=True,
            text=True,
        )


class Toolbox(llm.Toolbox):
    def __init__(self, *, ui, devbox):
        self.ui = ui
        self.devbox = devbox

    def write_file(self, filename: str, content: str):
        with self.ui.loading(f"Writing {filename}"):
            # Read existing content (if any) to compute diff
            old_content = ""
            try:
                with open(filename, "r") as f:
                    old_content = f.read()
            except FileNotFoundError:
                old_content = ""

            # Compute the diff
            diff_lines = list(
                difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=filename,
                    tofile=filename,
                )
            )
            if diff_lines:
                diff_text = "".join(diff_lines)
                self.ui.progress.stop()
                syntax = Syntax(diff_text, "diff", theme="ansi_dark", line_numbers=True)
                self.ui.console.print(Panel(syntax, title="Diff"))
                self.ui.progress.start()
            else:
                self.ui.info("Diff", f"No changes to {filename}")

            # Write the file
            with open(filename, "w") as f:
                f.write(content)

    def read_file(self, filename: str):
        with self.ui.loading(f"Reading {filename}"):
            with open(filename, "r") as f:
                return f.read()

    def run(self, shell: str, step_description: str):
        with self.ui.loading(step_description):
            ret = self.devbox.run(["/bin/sh", "-c", shell])
            if (len(ret.stderr) + len(ret.stdout)) > (1024 * 10):
                return {
                    "error": f"Output too long (you get {1024 * 10} chars max)",
                }
            return {
                "stdout": ret.stdout,
                "stderr": ret.stderr,
                "exit_code": ret.returncode,
            }


def run(*, model, ui):
    #
    # Init vars here
    #
    app_dir = os.path.realpath(".")
    conversation = model.conversation()
    devbox = DevBox(
        volume=app_dir,
        base_image="alpine",
    )
    toolbox = Toolbox(ui=ui, devbox=devbox)

    #
    # Prepare the devbox
    #
    with ui.catch():
        with ui.loading("Checking if devbox exists"):
            devbox_exists = devbox.exists()
        if not devbox_exists:
            with ui.loading("Creating devbox"):
                devbox.create()
        else:
            with ui.loading("Starting devbox"):
                devbox.start()

    #
    # Say hello
    #
    ui.hello()

    #
    # Loop
    #
    while True:
        query = ui.prompt()
        if query is None:
            break
        response = conversation.chain(
            query,
            tools=[toolbox],
            system=SYSTEM_PROMPT.format(
                project_map=utils.get_project_map(prepend_dummy_dir=False)
            ),
        )
        answer = response.text()

        ui.answer(answer)

    ui.bye()
