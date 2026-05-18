# Installation Guide

This guide covers setting up a2a for different platforms and use cases.

## Prerequisites

- Python 3.7+ with built-in `sqlite3` module
- ~50MB disk space for database (grows with usage)
- POSIX-compatible shell (bash, zsh, sh)

## Quick Install

The recommended way:

```bash
cd /path/to/a2a-skill
./install.sh
```

This symlinks the CLI and skill to standard locations:
- `~/.local/bin/a2a` — CLI command
- `~/.local/bin/a2a-spawn` — Multi-CLI launcher
- `~/.claude/skills/a2a` — Claude Code skill
- `~/.agents/skills/a2a` — Cross-CLI skills

Restart your CLI session so it picks up the new skill.

## Manual Installation

If you prefer not to run the installer:

```bash
# CLI commands
ln -sf "$PWD/a2a"      ~/.local/bin/a2a
ln -sf "$PWD/a2a-spawn" ~/.local/bin/a2a-spawn

# Skills
mkdir -p ~/.claude/skills ~/.agents/skills
ln -sf "$PWD" ~/.claude/skills/a2a
ln -sf "$PWD" ~/.agents/skills/a2a
```

## Python Client Library

To use the Python API in your projects:

```bash
# Copy to your project
cp a2a_client.py /path/to/your/project/

# Or install from source (if packaged)
pip install a2a-client
```

Then import it:

```python
from a2a_client import A2AClient

client = A2AClient(project="my-project", agent_id="alice")
client.send("bob", "Hello!")
```

## Platform-Specific Notes

### macOS

The system Python often lacks sqlite3. Use Homebrew:

```bash
brew install python3
# or use system python3.8+ which includes sqlite3
```

### Linux

Most distributions include Python with sqlite3:

```bash
# Ubuntu/Debian
apt-get install python3

# Fedora/RHEL
dnf install python3

# Alpine
apk add python3
```

### Windows (WSL2)

Install Python via WSL package manager:

```bash
# Ubuntu on WSL2
apt-get install python3

# Then proceed with Quick Install above
```

### Verifying Python Setup

Check if your Python has sqlite3:

```bash
python3 -c "import sqlite3; print('✓ sqlite3 available')"
```

If not available, the `a2a` wrapper will auto-detect and find one that does.

## Environment Setup

Optional: Set default project name globally

```bash
export A2A_PROJECT="my-project"
a2a init  # Creates database at ~/.a2a/my-project/database.db
```

## Verifying Installation

Test your setup:

```bash
a2a --version          # Should show help
a2a init               # Initialize first project
a2a register alice     # Register a test agent
a2a list               # Should show 'alice'
a2a send alice "test"  # Send message to self
a2a recv --as alice    # Should receive the message
```

## Troubleshooting

**"a2a: command not found"**
- Verify symlink exists: `ls -la ~/.local/bin/a2a`
- Check PATH: `echo $PATH | grep .local/bin`
- Restart your shell or run: `source ~/.bashrc`

**"No Python 3 with sqlite3 found"**
- Run: `python3 -c "import sqlite3"`
- Install Python with sqlite3 (see Platform-Specific Notes)
- Or set: `export A2A_CLI=/path/to/python3-with-sqlite3`

**"Permission denied" on `a2a-spawn`**
- Make executable: `chmod +x ~/.local/bin/a2a-spawn`

**Database locked errors**
- Usually temporary (concurrent writes)
- SQLite handles this automatically with WAL mode
- If persistent, check for hung `a2a` processes: `ps aux | grep a2a`

**Messages not appearing**
- Check agent registration: `a2a list`
- Verify recipient exists: `a2a register bob`
- Try verbose: `a2a recv --as alice --json`

## Uninstalling

Remove symlinks:

```bash
rm ~/.local/bin/a2a
rm ~/.local/bin/a2a-spawn
rm ~/.claude/skills/a2a
rm ~/.agents/skills/a2a
```

Databases persist at `~/.a2a/` for recovery. Delete if needed:

```bash
rm -rf ~/.a2a/
```

## Docker Deployment

For containerized deployment:

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y git
RUN git clone https://github.com/anthropics/a2a-skill /app/a2a
WORKDIR /app/a2a
RUN ./install.sh
ENV A2A_PROJECT=container-test
CMD ["/bin/bash"]
```

## Next Steps

After installation:

- Read [QUICKSTART.md](QUICKSTART.md) for 5-minute introduction
- Check [examples/](examples/) for pattern implementations
- Review [CLIENT_API.md](CLIENT_API.md) for Python API
- See [AGENTS.md](AGENTS.md) for agent development
