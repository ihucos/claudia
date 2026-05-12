

Claudia is a command-line tool that uses DeepSeek's language models to implement code changes in your git repository based on natural language task descriptions.

## Usage

```bash
export DEEPSEEK_API_KEY=your_key_here
uvx claudia "Add email verification to the login form"

# Interactive mode
uvx claudia
```

## Why?
Speed and cost. About two orders of magnitude cheaper than claude.


## Requirements

- Python 3.10+
- A DeepSeek API key (`DEEPSEEK_API_KEY` environment variable)
- Git
- Universal Ctags (for project analysis)
