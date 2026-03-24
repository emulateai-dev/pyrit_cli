# pyrit-cli

**pyrit-cli** is a command-line tool for security workshops and authorized red-teaming with [PyRIT](https://azure.github.io/PyRIT/). It wraps common flows: credential setup, dataset and converter discovery, single-turn and multi-turn attacks, TAP, optional HTTP victims, and an **`ask-ai`** helper that uses bundled documentation plus a chat API to suggest commands.

Use only on systems, data, and models you are **authorized** to test.

**Workshop cheatsheet (AISecWorkshops):** [`labs/llms/red-teaming/jailbreaks/pyrit_cli_cheatsheet.md`](https://github.com/emulateai-dev/AISecWorkshops/blob/main/labs/llms/red-teaming/jailbreaks/pyrit_cli_cheatsheet.md) — one-page commands for datasets, jailbreak templates, converters, scorers, and red-team flows. Full reference: bundled **`src/pyrit_cli/HELP.md`** (also shown by tooling / `ask-ai`).

## Requirements

- **Python** 3.10–3.13 (see `requires-python` in `pyproject.toml`)
- API access to any LLM providers you target (OpenAI, Groq, Ollama, etc., depending on flags)
- A [PyRIT](https://github.com/Azure/PyRIT)-compatible install (pulled in as a dependency)

## Install

**Default (recommended): with Makefile**

From this repository root:

```bash
make venv-install
make venv-update
make uv-install
make uv-update
```

Use `make venv-install` / `make venv-update` when working inside the project `.venv`.

**Second option: with uv**

venv + pip interface:

```bash
uv venv && uv pip install -e .
```

Install `pyrit-cli` on your PATH (like `pipx`):

```bash
uv tool install --editable .
```

Reinstall after git pull: `uv tool install --editable --force .`. Remove: `uv tool uninstall pyrit-cli`.

With the submodule lockfile: `uv sync` (installs into the project `.venv` when using uv's project layout).

**Alternative: with pip**

```bash
git clone git@github.com:emulateai-dev/pyrit_cli.git
cd pyrit_cli
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

**Developers** (tests + lint):

```bash
pip install -e .
```

**With Poetry** (activate **your** workshop venv — e.g. `poetry shell` from your lab project — then from this repo directory)

```bash
cd /path/to/pyrit_cli   # this repository root
pip install -e .
```

Phoenix/OpenTelemetry and Hugging Face dataset support are installed by default.

**From PyPI** *(if published)*

```bash
pip install pyrit-cli
```

## Quick start

1. Configure environment (interactive wizard; writes under `~/.pyrit/`):

   ```bash
   pyrit-cli setup configure
   ```

2. Check status:

   ```bash
   pyrit-cli setup
   pyrit-cli setup guide
   ```

3. Run a minimal **single-turn** check (adjust `--target` to your model and backend):

   ```bash
   pyrit-cli redteam prompt-sending-attack \
     --target openai:gpt-4o-mini \
     --objective "Reply with exactly: OK"
   ```

If you used an **OpenAI-compatible** wizard (e.g. Groq), the model id in `openai:<model>` must exist on that host (see [HELP.md](src/pyrit_cli/HELP.md) and [docs/workshop-track.md](docs/workshop-track.md)).

## What you can run

| Area | Examples |
|------|----------|
| **Setup** | `pyrit-cli setup`, `setup guide`, `setup configure` |
| **Tool lifecycle** | `pyrit-cli uv-install`, `pyrit-cli uv-update` |
| **Help via LLM** | `pyrit-cli ask-ai "…"` (optional `--http-request-file` / `--http-response-sample`) |
| **Discover** | `targets list`, `datasets list`, `datasets inspect`, `converters list`, `converters list-keys`, `converters run`, `jailbreak-templates list`, `scorers list` |
| **Red team** | `redteam prompt-sending-attack`, `redteam red-teaming-attack`, `redteam tap-attack` |

### Stateless converters on arbitrary text

Same keys as `converters list-keys` / `--request-converter` (repeat `-c` for a stack):

```bash
pyrit-cli converters run -c rot13 "Hello"
echo "plain" | pyrit-cli converters run -c base64
```

### Jailbreak template names (for Python / PyRIT)

Lists YAML basenames used with `pyrit.datasets.TextJailBreak`:

```bash
pyrit-cli jailbreak-templates list
pyrit-cli jailbreak-templates list --json
```

Image and LLM-backed converters are **not** run through this CLI; use PyRIT in Python (see [HELP.md](src/pyrit_cli/HELP.md)).

### Local Ollama (example)

```bash
pyrit-cli redteam prompt-sending-attack \
  --target ollama:llama3.2 \
  --objective "Reply with exactly: OK"
```

### Multi-turn (example)

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "Get the assistant to state the capital of France is Paris." \
  --true-description "The response states that Paris is the capital of France." \
  --max-turns 3
```

Full flags, HTTP victim options, provider env vars, and edge cases: **[src/pyrit_cli/HELP.md](src/pyrit_cli/HELP.md)** (also loaded by **`ask-ai`**).

## Phoenix tracing (optional)

Use this to capture pyrit-cli redteam HTTP traffic and spans in a local Phoenix instance.

1. Start Phoenix:

```bash
make phoenix-up
```

2. Create local env and enable tracing:

```bash
cp .env.template .env.local
# Edit .env.local and set:
#   PHOENIX_TRACING_ENABLED=true
#   PHOENIX_AUTO_INSTRUMENT=true
```

3. Install/update pyrit-cli in your environment:

```bash
pip install -e .
```

4. Run any redteam command, then open Phoenix:

- UI: `http://localhost:16007`
- OTLP HTTP traces endpoint: `http://localhost:16007/v1/traces`

Fail-open behavior: if Phoenix is unavailable or observability deps are missing, pyrit-cli automatically disables tracing and continues without failing the command.

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/README.md](docs/README.md) | How the docs fit together |
| [docs/workshop-track.md](docs/workshop-track.md) | Linear path: install → setup → discover → red team → ask-ai |
| [src/pyrit_cli/HELP.md](src/pyrit_cli/HELP.md) | Complete CLI reference |

**PyRIT library:** [https://azure.github.io/PyRIT/](https://azure.github.io/PyRIT/)

## Development

Install and run **pytest** (or use **Nox** to create a clean venv each time):

```bash
pip install -e .
pytest tests/
pytest tests/ -m "not integration"   # skip HF download + Ollama (default Nox session)
ruff check src/pyrit_cli tests
```

**Nox** (install globally: `pipx install nox` / `uv tool install nox`):

```bash
# Fast suite: editable install + subprocess CLI checks (no HF / Ollama)
nox -s tests -p 3.12

# Ollama prompt-sending if ``qwen3:0.6b`` is in ``ollama list``; Hugging Face subprocess inspect is opt-in:
nox -s integration -p 3.12
nox -s integration -p 3.12 -- --with-hf   # pass through to pytest after ``--``; enables HF subprocess inspect

nox -s lint -p 3.12
```

If your environment sets conflicting TTY color vars, prefix: `env -u FORCE_COLOR -u NO_COLOR nox ...`.

Sessions **tests** run on Python **3.10** and **3.12** by default; pass **`-p 3.12`** to run one interpreter only.

## License

Package licensing follows the repository that contains this project. PyRIT is licensed separately by Microsoft; see the [PyRIT repository](https://github.com/Azure/PyRIT).

## Also in AISecWorkshops

This package originated in the [AISecWorkshops](https://github.com/emulateai-dev/AISecWorkshops) monorepo under `labs/setup/pyrit/pyrit_cli`. Installing from **this** repo is the standalone layout (`pyrit_cli/` at the root).
