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
import hashlib
import shutil

from . import utils
from . import models

# DOCKER_EXIT_CODES = [125, 126]


def hash(obj):
    return hashlib.sha256(repr(obj).encode("utf-8")).hexdigest()


model = models.DeepSeekChat("deepseek-v4-flash")
model.supports_tools = True

# MAKE IT THE GIT DIR!

console = Console()

git_dir = os.getcwd()
workdirs = os.path.realpath(".claudia/workdirs")
os.makedirs(workdirs, exist_ok=True)
workdir = tempfile.mkdtemp(dir=workdirs, prefix="")


def debug(text):
    if os.environ.get("CLAUDIA_DEBUG") in ["1", "true"]:
        with spinner:
            console.print(text, style="dim")


def before_call(tool, tool_call):
    debug(f"{tool.name}: {tool_call.arguments}")


def after_call(tool, tool_call, tool_result):
    debug(f"-> {tool_result.output}")


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
    def __init__(self, project_name, base_image, *, extra_docker_args, workdir):
        self.project_name = project_name
        self.base_image = base_image
        self.extra_docker_args = extra_docker_args
        self.workdir = workdir

    @property
    def name(self):
        return f"claudia-{self.project_name}-{self.base_image}-{hash(self.extra_docker_args)}"

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
                ]
                + list(self.extra_docker_args)
                + [
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
                ["docker", "exec", "--workdir", self.workdir, self.name] + cmd,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
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


devbox = DevBox(
    "here",
    "alpine",
    extra_docker_args=["--volume", f"{workdirs}:{workdirs}"],
    workdir=workdir,
)
devbox.create_if_not_exists()


def create_synced_worktree(workdir):
    with spinner("Creating worktree..."):
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "-f",
                workdir,
                "-b",
                f"claudia-{os.path.basename(workdir)}",
            ],
            check=True,
            capture_output=True,
        )
        out = subprocess.run(
            ["git", "status", "--porcelain", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        for line in out.splitlines():
            status, path = line.split(None, 1)
            source_path = os.path.join(git_dir, path)
            target_path = os.path.join(workdir, path)
            if status == "M":
                shutil.copyfile(source_path, target_path)
                debug(f"shutil.copyfile({source_path}, {target_path})")
            elif status == "A":
                debug(f"shutil.copyfile({source_path}, {target_path})")
            else:
                debug("skipping git status line: " + line)

        # subprocess.run(["git", "stash", "-u"], check=True, capture_output=True)
        # subprocess.run(
        #     ["git", "stash", "apply", "--index"], check=True, capture_output=True
        # )
        # subprocess.run(
        #     ["git", "stash", "apply", "--index"],
        #     check=True,
        #     cwd=workdir,
        #     capture_output=True,
        # )


class Toolbox(llm.Toolbox):
    def write_file(self, filename: str, content: str, step_description: str):
        with spinner(step_description):
            try:
                with open(os.path.join(workdir, filename), "w") as f:
                    f.write(content)
            except OSError as exc:
                return {"error": str(exc)}

    def read_file(self, filename: str, step_description: str):
        with spinner(step_description):
            try:
                with open(os.path.join(workdir, filename), "r") as f:
                    return f.read()
            except OSError as exc:
                return {"error": str(exc)}

    def run(self, shell: str, step_description: str):
        with spinner(step_description):
            ret = devbox.run(["/bin/sh", "-c", shell])
            if (len(ret["stderr"]) + len(ret["stdout"])) > (1024 * 10):
                return {
                    "error": f"Output too long (you get {1024 * 10} chars max)",
                }
            return ret


SYSTEM_PROMPT = """
# Notes
- You are an coding agent.
- Use the tools.
- Install any software you need to accomplish the task.

# Application structure
{project_map}
""".strip()


def main():
    try:
        create_synced_worktree(workdir)
        with spinner:
            console.print(f"[cyan] workdir: {workdir}[/cyan]")
        spinner("Clouding...")
        conversation = model.conversation()
        history = FileHistory(os.path.expanduser("~/.klaus_history"))
        with spinner:
            console.print("[cyan]Claudia> Hello, how can I help.")
        while True:
            with spinner:
                user_input = prompt(
                    "You> ",
                    history=history,
                    prompt_continuation="... ",
                )

            if user_input == "breakpoint":
                with spinner:
                    breakpoint()
                continue

            response = conversation.chain(
                user_input,
                after_call=after_call,
                before_call=before_call,
                tools=[Toolbox()],
                system=SYSTEM_PROMPT.format(
                    project_map=utils.get_project_map(prepend_dummy_dir=False)
                ),
            )

            # for token in response:
            #     pass
            # console.print(f"[cyan]{token}", end="")
            # wait
            response.text()

            last_response = response._responses[-1]
            with spinner:
                if not last_response.text():
                    console.print("[cyan]Claudia> ...")
                else:
                    console.print(f"[cyan]Claudia> {last_response.text()}", end="")
    except (KeyboardInterrupt, EOFError):
        spinner.stop()
        console.print("[cyan]Claudia> Goodbye")
        subprocess.run(["git", "stash", "-u"], cwd=workdir)
        sys.exit(130)
