# data-to-chart — Collaborative Data Analysis & Visualization

Three agents (fetcher → analyst → plotter) collaborate via the a2a bus to
produce sample data, analyze it, and render ASCII charts.

## How it works

1. **fetcher** — Generates sample CSV data (e.g., CPU temperature over time,
   server response times, or simulated stock prices). Sends raw data to analyst.

2. **analyst** — Reads the CSV data, computes stats (min, max, avg, trend,
   percentiles). Sends structured analysis + chart-ready series to plotter.

3. **plotter** — Generates ASCII line charts from the data series using a
   pure-Python charting module that requires no external dependencies.
   Broadcasts the formatted chart + analysis summary.

## Output

| File | Description |
|------|-------------|
| `output/charts.txt` | ASCII charts generated from the data |
| `output/analysis.md` | Statistical analysis with findings and methodology |
| `output/bus-state.txt` | Raw bus message log for debugging |

## Running

```bash
python3 examples/artifacts/data-to-chart/build.py --cli opencode --project my-chart
```

With a specific model:
```bash
python3 examples/artifacts/data-to-chart/build.py --cli opencode --model opencode/deepseek-v4-flash-free
```

## Requirements

- `a2a` and `a2a-spawn` on PATH
- `opencode`, `claude`, or `pi` AI CLI (or none — fallback uses direct generation)

## Resilience

If agents cannot produce output (API key limits, etc.), the build script
generates data, computes statistics, and produces ASCII charts directly.
The `output/` directory is always populated, even under degraded conditions.
