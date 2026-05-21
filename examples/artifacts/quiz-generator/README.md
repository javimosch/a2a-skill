# Collaborative Artifact: Interactive Quiz Generator

Three AI agents collaborate to produce a self-contained HTML quiz page on
an educational topic — demonstrating the producer→checker→renderer pipeline
on the a2a bus.

## Agent team

| Agent | Role | Task |
|-------|------|------|
| `researcher` | Topic researcher | Chooses a topic and creates 5 multiple-choice questions |
| `checker` | Answer checker | Validates each answer is correct, approves the quiz |
| `formatter` | HTML formatter | Renders the verified quiz as an interactive HTML page |

## Workflow

1. Researcher picks a topic (space, history, science, etc.) and writes 5 questions
2. Researcher sends the structured quiz to the checker
3. Checker validates each answer — corrects errors or approves
4. Checker sends the verified quiz to the formatter with `VERIFIED_QUIZ:` prefix
5. Formatter creates a self-contained HTML page with clickable quiz + JS answer reveal
6. Formatter broadcasts the final HTML on the bus
7. Build script captures the broadcast and writes `output/index.html`

## Running

```bash
cd /root/projects/a2a-skill
python3 examples/artifacts/quiz-generator/build.py --cli opencode
```

## Output

- `output/index.html` — Self-contained HTML quiz page
- Interactive: radio-button options, "Check Answers" button with green/red highlights
- Valid HTML5 with inline CSS and vanilla JavaScript
- Responsive layout, clean modern design

## Bus transcript

```
STATS:
  Messages: 7+ total
  Agents: 1 collector + 3 worker agents
  Top senders: collector (3), researcher (1), checker (1), formatter (1+)

CONVERSATION:
  #1 collector -> researcher: Task: Choose a topic and create 5 quiz questions
  #2 collector -> checker: Task: Validate the quiz answers
  #3 collector -> formatter: Task: Render verified quiz as HTML
  #4 researcher -> checker: Quiz: 5 multiple-choice questions on <topic>
  #5 checker -> formatter: VERIFIED_QUIZ: ... (approved quiz data)
  #6 formatter -> ALL: <!DOCTYPE html>... (complete HTML quiz page)
```

## What demonstrates a2a

- **Three-stage pipeline**: producer → validator → renderer, each stage dependent on the previous
- **Structured handoffs**: `VERIFIED_QUIZ:` prefix marks validated deliverables on the bus
- **Validation gate**: checker ensures quality before the expensive HTML rendering step
- **Bus as source of truth**: the final HTML is broadcast and captured from the bus
- **a2a-spawn integration**: three agents launched with role-specific kit prompts
