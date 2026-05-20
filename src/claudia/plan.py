import llm
import json
import sys
import questionary
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from . import utils

from . import models

PROMPT_TEMPLATE = """
# Task
I need a three-sentence implementation instruction.

# Project overview
```
{project_map}
```

## Task
{task}

# Notes
- Understand project conventions by reading files.
- Feel free to ask clarification questions if necessary
"""


class Planner:
    def __init__(self):
        self.model = models.DeepSeekChat("deepseek-v4-flash")
        self.model.supports_tools = True
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        )
        self.progress.add_task("[cyan]Planning...", total=None)
        self.progress.start()
        self.questions_answers = {}

    def readFiles(self, files: list[str]) -> dict[str, str]:
        """Read files"""
        self.progress.update(
            0, description=f"[cyan]Analyzing files: {', '.join(files)}"
        )
        contents = {}
        for file in files:
            with open(file) as f:
                contents[file] = f.read()
        return contents

    def multipleChoiceQuestion(self, question: str, choices: list[str]) -> int:
        """Ask a question to the developer and product owner."""
        self.progress.stop()
        q = questionary.select(question, choices=choices, use_shortcuts=True).ask()
        self.progress.start()
        self.questions_answers[question] = q
        return q

    def plan(self, task):
        prompt = PROMPT_TEMPLATE.format(project_map=utils.get_project_map(), task=task)

        conversation = self.model.conversation()
        response = conversation.chain(
            prompt,
            tools=[self.readFiles, self.multipleChoiceQuestion],
        )

        print(response.text())
        return response.text()


def main():
    task = " ".join(sys.argv[1:])
    p = Planner()
    p.plan(task)
    from pprint import pprint

    pprint(p.questions_answers)
    print()
