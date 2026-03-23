# pyrit-cli

Workshop CLI for PyRIT: **configure** credentials (`setup configure`), **ask-ai** for natural-language command suggestions (uses bundled [HELP.md](src/pyrit_cli/HELP.md) + a chat API), inspect `~/.pyrit`, run **single-turn** / **multi-turn** / **TAP** attacks ([PyRIT docs](https://azure.github.io/PyRIT/)), and list **datasets**, **converters**, **scorers**, and **targets**.

**Documentation (install → red team → ask-ai, basic → advanced):** see [docs/README.md](docs/README.md) and the linear [docs/workshop-track.md](docs/workshop-track.md). **Every flag:** [HELP.md](src/pyrit_cli/HELP.md).

Use only on systems and models you are authorized to test.

## Install

```bash
cd labs/setup/pyrit/pyrit_cli
pip install -e .
pip install -e ".[dev]"   # pytest, ruff
# Optional: Hugging Face datasets for --dataset hf:...
pip install -e ".[hf]"
```

On PEP 668 systems, use a venv or `uv venv && uv pip install -e ".[dev]"`.

Configure credentials interactively or by hand:

```bash
pyrit-cli setup configure   # OpenAI or OpenAI-compatible (Groq-style); writes ~/.pyrit/.env + .env.local
```

After **OpenAI-compatible** setup, use **`--target openai:<model>`** with a model id your host supports (e.g. Groq’s `llama-3.3-70b-versatile`), not OpenAI-only names unless that backend exposes them.

Or follow the parent [README](../README.md). `OpenAIChatTarget` reads `OPENAI_CHAT_*` from `.env.local` (often mirroring `OPENAI_API_KEY` or `PLATFORM_*`).

**ask-ai** loads the same HELP reference as humans and calls an OpenAI-compatible `/v1/chat/completions` endpoint using `OPENAI_API_KEY` or `OPENAI_CHAT_KEY` (and optional `OPENAI_CHAT_ENDPOINT`). Example:

```bash
pyrit-cli ask-ai "I want a one-shot test against gpt-4o-mini"
```

## Discover

```bash
pyrit-cli converters list              # modalities table (after PyRIT init)
pyrit-cli converters list --json
pyrit-cli converters list-keys         # stateless keys for --request-converter
pyrit-cli scorers list
pyrit-cli targets list
pyrit-cli datasets list                # paths for --dataset pyrit:...
pyrit-cli datasets list --glob '*airt*'
pyrit-cli datasets inspect pyrit:seed_datasets/local/airt/illegal.prompt --limit 3
pyrit-cli datasets inspect pyrit:airt_illegal --limit 2   # registered built-in (may download)
```

Further reading: [Converters](https://azure.github.io/PyRIT/code/converters/converters/), [Scoring](https://azure.github.io/PyRIT/code/scoring/scoring/).

## Setup

```bash
pyrit-cli setup              # masked env status
pyrit-cli setup guide        # Option A / B summary
pyrit-cli setup configure    # interactive wizard (OpenAI vs compatible API)
```

## Red team

**Single-turn**

```bash
pyrit-cli redteam prompt-sending-attack --target openai:gpt-4o --objective "Say hello in one sentence."
pyrit-cli redteam prompt-sending-attack --target openai:gpt-4o --dataset pyrit:seed_datasets/local/airt/illegal.prompt --limit 2
pyrit-cli redteam prompt-sending-attack --target openai:gpt-4o --dataset hf:imdb --hf-split train --hf-column text --limit 1
```

**Local Ollama** (OpenAI-compatible `/v1` on `127.0.0.1:11434` by default; use `OLLAMA_HOST` for a remote server — see [HELP.md](src/pyrit_cli/HELP.md)):

```bash
pyrit-cli redteam prompt-sending-attack --target ollama:llama3.2 --objective "Reply with exactly: OK"
```

**Multi-turn** (benign example: scorer checks that the model answered a simple factual ask)

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "Get the assistant to state the capital of France is Paris." \
  --true-description "The response states that Paris is the capital of France." \
  --max-turns 3
```

Same flow against a local model: `--objective-target ollama:llama3.2` (and the same `--objective` / `--true-description` / `--max-turns` pattern).

Optional: `--adversarial-target openai:...`, `--scorer-preset self-ask-refusal`, `--rta-prompt text_generation`, `--memory-labels-json '{"lab":"demo"}'`, stacked converters `--request-converter base64 --request-converter rot13`, `--include-adversarial-conversation`.

On PyRIT **0.11.x**, `--refusal-mode` is ignored for `self-ask-refusal` (fixed prompt paths only). Newer PyRIT versions may support `default` / `strict` refusal prompts.

## Tests

```bash
cd labs/setup/pyrit/pyrit_cli
pytest tests/
```
