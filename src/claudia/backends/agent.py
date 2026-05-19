from time import sleep
import subprocess
import os
import tempfile
import shlex
import sys
import llm

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
    def __init__(self, project_name, base_image):
        self.project_name = project_name
        self.base_image = base_image

    @property
    def name(self):
        return f"claudia-{self.project_name}-{self.base_image}"

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
                "--name",
                self.name,
                self.base_image,
            ],
            check=True,
            capture_output=True,
        )

    def run(self, cmd, workdir="/"):
        return subprocess.run(
            ["docker", "exec", "--workdir", workdir, self.name] + cmd,
            capture_output=True,
            text=True,
        )

    def sync_up(self, src, dst):
        subprocess.run(
            ["docker", "cp", f"{src}/.", f"{self.name}:{dst}/."],
            check=True,
            capture_output=True,
        )

    def sync_down(self, src, dst):
        subprocess.run(
            ["docker", "cp", f"{self.name}:{src}/.", dst],
            check=True,
            capture_output=True,
        )


class Toolbox(llm.Toolbox):
    def __init__(self, *, ui, devbox, workdir="/"):
        self.ui = ui
        self.devbox = devbox
        self.workdir = workdir

    def write_file(self, filename: str, content: str):
        with self.ui.loading(f"Writing {filename}"):
            ret = self.devbox.run(
                ["sh", "-c", 'echo "$0" > "$1"', content, filename],
                workdir=self.workdir,
            )
            if ret.returncode != 0:
                return {"error": ret.stderr}

    def read_file(self, filename: str):
        with self.ui.loading(f"Reading {filename}"):
            ret = self.devbox.run(
                ["sh", "-c", 'cat "$0"', filename],
                workdir=self.workdir,
            )
            if ret.returncode != 0:
                return {"error": ret.stderr}
            return ret.stdout

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


class NoIgnoredFiles:
    def __init__(self, dir):
        self.dir = dir

    def __enter__(self):
        self._tmpdir_obj = tempfile.TemporaryDirectory()
        tmpdir = self._tmpdir_obj.__enter__()
        subprocess.run(
            [
                "rsync",
                "--archive",
                "--filter",
                ":- .gitignore",
                "--exclude",
                ".git",
                self.dir + "/",  # '/' - copy the contents
                tmpdir,
            ],
            check=True,
            capture_output=True,
        )
        return tmpdir

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._tmpdir_obj.__exit__(exc_type, exc_val, exc_tb)


def diff_dirs(dir_a, dir_b):
    with NoIgnoredFiles(dir_a) as a, NoIgnoredFiles(dir_b) as b:
        try:
            # We run the command inside `cwd=a` so everything in 'a' is relative.
            # We pass 'b' as a relative path from 'a' using os.path.relpath.
            rel_b = os.path.relpath(b, start=a)

            res = subprocess.run(
                [
                    "git",
                    "diff",
                    "--no-index",
                    "--stat",
                    "--relative",  # Forces relative pathing in stats
                    "--src-prefix=A/",  # Clean prefix for source
                    "--dst-prefix=B/",  # Clean prefix for destination
                    rel_b,  # Target B (path to the other temp dir)
                    ".",  # Target A (current directory)
                ],
                text=True,
                capture_output=True,
                cwd=a,
                check=True,  # Raises CalledProcessError on changes (exit code 1)
            )
            out = res.stdout.strip()
        except subprocess.CalledProcessError as exc:
            # Git returns exit code 1 when differences are found.
            # We want to grab the stdout from that 'error'.
            if exc.returncode == 1:
                out = exc.stdout.strip()
            else:
                raise
        return out


def run(*, model, ui):
    #
    # Init vars here
    #
    app_dir = os.path.realpath(".")
    conversation = model.conversation()
    devbox = DevBox(
        app_dir.replace("/", "."),
        "alpine",
    )
    with ui.loading("Creating app dir"):
        container_app_dir = devbox.run(["mktemp", "-d"]).stdout.strip()
    toolbox = Toolbox(ui=ui, devbox=devbox, workdir=container_app_dir)

    #
    # Prepare the devbox
    #
    with ui.loading("Checking if devbox exists"):
        devbox_exists = devbox.exists()
    if not devbox_exists:
        with ui.loading("Creating devbox"):
            devbox.create()
    else:
        with ui.loading("Starting devbox"):
            devbox.start()
    with ui.loading("Syncing container dir"):
        with NoIgnoredFiles(app_dir) as stripped_app_dir:
            devbox.sync_up(stripped_app_dir, container_app_dir)

    #
    # Say hello
    #
    ui.hello()

    #
    # Loop
    #
    while True:
        # query = ui.prompt()
        # if query is None:
        #     break
        # response = conversation.chain(
        #     query,
        #     tools=[toolbox],
        #     system=SYSTEM_PROMPT.format(
        #         project_map=utils.get_project_map(prepend_dummy_dir=False)
        #     ),
        # )
        # answer = response.text()
        toolbox.write_file("test_file", "contents")
        answer = "file written"

        with ui.loading("Syncing container dir"):
            tmpdir = tempfile.TemporaryDirectory()
            devbox.sync_down(container_app_dir, tmpdir.name)
            ui.info("downed app dir", tmpdir.name)
            ui.info("container app dir", container_app_dir)

            with ui.catch():
                diff = diff_dirs(tmpdir.name, app_dir)

            ui.info("Changes", diff)

            # with ui.catch():
            #     ui.progress.stop()
            #     subprocess.run(
            #         [
            #             "git",
            #             "diff",
            #             "--no-index",
            #             app_dir,
            #             tmpdir.name,
            #             "--diff-filter=AM",
            #         ],
            #     )
            #     ui.progress.start()

        ui.answer(answer)

        from time import sleep

        sleep(100000000)

        # if git_stat.returncode == 1:
        # ui.info("Changes", git_stat.stdout.strip())
    ui.bye()
