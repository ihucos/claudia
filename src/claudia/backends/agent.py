import subprocess
import os
import llm
import tempfile
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
import shutil

from ..ui import UI
from ..models import DeepSeekChat
from .. import utils


CODER_SYSTEM_PROMPT = """
# Task
You re a Senior Software Architect. Orchestrate and delegate to the provided tools in order to fulfill the requested task.

## Application structure
{project_map}
""".strip()

# =========================

SYSOPS_SYSTEM_PROMPT = """
# Task
You are a SysOps agent.

## Notes
- You can delete any data you want as you are sandboxed.
- This is a temporary devbox.
- Install any tools you need.
- The project is at {workdir}.
- Refuse to edit files
- When possible, execute complete shell scripts rather than commands
- Read and maintain information usefull for future invocations at /sysops_breadcrumbs.txt to make future invocations of sysops more efficient.

## Project files
{project_files}
""".strip()


class DisallowedFilenameError(Exception):
    pass


@contextmanager
def die():
    try:
        yield
    except Exception:
        # Handle the exception exactly like your decorator did
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


class DevBox:
    def __init__(self, *, volume, base_image, workdir):
        self.volume = volume
        self.base_image = base_image
        self.workdir = workdir

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
            [
                "docker",
                "exec",
                "--workdir",
                self.workdir,
                self.name,
            ]
            + cmd,
            capture_output=True,
            text=True,
        )


class RunnerToolbox(llm.Toolbox):
    def __init__(self, *, ui, workdir, devbox):
        self.ui = ui
        self.workdir = workdir
        self.devbox = devbox

    def cmd(self, shell_cmd, step_description):
        with die():
            with self.ui.loading(step_description):
                proc = self.devbox.run(["/bin/sh", "-c", shell_cmd])
                return {
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "exit_status": proc.returncode,
                }


class CoderToolbox(llm.Toolbox):
    def __init__(self, *, ui, workdir, model):
        self.ui = ui
        self.workdir = workdir
        self.model = model

    def _check_filename(self, filename):
        filename = (Path(self.workdir) / Path(self.workdir)).resolve()
        if not filename.is_relative_to(self.workdir):
            raise DisallowedFilenameError(f"Bad filename: {filename}")

    def _read_file(self, filename: str):
        with die():
            self._check_filename(filename)
            # with self.ui.loading(f"Reading {filename}"):
            try:
                with open(os.path.join(self.workdir, filename), "r") as f:
                    return f.read()
            except FileNotFoundError:
                return {"error": "File not found"}
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            except OSError:
                return {"error": f"OSError: {filename}"}

    def read_files(self, filenames: list[str], step_description) -> dict[str, str]:
        with die(), self.ui.loading(step_description):
            files = {}
            for filename in filenames:
                files[filename] = self._read_file(filename)
            return files

    def write_file(self, filename: str, content: str, step_description: str):
        with die(), self.ui.loading(step_description):
            try:
                self._check_filename(filename)
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            with self.ui.loading(step_description):
                full_filename = os.path.join(self.workdir, filename)
                os.makedirs(os.path.dirname(full_filename), exist_ok=True)
                with open(full_filename, "w") as f:
                    f.write(content)

    def copy(self, path: str, dest: str, step_description: str):
        with die(), self.ui.loading(step_description):
            try:
                self._check_filename(path)
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            shutil.copy(path, dest)

    def move(self, path: str, dest: str, step_description: str):
        with die(), self.ui.loading(step_description):
            try:
                self._check_filename(path)
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            shutil.move(path, dest)

    def delete(self, path: str, step_description: str):
        with die(), self.ui.loading(step_description):
            try:
                self._check_filename(path)
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            try:
                shutil.rmtree(path)
            except OSError as exc:
                return {"error": str(exc)}

    def coder(self, prompt: str, step_description: str):
        """
        This tool is used to do any code changes. It is optimized for implementation.
        It works best when given high level instructions.
        Use it to delegate bigger chunks of programming work. Coder cannot move, rename or delete files.
        You can use this tool first, then other editing capabilites for polishing the result.
        """
        with die():
            with self.ui.loading(step_description):
                from . import coder

                files = coder.implement(
                    task=prompt,
                    context_files=coder.get_context_files(self.model, prompt),
                    model=self.model,
                    progress_cb=self.ui.loading,
                )

                errors = {}
                for file, content in files.items():
                    os.makedirs(
                        os.path.dirname(os.path.join(self.workdir, file)), exist_ok=True
                    )
                    try:
                        with open(os.path.join(self.workdir, file), "w") as f:
                            f.write(content)
                    except OSError as exc:
                        errors[file] = str(exc)
                ret = f"Files changed: {', '.join(files.keys())}."
                if errors:
                    ret += f" Errors: {', '.join(errors.keys())}"
                return ret


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
        ["git", "commit", "-m", "Initial commit", "--allow-empty"],
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


def get_diff_shortstat(workdir):
    """Get a git-style shortstat summary from the staged diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--staged", "--shortstat"],
            cwd=workdir,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def apply_diff(dir, diff):
    subprocess.run(
        ["patch", "-p1"],
        cwd=dir,
        check=True,
        capture_output=True,
        text=True,
        input=diff,
    )


def get_tools(*, workdir, devbox, ui, model):
    return [CoderToolbox(ui=ui, workdir=workdir, model=model)]


def run(
    *,
    model=None,
    ui=None,
    get_tools=get_tools,
    system_prompt=CODER_SYSTEM_PROMPT,
    prompt=None,
):
    if ui is None:
        ui = UI.from_env()

    if model is None:
        model = DeepSeekChat("deepseek-v4-flash")

    app_dir = os.getcwd()

    with ui.loading("Initializing workdir"):
        os.makedirs(os.path.join(app_dir, ".claudia"), exist_ok=True)
        workdir = tempfile.mkdtemp(dir=os.path.join(app_dir, ".claudia"))
        with ui.catch():
            init_workdir(app_dir, workdir)

    devbox = DevBox(
        volume=os.path.join(app_dir, ".claudia"),
        base_image="alpine",
        workdir=workdir,
    )

    tools = get_tools(workdir=workdir, devbox=devbox, ui=ui, model=model)

    conversation = model.conversation()

    with ui.catch():
        with ui.loading("Checking if devbox exists"):
            devbox_exists = devbox.exists()
        if not devbox_exists:
            with ui.loading("Creating devbox"):
                devbox.create()
        else:
            with ui.loading("Starting devbox"):
                devbox.start()

    ui.hello()

    while True:
        if prompt is None:
            query = ui.prompt()
            if query is None:
                break
        else:
            query = prompt

        if query.startswith("$ "):
            query = query[len("$ ") :]
            response = conversation.chain(
                query,
                tools=[RunnerToolbox(ui=ui, workdir=workdir, devbox=devbox)],
            )
        else:

            def before_call(tool, tool_call):
                ui.debug(f"{tool.name}({tool_call.arguments})")

            def after_call(tool, tool_call, tool_result):
                ui.debug(f"-> {tool_result.output}")

            response = conversation.chain(
                query,
                tools=tools,
                system=system_prompt.format(project_map=utils.get_project_map()),
                before_call=before_call,
                after_call=after_call,
            )
        answer = response.text()

        ui.answer(answer)

        with ui.loading("Cleaning up"):
            with ui.catch():
                diff = get_diff(workdir)
                stat = get_diff_shortstat(workdir)

            if diff and (prompt is not None or ui.ask_diff(diff, stat=stat)):
                with ui.catch():
                    apply_diff(app_dir, diff)

                    ui.info("app_dir", app_dir)
                    ui.info("workdir", workdir)
                    subprocess.run(
                        ["git", "commit", "-m", "Update"],
                        cwd=workdir,
                        check=True,
                    )

                # ui.progress.stop()
                # ui.diff_applied_msg(cmd="blah", dir=app_dir)

        if prompt is not None:
            break

    ui.bye()
