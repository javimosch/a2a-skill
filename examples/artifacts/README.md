# Collaborative Artifact Smoke Tests

This directory contains **collaborative artifact smoke tests** — self-contained
build scripts that demonstrate a2a's peer-to-peer messaging bus by having
teams of AI agents produce real, tangible output files.

## What is an artifact?

An artifact is a concrete file (HTML page, SVG image, Python script) produced
by a team of AI agents communicating exclusively via the a2a bus. Each agent:

1. Registers on the bus
2. Receives a task via the bus
3. Communicates with peers via send/recv
4. Contributes its piece to the final artifact
5. Marks itself done

The **build script** orchestrates the process: it initializes the bus, spawns
agents via `a2a-spawn`, sends tasks, waits for results, and writes the final
output to `output/`.

## Available artifacts

| Artifact | Agents | Output | Description |
|----------|--------|--------|-------------|
| `landing-page/` | designer, copywriter, integrator | `output/index.html` | 3 agents collaborate to produce a SaaS landing page |
| `svg-banner/` | designer, reviewer | `output/banner.svg` | 2 agents iterate on an SVG banner through critique rounds |
| `mini-cli/` | architect, implementer | `output/tasky.py` | 2 agents spec and implement a Python CLI tool |
| `config-generator/` | architect, implementer | `output/docker-compose.yml`, `output/nginx.conf`, `output/.env.example` | 2 agents produce a full server deployment configuration |
| `color-palette/` | colorist, generator | `output/index.html` | 2 agents propose a color palette and render an HTML preview |
| `quiz-generator/` | researcher, checker, formatter | `output/index.html` | 3 agents collaborate to produce an interactive HTML quiz page |
| `docker-compose-generator/` | specifier, writer | `output/docker-compose.yml`, `output/README.md` | 2 agents spec and write a 5-service Docker stack with README |

## Requirements

To run an artifact build script, you need:

- **a2a** and **a2a-spawn** on your PATH (or the repo root)
- One of the supported AI CLIs:
  - `claude` (Anthropic)
  - `opencode` (Codex CLI)
  - `pi` (Pi)

## Running

```bash
# From the repo root:
python3 examples/artifacts/landing-page/build.py --cli opencode --project artifact-landing

# Or with a specific model:
python3 examples/artifacts/svg-banner/build.py --cli claude --model haiku

# Custom project name:
python3 examples/artifacts/mini-cli/build.py --cli pi --model sonnet

# Recommended: opencode with opencode-go/deepseek-v4-flash:
python3 examples/artifacts/quiz-generator/build.py --cli opencode --model opencode-go/deepseek-v4-flash
```

Output goes to `examples/artifacts/<name>/output/` (checked in).

## Architecture

All build scripts use shared utility code from `examples/artifacts/_util.py`:

- `find_a2a()` / `find_spawn()` — locate the binaries
- `run_a2a()` / `run_a2a_json()` — CLI wrappers
- `spawn_agent()` — launches AI agents via `a2a-spawn`
- `make_kit()` — builds kit prompts following the standard pattern
- `strip_html_preamble()` — strips agent preamble text from HTML output
- `SpawnManager` — tracks PIDs and cleans up on exit
- `wait_for_messages()` — collects results from the bus

## Adding a new artifact

1. Create `examples/artifacts/<name>/build.py` (under 200 lines)
2. Create `examples/artifacts/<name>/README.md`
3. Add to the table above
4. Add a `output/` gitignore entry if not already present
5. Test: `python3 examples/artifacts/<name>/build.py`

See the [examples/AGENTS.md](/examples/AGENTS.md) for agent collaboration patterns.
