# Claudia - LLM-Powered Code Assistant

Claudia is a command-line tool that uses DeepSeek's language models to implement code changes in your git repository based on natural language task descriptions.

## Features

- **Context-aware file selection**: Automatically identifies relevant files for your task
- **Interactive mode**: Continuous conversation mode for iterative development
- **Streaming output**: Real-time token streaming from the LLM
- **Change preview**: Shows a git diff before applying changes
- **Project mapping**: Uses ctags to provide the LLM with a structural overview of your codebase

## Usage

```bash
# Single task
python -m claudia.main "Add input validation to the login endpoint"

# Interactive mode
python -m claudia.main
```

## Requirements

- Python 3.10+
- A DeepSeek API key (`DEEPSEEK_API_KEY` environment variable)
- Git repository
- Universal Ctags (for project mapping)
- `prompt-toolkit` (for interactive mode)

## Configuration

Set your API key:
```bash
export DEEPSEEK_API_KEY=your_key_here
```

Optional debug output:
```bash
export CLAUDIA_DEBUG=1
