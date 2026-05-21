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

## Sample output

When run with `opencode-go/deepseek-v4-flash`, the agents produced an
interactive quiz on **Deep Sea Biology** with 5 questions covering the
Mariana Trench, anglerfish, piezolytes, hydrothermal vents, and the
Greenland Shark.

## Bus state

```
collector            build-script     python     active
researcher           topic researcher opencode   active
checker              answer checker   opencode   done
formatter            html formatter   opencode   active
```

Key bus messages:

```
#1  collector -> researcher    Your task: You are the topic researcher...
#2  collector -> checker       Your task: You are the answer checker...
#3  collector -> formatter     Your task: You are the HTML formatter...
#4  researcher -> checker      TOPIC: Deep Sea Biology\nQ1: What is the deepest part...
#5  checker -> formatter       VERIFIED_QUIZ: TOPIC: Deep Sea Biology\nQ1: ...
#6  formatter -> ALL           <!DOCTYPE html>\n<html lang="en">...
```

The full pipeline completed in ~40 seconds with three opencode agents.
