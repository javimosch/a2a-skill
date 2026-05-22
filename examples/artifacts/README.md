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
| `web-research-report/` | researcher, analyst, writer | `output/report.md`, `output/bus-state.txt` | 3 agents produce a research report using ddgr for live web search |
| `news-briefing/` | curator, narrator | `output/briefing.md`, `output/bus-state.txt` | 2 agents produce a tech news briefing with real ddgr-sourced stories |
| `competitive-analysis/` | searcher, analyst, writer | `output/competitive-analysis.md`, `output/bus-state.txt` | 3 agents produce a competitive analysis with comparison table and market positioning |
| `a2a-landscape/` | searcher, analyst, writer | `output/a2a-landscape.md`, `output/bus-state.txt` | 3 agents research and position a2a-skill against 9 competing multi-agent frameworks |
| `weekly-digest/` | scout, curator, editor | `output/weekly-digest.md`, `output/bus-state.txt` | 3 agents produce a formatted tech news digest via ddgr web research |
|| `data-to-chart/` | fetcher, analyst, plotter | `output/charts.txt`, `output/analysis.md`, `output/bus-state.txt` | 3 agents produce CSV data, statistical analysis, and ASCII charts |
||| `doc-pipeline/` | writer, formatter, publisher | `output/guide.md`, `output/guide.html`, `output/bundle.zip`, `output/bus-state.txt` | 3 agents produce a markdown guide, convert to HTML via pandoc, and bundle into a zip archive |
|| `tech-stack-advisor/` | researcher, recommender | `output/tech-stack-guide.md`, `output/bus-state.txt` | 2 agents research and recommend a technology stack using ddgr web search |

## Requirements

To run an artifact build script, you need:

- **a2a** and **a2a-spawn** on your PATH (or the repo root)
- One of the supported AI CLIs:
  - `claude` (Anthropic)
  - `opencode` (Codex CLI)
  - `pi` (Pi)
- Some artifacts require additional CLI tools (e.g., `ddgr` for `web-research-report/`)

## Running

```bash
# From the repo root:
python3 examples/artifacts/landing-page/build.py --cli opencode --project artifact-landing

# Or with a specific model:
python3 examples/artifacts/svg-banner/build.py --cli claude --model haiku

# Custom project name:
python3 examples/artifacts/mini-cli/build.py --cli pi --model sonnet

# Recommended: opencode with the free DeepSeek V4 Flash model:
python3 examples/artifacts/quiz-generator/build.py --cli opencode --model opencode/deepseek-v4-flash-free
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

## Lessons from the field

For a collection of pitfalls discovered during artifact smoke testing —
agent communication quirks, spawn management gotchas, and build-script design
patterns — see [docs/PITFALLS.md](../../docs/PITFALLS.md).
