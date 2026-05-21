# Collaborative Artifact: Interactive Quiz Generator

Three AI agents collaborate to produce a self-contained HTML quiz page on
an educational topic — demonstrating the producer→checker→renderer pipeline
on the a2a bus.

## How it works

| Agent | Role | Task |
|-------|------|------|
| **researcher** | Topic researcher | Chooses an educational topic and creates 5 multiple-choice quiz questions |
| **checker** | Answer checker | Verifies each answer is correct; approves or requests fixes |
| **formatter** | HTML formatter | Receives the verified quiz and renders it as an interactive HTML page |

## Pipeline

1. Build script sends tasks to all three agents
2. **researcher** creates a quiz and sends it to **checker**
3. **checker** verifies all answers, then forwards the verified quiz with `VERIFIED_QUIZ:` prefix to **formatter**
4. **formatter** generates a complete HTML page with radio buttons, JavaScript scoring, and modern CSS
5. Build script captures the HTML from the bus and writes `output/index.html`

## Running

```bash
python3 examples/artifacts/quiz-generator/build.py --cli opencode
```

## Output (from opencode build)

- `output/index.html` — 5,954 bytes, interactive HTML5 quiz page
- Topic: **Space Exploration** — 5 questions covering orbital periods, Sputnik 1, James Webb, Titan, Apollo 11
- JavaScript scoring with Check Answers / Reset buttons, correct (green) / wrong (red) highlighting
- All answers verified correct by the checker agent before formatting

## Bus state (from opencode build)

```
STATS:
  Messages: 6 total (5 direct + 1 broadcast)
  Agents: 1 collector + 3 worker agents
  Top senders: collector (3), researcher (1), checker (1), formatter (1)

TIMELINE:
  t+0s   collector -> researcher: "Create 5 MCQ quiz on an educational topic"
  t+0s   collector -> checker: "Verify each answer is correct, then forward"
  t+0s   collector -> formatter: "Wait for verified quiz, then render HTML"
  t+11s  researcher -> checker: "TOPIC: Space Exploration\nQ1: Mercury (shortest orbit)... Q5: Apollo 11"
  t+18s  checker -> formatter: "VERIFIED_QUIZ: TOPIC: Space Exploration\n(all 5 answers correct ✓)"
  t+28s  formatter -> ALL: <!DOCTYPE html>... (interactive quiz with radio buttons + JS scoring)
```
