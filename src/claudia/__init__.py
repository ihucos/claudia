from pathlib import Path
import subprocess
import tempfile
import sys

from . import tools
from .models import DeepSeekChat
from .ui import UI


SYSTEM_PROMPT = """
# Task
You re a Senior Software Architect. Use the provided tools in order to fulfill the requested task.

## Application structure
{project_map}
""".strip()


class ClaudiaToolDebugMixin:
    def before_call(self, tool, tool_call):
        self.ui.debug(f"{tool.name}({tool_call.arguments})")
        super().before_call(tool, tool_call)

    def after_call(self, tool, tool_call, tool_result):
        self.ui.debug(f"-> {tool_result.output}")
        super().after_call(tool, tool_call, tool_result)


# class ClaudiaToolsMxin:
#     def get_tools(self):
#         devbox = DevBox(
#             volume=self.app_dir,
#             base_image="alpine",
#         )
#
#         with self.ui.catch():
#             with self.ui.loading("Checking if devbox exists"):
#                 devbox_exists = devbox.exists()
#             if not devbox_exists:
#                 with self.ui.loading("Creating devbox"):
#                     devbox.create()
#             else:
#                 with self.ui.loading("Starting devbox"):
#                     devbox.start()
#
#             with self.ui.loading("Devbox health check"):
#                 devbox.run("true").returncode == 0
#
#             asdf
#             # return get_tools(workdir=workdir, devbox=devbox, ui=ui, model=model)
#         tools = [tool1, tool2]
#         tools.extend(super().get_tools())
#         return tools


class ClaudiaCoderToolsMixin:
    def get_tools(self):
        return [
            tools.CoderToolbox(
                ui=self.ui,
                workdir=self.app_dir,
                model=self.model,
            )
        ] + super().get_tools()


class ProjectCopyMixin:
    # def get_app_dir(self):
    #     return self.copied_app_dir

    def get_app_dir(self):
        self.real_app_dir = super().get_app_dir()
        self.copied_app_dir = tempfile.mkdtemp()
        with self.ui.catch(), self.ui.loading("Initializing workdir"):
            subprocess.run(
                [
                    "rsync",
                    "--archive",
                    "--filter=:- .gitignore",
                    "--exclude",
                    ".git",
                    "--exclude",
                    ".claudia",
                    f"{self.real_app_dir}/.",
                    self.copied_app_dir,
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                """git init; git add .; git commit -m "Initial commit" --allow-empty""",
                cwd=self.copied_app_dir,
                shell=True,
                check=True,
                capture_output=True,
            )
        return self.copied_app_dir

    def ask_diff(self, diff, stat=None):
        return self.ui.ask_diff(diff, stat=stat)

    def after_response(self):
        with self.ui.catch(), self.ui.loading("Cleaning up"):
            diff, stat = self.get_diff()
            if not diff:
                return
            if self.ask_diff(diff, stat=stat):
                self.apply_diff(diff)
                subprocess.run(
                    ["git", "commit", "-m", "Update"],
                    cwd=self.copied_app_dir,
                    check=True,
                )

    def get_diff(self):
        subprocess.run(
            ["git", "add", "."],
            cwd=self.copied_app_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        diff = subprocess.run(
            ["git", "diff", "--staged"],
            cwd=self.copied_app_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        yield diff.stdout

        result = subprocess.run(
            ["git", "diff", "--staged", "--shortstat"],
            cwd=self.copied_app_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        yield result.stdout.strip()

    def apply_diff(self, diff):
        subprocess.run(
            ["patch", "-p1"],
            cwd=self.real_app_dir,
            check=True,
            capture_output=True,
            text=True,
            input=diff,
        )


# class BaseClaudia:


class BaseClaudia:
    def __init__(
        self, *, system_prompt=None, ui=None, model=None, loop=None, app_dir=None
    ):
        self.system_prompt = system_prompt or self.get_system_prompt()
        self.ui = ui or self.get_ui()
        self.model = model or self.get_model()
        self.loop = loop if loop is None else self.get_loop()

        self._app_dir = app_dir

    def get_app_dir(self):
        if self._app_dir is not None:
            return self._app_dir
        return Path.cwd().resolve()

    def on_response(self, response):
        self.ui.answer(response)

    def get_ui(self):
        return UI.from_env()

    def get_model(self):
        return DeepSeekChat("deepseek-v4-flash")

    def get_system_prompt(self):
        return SYSTEM_PROMPT

    def ask_prompt(self):
        return self.ui.prompt()

    def get_loop(self):
        return self.loop

    def warmup(self):
        self.app_dir = Path(self.get_app_dir())
        self.tools = self.get_tools()
        self.ui.hello()

    def on_stop(self):
        self.ui.bye()

    def get_tools(self):
        return []

    def get_conversation(self):
        return self.model.conversation()

    def answer(self, prompt):
        response = self.conversation.chain(
            prompt,
            tools=self.tools,
            system=self.get_system_prompt(),
            before_call=self.before_call,
            after_call=self.after_call,
        )
        return response.text()

    def start(self):
        try:
            self.warmup()
            self.conversation = self.get_conversation()
            while True:
                prompt = self.ask_prompt()
                response = self.answer(prompt)
                self.on_response(response)
                self.after_response()
                if not self.get_loop():
                    break
        except KeyboardInterrupt:
            pass
        self.on_stop()

    def before_call(self, tool, tool_call):
        return

    def after_call(self, tool, tool_call, tool_result):
        return


class Claudia(
    ClaudiaToolDebugMixin,
    # ClaudiaToolsMxin,
    ClaudiaCoderToolsMixin,
    ProjectCopyMixin,
    BaseClaudia,
):
    pass


def main():
    Claudia().start()
