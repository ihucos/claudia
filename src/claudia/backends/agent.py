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
        # return {
        #     "stdout": r.stdout.decode(),
        #     "stderr": r.stderr.decode(),
        #     "exit_code": r.returncode,
        # }

    def sync_up(self, src, dst):
        subprocess.run(
            ["docker", "cp", src, f"{self.name}:{dst}"],
            check=True,
            capture_output=True,
        )

    def sync_down(self, src, dst):
        subprocess.run(
            ["docker", "cp", f"{self.name}:{src}", dst],
            check=True,
            capture_output=True,
        )


class Toolbox(llm.Toolbox):
    def __init__(self, *, ui, devbox):
        self.ui = ui
        self.devbox = devbox

    def write_file(self, filename: str, content: str):
        with self.ui.loading(f"Writing {filename}..."):
            ret = self.devbox.run(
                ["sh", "-c", "echo $0 > $1", content, filename],
            )
            if ret.returncode != 0:
                return {"error": ret.stderr}

    def read_file(self, filename: str):
        with self.ui.loading(f"Reading {filename}..."):
            ret = self.devbox.run(
                ["sh", "-c", "cat $0", filename],
            )
            if ret.returncode != 0:
                return {"error": ret.stderr}
            return ret.stdout

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
        app_dir.replace("/", "."),
        "alpine",
    )
    toolbox = Toolbox(ui=ui, devbox=devbox)

    #
    # Prepare the devbox
    #
    if not devbox.exists():
        with ui.loading("Creating devbox..."):
            devbox.create()
    else:
        with ui.loading("Starting devbox..."):
            devbox.start()
    with ui.loading("Syncing container dir..."):
        container_app_dir = devbox.run(["mktemp", "-d"]).stdout.strip()
        devbox.sync_up(app_dir, container_app_dir)

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

        ui.answer(response.text())
    ui.bye()


# def get_ansi_diff_info():
#     with spinner("Checking changes..."):
#         current_branch = subprocess.run(
#             ["git", "branch", "--show-current"], text=True, capture_output=True
#         ).stdout.strip()
#
#         commits = subprocess.run(
#             ["git", "log", "--oneline", "--color=always", f"HEAD...{branch}"],
#             text=True,
#             capture_output=True,
#             check=True,
#         ).stdout.strip()
#
#         # Force color on stat so we get the green '+' and red '-' graphs automatically!
#         stat = subprocess.run(
#             ["git", "diff", "--stat", "--color=always", f"HEAD...{branch}"],
#             text=True,
#             capture_output=True,
#             check=True,
#         ).stdout.strip()
#
#         diff = subprocess.run(
#             ["git", "diff", "--color=always", f"HEAD...{branch}"],
#             text=True,
#             capture_output=True,
#             check=True,
#         ).stdout.strip()
#
#     return {
#         "current_branch": current_branch,
#         "commits": commits,
#         "stat": stat,
#         "diff": diff,
#     }
#
#
# def request_merge():
#     with spinner:
#         diff_info = get_ansi_diff_info()
#         with console.pager(styles=True):
#             console.print(
#                 Panel(
#                     f"[bold blue]Agent is requesting a merge[bold blue]: {branch} -> {diff_info['current_branch']}",
#                     title="Merge Request",
#                     border_style="green",
#                     title_align="left",
#                     padding=(1, 2),
#                 )
#             )
#             console.print(
#                 Panel(
#                     Text.from_ansi(diff_info["commits"]),
#                     title="Commits",
#                     border_style="yellow",
#                     title_align="left",
#                     padding=(1, 2),
#                 )
#             )
#             console.print(
#                 Panel(
#                     Text.from_ansi(diff_info["stat"]),
#                     title="Files",
#                     border_style="cyan",
#                     title_align="left",
#                     padding=(1, 2),
#                 )
#             )
#             console.print(
#                 Panel(
#                     Text.from_ansi(diff_info["diff"]),
#                     title="Diff",
#                     border_style="magenta",
#                     title_align="left",
#                     padding=(1, 1),
#                 )
#             )
#         console.print()
#
#         apply_changes = Confirm.ask(
#             f"[green]Merge {branch} into {diff_info['current_branch']}?[/green]",
#             default=False,
#         )
#         if apply_changes:
#             subprocess.run(["git", "merge", branch], check=True, cwd=git_dir)
#             with spinner:
#                 console.print("[green]Merged[/green]")
#         else:
#             with spinner:
#                 console.print("[red]Not Merged[/red]")
#
#
#
#
# def main():
#     try:
#         create_worktree(workdir)
#         with spinner:
#             console.print(f"[cyan]workdir: {workdir}[/cyan]")
#         spinner("Clouding...")
#         conversation = model.conversation()
#         history = FileHistory(os.path.expanduser("~/.klaus_history"))
#         with spinner:
#             console.print("[cyan]Claudia> Hello, how can I help.")
#         while True:
#             with spinner:
#                 user_input = prompt(
#                     "You> ",
#                     history=history,
#                     prompt_continuation="... ",
#                 )
#
#             if user_input == "breakpoint":
#                 with spinner:
#                     breakpoint()
#                 continue
#
#             response = conversation.chain(
#                 user_input,
#                 after_call=after_call,
#                 before_call=before_call,
#                 tools=[Toolbox()],
#                 system=SYSTEM_PROMPT.format(
#                     project_map=utils.get_project_map(prepend_dummy_dir=False)
#                 ),
#             )
#
#             # for token in response:
#             #     pass
#             # console.print(f"[cyan]{token}", end="")
#             # wait
#             response.text()
#
#             last_response = response._responses[-1]
#             with spinner:
#                 if not last_response.text():
#                     console.print("[cyan]Claudia> ...")
#                 else:
#                     console.print(f"[cyan]Claudia> {last_response.text()}", end="")
#     except (KeyboardInterrupt, EOFError):
#         spinner.stop()
#         console.print("[cyan]Claudia> Goodbye")
