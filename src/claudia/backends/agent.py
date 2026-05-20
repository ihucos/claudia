import difflib
import subprocess
import os
import llm
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax
import tempfile

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

    def run(self, cmd, *, workdir="/"):
        return subprocess.run(
            [
                "docker",
                "exec",
                "--workdir",
                workdir,
                self.name,
            ]
            + cmd,
            capture_output=True,
            text=True,
        )


class Toolbox(llm.Toolbox):
    def __init__(self, *, ui, devbox, workdir):
        self.ui = ui
        self.devbox = devbox
        self.workdir = workdir

    def write_file(self, filename: str, content: str):
        with self.ui.loading(f"Writing {filename}"):
            with open(os.path.join(self.workdir, filename), "w") as f:
                f.write(content)

    def read_file(self, filename: str):
        with self.ui.loading(f"Reading {filename}"):
            with open(os.path.join(self.workdir, filename), "r") as f:
                return f.read()

    def run(self, shell: str, step_description: str):
        with self.ui.loading(step_description):
            ret = self.devbox.run(["/bin/sh", "-c", shell], workdir=self.workdir)
            if (len(ret.stderr) + len(ret.stdout)) > (1024 * 10):
                return {
                    "error": f"Output too long (you get {1024 * 10} chars max)",
                }
            return {
                "stdout": ret.stdout,
                "stderr": ret.stderr,
                "exit_code": ret.returncode,
            }


def init_workdir(app_dir, workdir):
    subprocess.run(
        [
            "rsync",
            "--archive",
            "--filter=:- .gitignore",
            "--exclude",
            ".git",
            "--exclude",
            ".claudia",
            f"{app_dir}/.",
            workdir,
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "init"],
        cwd=workdir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=workdir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=workdir,
        check=True,
        capture_output=True,
    )
    return workdir


# def get_workdir_diffs(workdir):
#     subprocess.run(
#         ["git", "add", "."],
#         cwd=workdir,
#         check=True,
#         capture_output=True,
#     )
#     try:
#         stat = subprocess.run(
#             ["git", "diff", "--stat", "--staged"],
#             cwd=workdir,
#             check=True,
#             capture_output=True,
#             text=True,
#         )
#     except subprocess.CalledProcessError as exc:
#         if exc.returncode != 1:
#             raise
#
#     diff = subprocess.run(
#         ["git", "diff", "--staged"],
#         cwd=workdir,
#         check=True,
#         capture_output=True,
#         text=True,
#     )
#     return {
#         "stat": stat.stdout.strip(),
#         "diff": diff.stdout.strip(),
#     }


def get_diff(workdir):
    subprocess.run(
        ["git", "add", "."],
        cwd=workdir,
        check=True,
        capture_output=True,
        text=True,
    )
    diff = subprocess.run(
        ["git", "diff", "--staged"],
        cwd=workdir,
        check=True,
        capture_output=True,
        text=True,
    )
    return diff.stdout


def apply_diff(dir, diff):
    subprocess.run(
        ["git", "apply", "-"],
        cwd=dir,
        check=True,
        capture_output=True,
        text=True,
        input=diff,
    )


def run(*, model, ui):
    #
    # Init vars here
    #

    app_dir = os.getcwd()

    with ui.loading("Initializing workdir"):
        os.makedirs(os.path.join(app_dir, ".claudia"), exist_ok=True)
        workdir = tempfile.mkdtemp(dir=os.path.join(app_dir, ".claudia"))
        with ui.catch():
            init_workdir(app_dir, workdir)
        print(workdir)

    conversation = model.conversation()
    devbox = DevBox(
        volume=os.path.join(app_dir, ".claudia"),
        base_image="alpine",
    )
    toolbox = Toolbox(ui=ui, devbox=devbox, workdir=workdir)

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
        # response = conversation.chain(
        #     query,
        #     tools=[toolbox],
        #     system=SYSTEM_PROMPT.format(
        #         project_map=utils.get_project_map(prepend_dummy_dir=False)
        #     ),
        # )
        # answer = response.text()
        answer = toolbox.run(query, step_description="Running query")
        toolbox.write_file("test_file", "asdf\nasdf")

        ui.answer(answer)
        with ui.catch():
            diff = get_diff(workdir)

        if ui.ask_diff(diff):
            with ui.catch():
                apply_diff(workdir, diff)

    ui.bye()
