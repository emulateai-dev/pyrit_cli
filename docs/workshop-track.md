# pyrit-cli workshop track

Linear path from **install** through **red team** to **ask-ai**, from basic usage toward advanced patterns. For every flag and environment variable, see [HELP.md](../src/pyrit_cli/HELP.md).

**Convention:** Examples that use **`openai:gpt-4o-mini`** (or similar OpenAI model ids) assume **`OPENAI_CHAT_*`** points at **api.openai.com**. If you used **`setup configure` → OpenAI-compatible (Groq)**, use **`openai:<your wizard model>`** (e.g. `llama-3.3-70b-versatile`) or **`groq:…`** with **`GROQ_API_KEY`** — see Level 2 — or the API will return **model_not_found**.

---

## Level 0 — Before you start

- You need **Python 3** and permission to call the **LLM or HTTP APIs** you target.
- Credentials for cloud models usually live under **`~/.pyrit/`** (`.env` and `.env.local`).
- This CLI is for **authorized** security research and workshops, not for attacking systems without consent.

---

## Level 1 — Install (basic)

From the `pyrit_cli` package directory (inside the AISecWorkshops repo: `labs/setup/pyrit/pyrit_cli`):

```bash
pip install -e .
```

**Optional extras**

- Developers (tests, lint): `pip install -e ".[dev]"`.
- Hugging Face dataset objectives are included by default.

On PEP 668–locked systems, use a virtual environment, for example:

```bash
uv venv && uv pip install -e ".[dev]"
```

Verify:

```bash
pyrit-cli --version
```

---

## Level 2 — Setup and credentials (basic → intermediate)

### Basic: interactive wizard

```bash
pyrit-cli setup configure
```

Writes **`~/.pyrit/.env`** and **`.env.local`** so **`openai:`** targets can use **`OPENAI_CHAT_*`** (aligned with the aisec-gradio Setup tab).

### Basic: check status

```bash
pyrit-cli setup              # masked view of env
pyrit-cli setup guide        # OpenAI vs OpenAI-compatible summary
```

### Intermediate: other chat providers

Targets like **`groq:`**, **`ollama:`**, **`lmstudio:`**, **`compat:`** need **extra env vars** (not all set by the wizard). See the **Environment variables** table in [HELP.md](../src/pyrit_cli/HELP.md).

#### After `setup configure` → OpenAI-compatible (e.g. Groq)

The wizard stores **`PLATFORM_OPENAI_CHAT_*`** in **`~/.pyrit/.env`** and maps **`OPENAI_CHAT_*`** in **`.env.local`** to that platform. Your default chat traffic uses **`OpenAIChatTarget`** with that endpoint and key.

Use a **Groq model id** in **`openai:`**, matching **`OPENAI_CHAT_MODEL`** (not `gpt-4o-mini`, which is for OpenAI’s API):

```bash
pyrit-cli redteam prompt-sending-attack \
  --target openai:llama-3.3-70b-versatile \
  --objective "Reply: OK"
```

**Explicit Groq target** (same API key pattern; requires **`GROQ_API_KEY`**):

```bash
export GROQ_API_KEY="gsk_..."
pyrit-cli redteam prompt-sending-attack --target groq:llama-3.3-70b-versatile --objective "Reply: OK"
```

---

## Level 3 — Discover the CLI (basic)

These commands list what you can pass into attacks:

```bash
pyrit-cli targets list
pyrit-cli datasets list
pyrit-cli datasets list --glob '*airt*'
pyrit-cli datasets inspect pyrit:seed_datasets/local/airt/illegal.prompt --limit 2
pyrit-cli datasets inspect pyrit:airt_illegal --limit 2
pyrit-cli datasets inspect hf:imdb --hf-split train --hf-column text --limit 2
pyrit-cli converters list-keys
pyrit-cli converters run -c rot13 "Hello"
echo "plain" | pyrit-cli converters run -c base64
pyrit-cli jailbreak-templates list
pyrit-cli scorers list
```

- **`datasets list`** — file paths for **`--dataset pyrit:…`**.
- **`datasets inspect`** — safe preview of seeds/rows (registered built-ins may download on first use). See [HELP.md](../src/pyrit_cli/HELP.md) and [PyRIT: Loading built-in datasets](https://azure.github.io/PyRIT/code/datasets/loading-datasets/).
- **`converters run`** — apply **stateless** converter keys (same as **`list-keys`**); repeat **`-c`** for stack order. Not for LLM or image converters.
- **`jailbreak-templates list`** — YAML names for **`pyrit.datasets.TextJailBreak`** in Python. Combining jailbreak text with **image** converters (QR, overlays, etc.) is done in Python; see [PyRIT: Image converters](https://azure.github.io/PyRIT/code/converters/image-converters/) and [HELP.md](../src/pyrit_cli/HELP.md).

Use **`pyrit-cli <command> --help`** when you need the full option list (widen the terminal or set `COLUMNS=120` if Rich truncates output).

---

## Level 4 — Red team (basic → advanced)

All flows below map to PyRIT executors; see [PyRIT docs](https://azure.github.io/PyRIT/) for concepts.

### 4.1 Single-turn — basic

One objective string, one victim response (no adversarial loop):

```bash
pyrit-cli redteam prompt-sending-attack \
  --target openai:gpt-4o-mini \
  --objective "Reply with exactly: OK"
```

### 4.2 Single-turn — local Ollama (basic)

```bash
pyrit-cli redteam prompt-sending-attack \
  --target ollama:llama3.2 \
  --objective "Reply with exactly: OK"
```

### 4.3 Single-turn — many objectives (intermediate)

From a PyRIT seed file (path from `pyrit-cli datasets list`):

```bash
pyrit-cli redteam prompt-sending-attack \
  --target openai:gpt-4o-mini \
  --dataset pyrit:seed_datasets/local/airt/illegal.prompt \
  --limit 3
```

Hugging Face columns work as **`--dataset hf:<id>`** (see HELP).

### 4.4 Multi-turn — basic

Victim + adversary + scorer (default chain uses one target spec unless you override):

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "Get the assistant to state the capital of France is Paris." \
  --true-description "The response states that Paris is the capital of France." \
  --max-turns 3
```

### 4.5 Multi-turn — mixed providers (intermediate)

Different **`--adversarial-target`** or **`--scorer-chat-target`** specs; each provider needs its env vars (HELP).

### 4.6 Multi-turn — converters (intermediate)

Stateless request/response transforms (keys from **`converters list-keys`**):

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "..." \
  --true-description "..." \
  --request-converter emoji \
  --request-converter rot13
```

### 4.7 HTTP victim — intermediate

Raw **`.req`** file + **`--http-response-parser`** (`json:`, `regex:`, or `jq:`). Victim can be **`http`** or an **`http(s)://...`** URL when the template uses a path-only request line.

```bash
pyrit-cli redteam prompt-sending-attack \
  --target 'http://127.0.0.1:11434/v1/chat/completions' \
  --http-request examples/http_target/ollama_openai_chat.req \
  --http-response-parser 'json:choices[0].message.content' \
  --http-json-body-converter \
  --objective "Reply with exactly: OK"
```

Multi-turn with an HTTP victim **requires** a chat **`--adversarial-target`**.

Templates and Ollama notes: [HELP.md](../src/pyrit_cli/HELP.md) (HTTP victim section) and **`examples/http_target/`**.

### 4.8 TAP — advanced

Tree-of-attacks with pruning (**chat victims only**; no HTTP victim):

```bash
pyrit-cli redteam tap-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "Get the assistant to state the capital of France is Paris." \
  --tree-width 4 \
  --tree-depth 3 \
  --adversarial-temperature 1.1
```

Smaller trees for local models: use **`ollama:...`** and reduce **`--tree-width`** / **`--tree-depth`**.

---

## Level 5 — ask-ai (basic → advanced)

`ask-ai` sends your question plus bundled **HELP.md** to an OpenAI-compatible **`/v1/chat/completions`** endpoint so the model can suggest **`pyrit-cli`** commands. **Verify** any suggestion before running it.

### 5.1 Basic

```bash
pyrit-cli ask-ai "I want a one-shot test against gpt-4o-mini with a benign objective"
```

Uses **`OPENAI_API_KEY`** or **`OPENAI_CHAT_KEY`** (and optional **`OPENAI_CHAT_ENDPOINT`**) after loading **`~/.pyrit`**. The helper’s suggested commands still follow HELP; if your env targets **Groq**, treat **`openai:`** model names in suggestions like any other command — they must match **your** endpoint (see Level 2).

### 5.2 Overrides (intermediate)

```bash
pyrit-cli ask-ai "..." --model gpt-4o-mini --api-key sk-... --base-url https://api.openai.com/v1
```

### 5.3 HTTP template + sample response (advanced)

Attach files so the model can propose a **`--http-request`** template and **`--http-response-parser`** (contents are sent to the API — redact secrets; max 64 KiB each):

```bash
pyrit-cli ask-ai "Propose parser and polish this template" \
  --http-request-file ./my.req \
  --http-response-sample ./sample_response.json
```

Details: [HELP.md](../src/pyrit_cli/HELP.md) (`ask-ai` section).

---

## Where to go next

- Full option matrices and limitations: [HELP.md](../src/pyrit_cli/HELP.md).
- Short copy-paste cheatsheet: [README.md](../README.md).
- More topical docs: add files under **`docs/`** and link them from [docs/README.md](README.md).

---

## Document history

When you add or change labs, update this file or add a linked doc under **`docs/`** and record the change in [docs/README.md](README.md).
