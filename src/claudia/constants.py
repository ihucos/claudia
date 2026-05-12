import re


CODEBLOCK = "\n```"
ESCAPED_CODEBLOCK = "\n ```"

# This is a marker used to detect files in llm output
DUMMY_DIR = "github_repository"

# Compiled regex for file path detection
FILE_PATH_PATTERN = re.compile(rf"({DUMMY_DIR}/[\w/.-]+)")


PROMPT_IMPLEMENT_TEMPLATE = """
# Persona
You are a senior software developer.

# Project overview
```
{project_map}
```

# Implement
{task}

# Notes
- Emit the whole file contents of files you want to edit as their content will be directly replaced with your content.
- Always emmit the full file path, even when you are editing only one file.
- Only emmit the file path and the file contents, don't reason.
"""

PROMPT_CONTEXT_TEMPLATE = """
# Task
List files thath are relevant to the task.

## Task
{task}

## Project overview
```
{project_map}
```

## Notes
- Emit the full file path including the '{dummy_dir}' prefix.
"""
