# Workflow: <name>

> SOP template. Copy this file, rename it, and fill in each section.
> Write in plain language — as if briefing a teammate.

## Objective
What this workflow accomplishes and why. One or two sentences.

## Trigger / When to run
When this should be executed (e.g. "every Monday", "on demand when X").

## Required inputs
- `input_name` — description, format, where it comes from
- ...

## Tools used
List the scripts in `tools/` this workflow calls, in order.
- `tools/<script>.py` — what it does, key arguments

## Steps
1. Step one — which tool, expected result.
2. Step two — ...
3. ...

## Expected outputs
- Where the deliverable lands (cloud service, file, etc.)
- Format and what "done" looks like

## Edge cases & failure handling
- What can go wrong, and how to recover
- Known constraints (rate limits, timing quirks, auth gotchas)

## Notes / lessons learned
Update this section as the workflow evolves.
