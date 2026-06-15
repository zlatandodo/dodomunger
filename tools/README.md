# Tools

Deterministic Python scripts. Each tool does **one** well-defined job (an API call,
a transform, a file/db operation) and is callable from the command line.

## Conventions

- Load secrets from `.env` via `python-dotenv` — never hardcode keys.
- Read inputs from CLI args / stdin; write results to `.tmp/` or stdout.
- Exit non-zero on failure and print a clear error message.
- Keep each tool small, testable, and independent of the others.

## Template

```python
"""<tool_name>.py — one-line description of what this tool does."""
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    # do the one job
    ...

if __name__ == "__main__":
    main()
```
