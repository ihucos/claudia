from time import sleep
import subprocess
import os
import tempfile
import shlex
import sys
import llm

from ..ui import UI


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
            self.devbox.run(
                ["sh", "-c", "echo $0 > $1", content, filename],
            )

    def read_file(self, filename: str):
        with self.ui.loading(f"Reading {filename}..."):
            return self.devbox.run(
                ["sh", "-c", "cat $0", filename],
            )

    def run(self, shell: str, step_description: str):
        with self.ui.loading(step_description):
            ret = self.devbox.run(["/bin/sh", "-c", shell])
            if (len(ret["stderr"]) + len(ret["stdout"])) > (1024 * 10):
                return {
                    "error": f"Output too long (you get {1024 * 10} chars max)",
                }
            return ret


def main(*, model: llm.Model, ui: UI):
    app_dir = os.path.realpath(".")

    devbox = DevBox(
        app_dir.replace("/", "."),
        "alpine",
    )

    with UI.from_env() as ui:
        if not devbox.exists():
            with ui.loading("Creating devbox..."):
                devbox.create()
        else:
            with ui.loading("Starting devbox..."):
                devbox.start()

        with ui.loading("Syncing container dir..."):
            container_app_dir = devbox.run(["mktemp", "-d"]).stdout.strip()
            devbox.sync_up(app_dir, container_app_dir)

        ui.hello()
        while True:
            query = ui.prompt()
            if query is None:
                break
            ui.loading("calculating...")
            sleep(1)
            ui.answer("echo: " + query)
        ui.bye()


#
# devbox.create_if_not_exists()
#
# branch = f"claudia-{os.path.basename(workdir)}"
#
#
# def create_worktree(workdir):
#     with spinner("Creating worktree..."):
#         subprocess.run(
#             [
#                 "git",
#                 "worktree",
#                 "add",
#                 "-f",
#                 workdir,
#                 "-b",
#                 branch,
#             ],
#             check=True,
#             capture_output=True,
#         )
#
#
# class Toolbox(llm.Toolbox):
#     def write_file(self, filename: str, content: str, step_description: str):
#         with spinner(step_description):
#             try:
#                 with open(os.path.join(workdir, filename), "w") as f:
#                     f.write(content)
#             except OSError as exc:
#                 return {"error": str(exc)}
#
#     def read_file(self, filename: str, step_description: str):
#         with spinner(step_description):
#             try:
#                 with open(os.path.join(workdir, filename), "r") as f:
#                     return f.read()
#             except OSError as exc:
#                 return {"error": str(exc)}
#
#     def run(self, shell: str, step_description: str):
#         with spinner(step_description):
#             ret = devbox.run(["/bin/sh", "-c", shell])
#             if (len(ret["stderr"]) + len(ret["stdout"])) > (1024 * 10):
#                 return {
#                     "error": f"Output too long (you get {1024 * 10} chars max)",
#                 }
#             return ret
#
#     def commit(self, commit_msg: str, add_files: list[str]):
#         with spinner:
#             console.print(f"[green]committing: {commit_msg.splitlines()[0]}[/green]")
#         with spinner("Committing changes..."):
#             subprocess.run(
#                 ["git", "add"] + add_files,
#                 check=True,
#                 cwd=workdir,
#                 capture_output=True,
#             )
#             subprocess.run(
#                 ["git", "commit", "-m", commit_msg],
#                 check=True,
#                 cwd=workdir,
#                 capture_output=True,
#             )
#
#     def request_merge(self):
#         request_merge()
#
#
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
# SYSTEM_PROMPT = """
# # Notes
# - You are an coding agent.
# - Use the tools.
# - Install any software you need to accomplish the task.
# - Commit when your have completed a single, logical unit of work.
# - Call the request_merge() function when you want to request a merge of your commits. This must be done at the end of an task that involves commits.
#
# # Application structure
# {project_map}
# """.strip()
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
