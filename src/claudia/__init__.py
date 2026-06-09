import subprocess
import os
from .devbox import DevBox
from .ui import UI
from .models import DeepSeekChat
from pathlib import Path
import tempfile


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


class ClaudiaToolsMxin:
    def get_tools(self):
        devbox = DevBox(
            volume=self.app_dir,
            base_image="alpine",
        )

        with self.ui.catch():
            with self.ui.loading("Checking if devbox exists"):
                devbox_exists = devbox.exists()
            if not devbox_exists:
                with self.ui.loading("Creating devbox"):
                    devbox.create()
            else:
                with self.ui.loading("Starting devbox"):
                    devbox.start()

            with self.ui.loading("Devbox health check"):
                devbox.run("true").returncode == 0

            asdf
            # return get_tools(workdir=workdir, devbox=devbox, ui=ui, model=model)
        tools = [tool1, tool2]
        tools.extend(super().get_tools())
        return tools


class ProjectCopyMixin:
    # def get_app_dir(self):
    #     return self.copied_app_dir

    def on_start(self):
        self.real_app_dir = self.get_app_dir()
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
        super().on_start()

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
    def __init__(self, system_prompt=None, ui=None, model=None):
        self.system_prompt = system_prompt or self.get_system_prompt()
        self.ui = ui or self.get_ui()
        self.model = model or self.get_model()

    def get_app_dir(self):
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

    def on_start(self):
        self.ui.hello()

    def on_stop(self):
        self.ui.bye()

    def get_tools(self):
        return []

    def get_conversation(self):
        return self.model.conversation()

    def get_response(self, conversation, prompt):
        response = conversation.chain(
            prompt,
            tools=self.get_tools(),
            system=self.get_system_prompt(),
            before_call=self.before_call,
            after_call=self.after_call,
        )
        return response.text()

    def start(self):
        self.on_start()
        conversation = self.get_conversation()
        while True:
            prompt = self.ask_prompt()
            response = self.get_response(conversation, prompt)
            self.on_response(response)
            self.after_response()
            asdf
        self.on_stop()


class Claudia(
    ClaudiaToolDebugMixin,
    ClaudiaToolsMxin,
    ProjectCopyMixin,
    BaseClaudia,
):
    pass


Claudia().start()
