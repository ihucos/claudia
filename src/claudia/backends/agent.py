import subprocess
import os
import llm
import tempfile
import sys
import traceback
from contextlib import contextmanager

from .. import utils


ROOT_SYSTEM_PROMPT = """
# Task
You re a software architect. Orchestrate the provided tools to fulfill the requested task.

## The `implement` tool
The `implement` is used to do any code changes. It is optimized for implementation. It works best when given high level instructions.

## The `sysops` tool
The `sysops` can run commands against a temporary devbox machine.

## Application structure
{project_map}
""".strip()

# =========================

SYSOPS_SYSTEM_PROMPT = """
# Task
You are a SysOps agent.

## Notes
- This is a temporary devbox.
- The project is at {workdir}.
- Refuse to edit files
- When possible, execute complete shell scripts rather than commands

## Project files
{project_files}
""".strip()


@contextmanager
def die():
    try:
        yield
    except Exception:
        # Handle the exception exactly like your decorator did
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


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
    def __init__(self, *, ui, devbox, workdir, model):
        self.ui = ui
        self.devbox = devbox
        self.workdir = workdir
        self.model = model

    def _check_filename(self, filename):
        if ".." in filename:
            raise ValueError("Filename contains '..'")
        if filename.startswith("/"):
            raise ValueError("Filename starts with '/'")

    def _read_file(self, filename: str):
        with die():
            self._check_filename(filename)
            # with self.ui.loading(f"Reading {filename}"):
            try:
                with open(os.path.join(self.workdir, filename), "r") as f:
                    return f.read()
            except FileNotFoundError:
                return {"error": "File not found"}
            except OSError:
                return {"error": f"OSError: {filename}"}

    def read_files(self, filenames: list[str]) -> dict[str, str]:
        with die():
            with self.ui.loading(f"Reading files: {', '.join(filenames)}"):
                files = {}
                for filename in filenames:
                    files[filename] = self._read_file(filename)
                return files

    def sysops(self, prompt: str, step_description: str):
        with die():
            with self.ui.loading("sysops: " + step_description):
                conversation = self.model.conversation()

                def run_shell_script(script: str) -> str:
                    with self.ui.loading("Executing: " + str(script)):
                        return self.devbox.run(
                            ["sh", "-c", script], workdir=self.workdir
                        )

                response = conversation.chain(
                    prompt,
                    tools=[run_shell_script],
                    system=SYSOPS_SYSTEM_PROMPT.format(
                        workdir=self.workdir,
                        project_files=utils.get_project_files(self.workdir),
                    ),
                )
                answer = response.text()
                return answer

    def implement(self, prompt: str, context_files: list[str], step_description: str):
        with die():
            print()
            print(prompt)
            print("====")
            with self.ui.loading(f"coder: {step_description} {context_files}"):
                from . import coder

                files = coder.implement(
                    task=prompt,
                    context_files=context_files,
                    model=self.model,
                    progress_cb=self.ui.loading,
                )

                # diff = coder.make_diff(files, self.workdir)
                for file, content in files.items():
                    with open(os.path.join(self.workdir, file), "w") as f:
                        os.makedirs(os.path.dirname(file), exist_ok=True)
                        f.write(content)
                return f"Files changed: {', '.join(files.keys())}"


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

    conversation = model.conversation()
    devbox = DevBox(
        volume=os.path.join(app_dir, ".claudia"),
        base_image="alpine",
    )
    toolbox = Toolbox(ui=ui, devbox=devbox, workdir=workdir, model=model)

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
            system=ROOT_SYSTEM_PROMPT.format(project_map=utils.get_project_map()),
        )
        answer = response.text()

        ui.answer(answer)

        with ui.loading("Cleaning up"):
            with ui.catch():
                diff = get_diff(workdir)

            if diff and ui.ask_diff(diff):
                with ui.catch():
                    apply_diff(app_dir, diff)
                ui.diff_applied_msg()

    ui.bye()
