# pyrit-cli HELP

Reference for **setup**, **discover**, **ask-ai**, and **red-team** commands. Install and quick examples: **`pyrit_cli/README.md`** in the workshop repo (`labs/setup/pyrit/pyrit_cli`). Longer **basic → advanced** path: **`pyrit_cli/docs/workshop-track.md`**. This file is bundled inside the `pyrit-cli` package for **`ask-ai`**.

**Quick map**

| Area | Section |
|------|---------|
| Discover (`datasets`, `converters run`, `jailbreak-templates`, …) | [Discover data and knobs](#discover-data-and-knobs) |
| Dataset previews | [`datasets inspect`](#datasets-inspect-preview) |
| Credentials / env | [Setup](#setup-pyrit-cli-setup), [Environment variables](#environment-variables-reference-targets) |
| Natural language helper | [`ask-ai`](#ask-ai-natural-language--shell-command) |
| Chat targets (`openai:`, `groq:`, …) | [Target syntax](#target-syntax-providermodel) |
| Raw HTTP victim | [HTTP victim flags](#http-victim-flags-with---target-http-or---objective-target-http) |
| Single-turn attack | [`prompt-sending-attack`](#1-prompt-sending-attack-single-turn) |
| Multi-turn attack | [`red-teaming-attack`](#2-red-teaming-attack-multi-turn) |
| TAP | [`tap-attack`](#3-tap-attack-tree-of-attacks-with-pruning) |

**PyRIT docs (behavior and theory):**

- Single-turn: [Prompt Sending Attack](https://azure.github.io/PyRIT/code/executor/attack/prompt-sending-attack/)
- Multi-turn: [Red Teaming Attack](https://azure.github.io/PyRIT/code/executor/attack/red-teaming-attack/)
- Tree of Attacks with Pruning: [TAP attack](https://azure.github.io/PyRIT/code/executor/attack/tap-attack/)
- Raw HTTP victim: [HTTP Target](https://azure.github.io/PyRIT/code/targets/http-target/)
- Targets overview (Responses API vs chat): [OpenAI Responses Target](https://azure.github.io/PyRIT/code/targets/openai-responses-target/)
- Built-in / registered datasets (names, loading): [Loading built-in datasets](https://azure.github.io/PyRIT/code/datasets/loading-datasets/)
- Text-to-text converters (incl. LLM-backed): [Text-to-text converters](https://azure.github.io/PyRIT/code/converters/text-to-text-converters/)
- Image converters (text↔image, overlays, etc.): [Image converters](https://azure.github.io/PyRIT/code/converters/image-converters/)

Use only on targets and data you are authorized to test.

---

## Setup (`pyrit-cli setup`)

| Command | Purpose |
|---------|---------|
| `pyrit-cli setup` | Print masked status for `~/.pyrit/.env` and `.env.local` (or `PYRIT_ENV_DIR`). |
| `pyrit-cli setup guide` | Short summary of Option A (native OpenAI) vs Option B (OpenAI-compatible platform vars). |
| `pyrit-cli setup configure` | **Interactive wizard**: choose **OpenAI (api.openai.com)** or **OpenAI-compatible** (e.g. Groq), enter API key (hidden prompt), model, and for compatible backends the base URL. Writes `~/.pyrit/.env` and `.env.local` the same way as the aisec-gradio Setup tab. |

When the wizard finishes, it prints a **`pyrit-cli redteam … --target openai:<model>`** line using the **model you just entered** (so Groq-compatible runs show a Groq model id, not a hard-coded OpenAI-only name).

After configuring, `OPENAI_CHAT_ENDPOINT`, `OPENAI_CHAT_KEY`, and `OPENAI_CHAT_MODEL` in `.env.local` are what PyRIT’s **`OpenAIChatTarget`** uses for **`openai:`** targets. Provider-specific targets (`groq:`, `ollama:`, etc.) use **additional** env vars documented below.

**`openai:<model>` and your backend:** The string after `openai:` is sent to the API as the model name. It must match a model **on whatever host `OPENAI_CHAT_ENDPOINT` points to** (e.g. after the **OpenAI-compatible** wizard, use a **Groq** model id such as `llama-3.3-70b-versatile`, not `gpt-4o-mini`, or you will get 404 / model_not_found). Align with **`OPENAI_CHAT_MODEL`** in `.env.local`, or use **`groq:<model>`** with **`GROQ_API_KEY`** instead.

**OpenAI-compatible wizard (manual file layout):** writes **`~/.pyrit/.env`** with `PLATFORM_OPENAI_CHAT_ENDPOINT`, `PLATFORM_OPENAI_CHAT_API_KEY`, `PLATFORM_OPENAI_CHAT_GPT4O_MODEL`, and **`.env.local`** with `OPENAI_CHAT_*` referencing those variables (see `pyrit-cli setup guide`).

---

## `ask-ai` (natural language → shell command)

```bash
pyrit-cli ask-ai "Describe what you want to run"
```

**HTTP templates (optional files)** — attach a raw request draft and/or a sample response body so the model can suggest a polished **`--http-request`** file and a valid **`--http-response-parser`** (`json:KEYPATH`, `regex:PATTERN`, or `jq:EXPR` per the HTTP victim section). File contents are **sent to your chat API**; keep them under **64 KiB**, **UTF-8** text, and **redact secrets** (API keys, cookies) before running.

```bash
pyrit-cli ask-ai "Propose parser and polish this template" \
  --http-request-file ./my.req \
  --http-response-sample ./sample_response.json
```

Loads **this** HELP text and calls an OpenAI-compatible **`/v1/chat/completions`** API. The model is instructed to:

- List **required environment variables** (with `export VAR=...` examples or “add to `~/.pyrit/.env`”) **whenever** a suggestion uses `groq:`, `ollama:`, `lmstudio:`, `compat:`, or mixed providers — not only `openai:`.
- For **broad or generic** questions (e.g. “how do I test PyRIT?”, “what can I run?”), answer with **several clearly labeled variants** (e.g. single-turn vs multi-turn vs TAP, or different targets), each with prerequisites + command.

**Not** a substitute for reading `--help`; verify suggestions before running.

**Credential resolution (for the ask-ai API call itself, in order):** loads `~/.pyrit/.env` then `.env.local`; then `--api-key`, else `OPENAI_API_KEY`, else `OPENAI_CHAT_KEY` (values starting with `${` are skipped as unresolved).

**Base URL (ask-ai helper only):** `--base-url`, else `OPENAI_CHAT_ENDPOINT`, else `https://api.openai.com/v1`.

| Option | Description |
|--------|-------------|
| `QUERY` (positional) | What you want to do with pyrit-cli. |
| `--model` | Chat model for the helper call (default `gpt-4o-mini` or `OPENAI_CHAT_MODEL`). |
| `--api-key` | Override API key for this call only. |
| `--base-url` | Override API base URL for this call only. |
| `--http-request-file` | Optional path to a raw HTTP template (for `--http-request`); max 64 KiB, UTF-8; contents sent to the API — redact secrets. |
| `--http-response-sample` | Optional path to a sample response body to derive `--http-response-parser`; same limits and privacy note. |

---

## Environment variables reference (targets)

`pyrit-cli setup configure` sets **`OPENAI_CHAT_*`** for **`openai:`** targets. It does **not** set provider-specific variables below — you must add them yourself (shell `export`, or entries in `~/.pyrit/.env` / `.env.local`).

| If you use | Required | Optional | Notes |
|------------|----------|----------|--------|
| `openai:<model>` | `OPENAI_CHAT_KEY`, `OPENAI_CHAT_ENDPOINT`, `OPENAI_CHAT_MODEL` (or use **setup configure**) | — | Loaded from `~/.pyrit`. **Model** in `openai:<model>` must exist on that endpoint (Groq vs OpenAI ids differ). |
| `groq:<model>` | **`GROQ_API_KEY`** | `GROQ_OPENAI_BASE_URL` | Default base `https://api.groq.com/openai/v1`. Without `GROQ_API_KEY`, Groq targets fail at runtime. |
| `ollama:<model>` | (none for typical local Ollama) | `OLLAMA_HOST`, `OLLAMA_API_KEY` | Default host `127.0.0.1:11434`; endpoint becomes `http://…/v1`. |
| `lmstudio:<model>` | (none if defaults work) | `LMSTUDIO_OPENAI_BASE_URL`, `LMSTUDIO_API_KEY` | Default `http://127.0.0.1:1234/v1`. |
| `compat:<model>` | **`PYRIT_CLI_COMPAT_ENDPOINT`** | `PYRIT_CLI_COMPAT_API_KEY` | Generic OpenAI-compatible server. |
| `http` / `https://…` victim | — | — | **No** extra env table: put tokens and cookies in the **raw request file** (`--http-request`). You may put the endpoint in the file **or** pass a full **`https://host/path`** (or `http://…`) as `--target` / `--objective-target` so the CLI merges it into the request line (see **HTTP victim flags**). |

**Example (Groq one-liner before red-team commands):**

```bash
export GROQ_API_KEY="gsk_..."   # from console.groq.com — not the same as OPENAI_CHAT_KEY
pyrit-cli redteam prompt-sending-attack --target groq:llama-3.3-70b-versatile --objective "Reply: OK"
```

**Example (Ollama, local default)** — uses Ollama’s **OpenAI-compatible** `/v1/chat/completions` API (`ollama:` → `http://127.0.0.1:11434/v1` by default). Ensure the server is running and the model tag exists (`ollama pull llama3.2`, `ollama list`).

```bash
ollama pull llama3.2   # once, if needed
pyrit-cli redteam prompt-sending-attack --target ollama:llama3.2 --objective "Reply with exactly: OK"
```

Same pattern with another local model tag, e.g. `ollama:qwen2.5`.

**Example (Ollama, remote or Docker host)** — point `OLLAMA_HOST` at `host:port` or a full URL; `/v1` is added when the value has no path.

```bash
export OLLAMA_HOST=http://192.168.1.50:11434
pyrit-cli redteam prompt-sending-attack --target ollama:llama3.2 --objective "Reply with exactly: OK"
```

If your Ollama deployment requires an API key, set **`OLLAMA_API_KEY`** (otherwise the CLI sends a placeholder key, which is fine for typical local installs).

---

## Shared concepts

### Target syntax (`<provider>:<model>`)

Red-team commands use PyRIT **`OpenAIChatTarget`** against the **chat completions** OpenAI-compatible HTTP API. The CLI does **not** expose **`OpenAIResponseTarget`** (Responses API); that path is library-only for now.

The **first** `:` separates **provider** from **model**. The model part may contain more colons or slashes (e.g. `groq:openai/gpt-oss-120b`, or `groq:openai:some-id` → model string `openai:some-id`).

| Prefix | Meaning | Env vars |
|--------|---------|----------|
| `openai:` | Workshop default | `OPENAI_CHAT_ENDPOINT`, `OPENAI_CHAT_KEY`, `OPENAI_CHAT_MODEL` in `~/.pyrit` (see **setup** above). |
| `groq:` | Groq | **`GROQ_API_KEY`** (required — **not** set by `setup configure` for OpenAI-only). Optional **`GROQ_OPENAI_BASE_URL`** (default `https://api.groq.com/openai/v1`). |
| `ollama:` | Local Ollama | **`OLLAMA_HOST`** (default `127.0.0.1:11434`, or a full `http(s)://` URL). Optional **`OLLAMA_API_KEY`**. API path `/v1` is appended when missing. |
| `lmstudio:` | LM Studio local | **`LMSTUDIO_OPENAI_BASE_URL`** (default `http://127.0.0.1:1234/v1`). Optional **`LMSTUDIO_API_KEY`**. Alias: **`lm-studio:`**. |
| `compat:` | Any OpenAI-compatible server | **`PYRIT_CLI_COMPAT_ENDPOINT`** (required, e.g. `https://host/v1`). Optional **`PYRIT_CLI_COMPAT_API_KEY`** (omit for no-auth locals). |
| `http` or `https://host/path…` | Raw **HTTP** victim ([`HTTPTarget`](https://azure.github.io/PyRIT/code/targets/http-target/)) | Literal **`http`** *or* a full **http(s) URL** as the victim spec: same **`--http-request`** template file, but when the template’s first line is path-only (e.g. `POST /v1/chat/completions HTTP/1.1`), the URL replaces the request-target so PyRIT sends to that endpoint. **`--http-response-parser`** + optional `--http-*` below. **Not** for `tap-attack`. |

You can **mix providers** across flags (e.g. victim `openai:gpt-4o-mini`, adversary `groq:llama-3.3-70b-versatile`, scorer `openai:gpt-4o-mini`) as long as each provider’s credentials are set. For **HTTP** victim (`http` or an http(s) URL) + multi-turn, you **must** set **`--adversarial-target`** to a **chat** spec (HTTP is only the objective / victim).

Run **`pyrit-cli targets list`** for the canonical list and notes.

### HTTP victim flags (with `--target` / `--objective-target` = `http` or an http(s) URL)

Aligned with the [PyRIT HTTP Target](https://azure.github.io/PyRIT/code/targets/http-target/) cookbook: a **raw HTTP request template** (Burp-style) with a prompt placeholder, plus a **response parser**.

**URL as victim spec:** Use **`--objective-target https://api.example.com/v1/chat/completions`** (or `http://…`) instead of **`http`** when the template file uses a **relative** request line (`POST /v1/chat/completions HTTP/1.1`) and you want the endpoint outside the file. The CLI rewrites the first line to use that URL and updates the **`Host`** header to match.

| Flag | When | Description |
|------|------|-------------|
| `--http-request` | required for HTTP victim | Path to a text file containing the full raw HTTP request. Include your placeholder (default `{PROMPT}`) where the objective text should be injected (URL or body). |
| `--http-response-parser` | required for HTTP victim | **`json:KEYPATH`** — PyRIT JSON path, e.g. `choices[0].message.content`. **`regex:PATTERN`** — search decoded **UTF-8** body (pyrit-cli); first match’s full span is returned; optional **`--http-regex-base-url`** prefixes that string. **`jq:EXPR`** — run **`jq`** on the body (`-r`); install [jq](https://jqlang.org/) or use `json:` instead. |
| `--http-prompt-placeholder` | optional | Substring/regex matched in the template for injection (default `{PROMPT}`). |
| `--http-regex-base-url` | optional | Used with **`regex:`** parsers only. |
| `--http-timeout` | optional | `httpx` client timeout (seconds). |
| `--http-use-tls` / `--no-http-use-tls` | optional | Controls URL scheme when the request line is a path and `Host` header is used. |
| `--http-json-body-converter` | optional | JSON-safe escaping of the prompt for embedding in JSON bodies (same role as PyRIT’s `JsonStringConverter`). **Cannot** combine with **`--request-converter`** on `red-teaming-attack`. |
| `--http-model-name` | optional | Stored on the target identifier metadata. |

Example template (also under `examples/http_target/sample_openai_chat.req` in the repo):

```text
POST https://api.example.com/v1/chat/completions HTTP/1.1
Host: api.example.com
Content-Type: application/json

{"model":"gpt-4o-mini","messages":[{"role":"user","content":"{PROMPT}"}]}
```

```bash
pyrit-cli redteam prompt-sending-attack \
  --target http \
  --http-request ./my.req \
  --http-response-parser 'json:choices[0].message.content' \
  --http-json-body-converter \
  --objective "Say hello in one sentence."
```

#### Ollama local API via HTTPTarget (vs `ollama:<model>`)

For day-to-day runs, **`ollama:llama3.2`** (OpenAI-compatible chat) is simpler. Use **`http`** or an **http(s) URL** victim when you want a **raw** template (custom headers, Burp-style replay, or teaching HTTP targets).

Ollama’s OpenAI-compatible chat endpoint is **`http://127.0.0.1:11434/v1/chat/completions`** (or your **`OLLAMA_HOST`**). Example template: `examples/http_target/ollama_openai_chat.req` (path + `Host` only).

**1. Victim = full URL (merges into the request line)** — good when the `.req` file omits an absolute URL:

```bash
pyrit-cli redteam prompt-sending-attack \
  --target 'http://127.0.0.1:11434/v1/chat/completions' \
  --http-request examples/http_target/ollama_openai_chat.req \
  --http-response-parser 'json:choices[0].message.content' \
  --http-json-body-converter \
  --objective "Reply with exactly: OK"
```

**2. Victim = literal `http` and full URL inside the file** — same endpoint, URL stored in the template:

```text
POST http://127.0.0.1:11434/v1/chat/completions HTTP/1.1
Host: 127.0.0.1:11434
Content-Type: application/json

{"model":"llama3.2","messages":[{"role":"user","content":"{PROMPT}"}],"stream":false}
```

```bash
pyrit-cli redteam prompt-sending-attack \
  --target http \
  --http-request ./ollama.req \
  --http-response-parser 'json:choices[0].message.content' \
  --http-json-body-converter \
  --objective "Reply with exactly: OK"
```

**3. Regex parser** (workshop-style; **fragile** if the model returns quotes or newlines inside `content`) — pyrit-cli runs the pattern on the **decoded** JSON text. Prefer **`json:choices[0].message.content`** for real runs.

Ollama `stream:false` responses look like: `... "message":{"role":"assistant","content":"Hello"} ...`. To capture **only** the assistant text as the match, use a lookbehind so the **whole regex match** is the value (the callback returns the full match, not capture group 1):

```bash
pyrit-cli redteam prompt-sending-attack \
  --target 'http://127.0.0.1:11434/v1/chat/completions' \
  --http-request examples/http_target/ollama_openai_chat.req \
  --http-response-parser 'regex:(?<="content":")([^"]*)' \
  --http-json-body-converter \
  --objective "Say hi in three words."
```

That pattern grabs the **first** `"content":"..."` value in the response text (fixed-width, no `"` inside the assistant string). If that hits the wrong field, use **`json:choices[0].message.content`**, **`jq:`**, or a tighter regex.

**Multi-turn** (HTTP victim + chat red-team LLM):

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target 'http://127.0.0.1:11434/v1/chat/completions' \
  --http-request examples/http_target/ollama_openai_chat.req \
  --http-response-parser 'json:choices[0].message.content' \
  --http-json-body-converter \
  --adversarial-target ollama:llama3.2 \
  --objective "Benign factual lab objective." \
  --true-description "Plain-language success criterion." \
  --max-turns 3
```

**CLI validation (HTTP):**

- `--http-request`, `--http-response-parser`, and other `--http-*` options are **only** allowed when the victim is **`http`** or an **http(s) URL**. Otherwise the CLI errors.
- On **`red-teaming-attack`**, **`--http-json-body-converter`** cannot be combined with **`--request-converter`** (pick one way to transform the victim-bound request).
- **`jq:`** parsers need the **`jq`** binary on your `PATH`; use **`json:KEYPATH`** if you want zero extra installs.

### Discover data and knobs

| Need | Command |
|------|---------|
| Paths for `--dataset pyrit:...` | `pyrit-cli datasets list` (optional `--glob 'pattern'`) |
| Preview seeds / rows before running attacks | `pyrit-cli datasets inspect SPEC` (see below) |
| Converter modalities (all PyRIT converters) | `pyrit-cli converters list` or `--json` |
| Keys for `--request-converter` / `--response-converter` (stateless only) | `pyrit-cli converters list-keys` |
| Apply stateless converters to arbitrary text (same keys as above; stack with repeated `-c`) | `pyrit-cli converters run -c KEY …` (positional text or stdin) |
| Jailbreak YAML template names (`TextJailBreak` in Python) | `pyrit-cli jailbreak-templates list` (`--json`, optional `--include-multi-parameter`) |
| Scorer presets and exports | `pyrit-cli scorers list` |
| Target patterns (`openai:`, `groq:`, `http`, …) | `pyrit-cli targets list` |

Sample HTTP templates (repo, under `pyrit_cli`): `examples/http_target/sample_openai_chat.req`, `examples/http_target/ollama_openai_chat.req`.

#### `converters run` (stateless text only)

Runs the same **stateless** converter keys as **`converters list-keys`** / **`--request-converter`**, in order: first converter sees your input; each next sees the previous **`output_text`**.

```bash
pyrit-cli converters run -c rot13 "Hello"
pyrit-cli converters run --converter base64 --converter rot13 "Hello"
echo "plain" | pyrit-cli converters run -c base64
```

- Pass **input** as a **positional** argument, or omit it to read **stdin** (trailing newlines are stripped). Empty stdin with no argument is an error.
- **LLM-backed** converters (variation, translation, …) are **not** available here; use PyRIT in Python or see [Text-to-text converters](https://azure.github.io/PyRIT/code/converters/text-to-text-converters/).
- **Text-to-image** and other **image** converters are **not** exposed as a CLI subcommand; use Python with [Image converters](https://azure.github.io/PyRIT/code/converters/image-converters/) (see below).

#### `jailbreak-templates list`

Lists **`.yaml`** basenames shipped under PyRIT’s jailbreak templates directory (same pool used by **`pyrit.datasets.TextJailBreak`** with **`template_file_name=`**). By default, templates under **`multi_parameter/`** are **excluded** (many need extra template parameters beyond **`prompt`**). Use **`--include-multi-parameter`** to list them anyway.

```bash
pyrit-cli jailbreak-templates list
pyrit-cli jailbreak-templates list --json
```

If two files share the same **basename**, **`TextJailBreak(template_file_name=...)`** fails in PyRIT; the CLI prints a **warning** and, in text mode, shows **`name<TAB>relative_path`** for duplicates.

#### Image converters and jailbreak templates (Python)

The workshop CLI does **not** run **`QRCodeConverter`**, **`AddImageTextConverter`**, or similar image pipelines. Follow [PyRIT: Image converters](https://azure.github.io/PyRIT/code/converters/image-converters/) in Python. A typical shape is: render jailbreak text with **`TextJailBreak`**, then pass that string into an image converter (e.g. QR or text-on-image) inside an **`async`** flow after **`initialize_pyrit_async`**.

```python
# Sketch only — run inside async code after initialize_pyrit_async(..., silent=True).
from pyrit.datasets import TextJailBreak

jb = TextJailBreak(template_file_name="jailbreak_1.yaml")
wrapped = jb.get_jailbreak(prompt="Your short user text here")
# Pass `wrapped` to e.g. QRCodeConverter or AddImageTextConverter.convert_async — see PyRIT image docs.
```

Use only in **authorized** research contexts.

#### `datasets inspect` (preview)

Shows a short preview of objectives before you pass them to **`--dataset`**. Spec must start with **`pyrit:`** or **`hf:`**.

| Spec form | Meaning |
|-----------|---------|
| **`pyrit:seed_datasets/...`** | Load a **YAML / `.prompt`** file under PyRIT’s **`DATASETS_PATH`** (same roots as `datasets list`). |
| **`pyrit:registered_name`** | Load a **built-in registered** dataset via PyRIT’s **`SeedDatasetProvider`** (e.g. `airt_illegal`, `harmbench`). Names match `SeedDatasetProvider.get_all_dataset_names()`; see [PyRIT: Loading built-in datasets](https://azure.github.io/PyRIT/code/datasets/loading-datasets/). Remote sets may download/cache on first use. |
| **`hf:org/dataset`** | Stream the first **`--limit`** non-empty rows from **`--hf-split`** / **`--hf-column`** (requires `pip install 'pyrit-cli[hf]'`). |

```bash
pyrit-cli datasets inspect pyrit:seed_datasets/local/airt/illegal.prompt --limit 3
pyrit-cli datasets inspect pyrit:airt_illegal --limit 2
pyrit-cli datasets inspect hf:imdb --hf-split train --hf-column text --limit 2
```

---

## 1. `prompt-sending-attack` (single-turn)

Maps to PyRIT **`PromptSendingAttack`**: one user-style objective per execution turn, no adversarial LLM loop.

### Options (reference)

| Option | Required | Description |
|--------|----------|-------------|
| `--target` | yes | `<provider>:<model>`, literal **`http`**, or an **http(s) URL** for HTTPTarget (see **Target syntax** / **HTTP victim flags**). |
| `--objective` | one of objective/dataset | Single string sent as the attack objective |
| `--http-request` | with HTTP victim | Path to raw HTTP template file |
| `--http-response-parser` | with HTTP victim | `json:…`, `regex:…`, or `jq:…` |
| `--http-*` | optional | See **HTTP victim flags** |
| `--dataset` | one of objective/dataset | `pyrit:<relative/path>` under PyRIT `DATASETS_PATH`, or `hf:<hub_id>` |
| `--hf-split` | no | Hugging Face split (default `train`) |
| `--hf-column` | no | Column name for objectives (default `text`) |
| `--hf-config` | no | HF dataset config / name when needed |
| `--limit` | no | Cap number of objectives after load (min 1) |

You must supply **either** `--objective` **or** `--dataset`, not both.

### Flavors

**A. One-shot string (simplest)**  
Send a single objective; result is printed with `ConsoleAttackResultPrinter` (outcome may be “undetermined” if no scorer is configured — same as basic PyRIT examples).

```bash
pyrit-cli redteam prompt-sending-attack \
  --target openai:gpt-4o-mini \
  --objective "Reply with exactly: OK"
```

**B. Local Ollama (OpenAI-compatible API)**  
The part after `ollama:` must match an Ollama model name on that host (`ollama list` / `ollama pull <tag>`). Default endpoint is `127.0.0.1:11434`; override with **`OLLAMA_HOST`** (see **Environment variables** examples above).

```bash
pyrit-cli redteam prompt-sending-attack \
  --target ollama:llama3.2 \
  --objective "Reply with exactly: OK"
```

```bash
pyrit-cli redteam prompt-sending-attack \
  --target ollama:qwen2.5 \
  --objective "Reply with exactly: OK"
```

**C. Many objectives from a PyRIT seed file**  
Path is relative to PyRIT’s bundled datasets root (see `datasets list`).

```bash
pyrit-cli redteam prompt-sending-attack \
  --target openai:gpt-4o-mini \
  --dataset pyrit:seed_datasets/local/airt/illegal.prompt \
  --limit 3
```

**D. Objectives from Hugging Face**  
Requires optional install: `pip install 'pyrit-cli[hf]'` (or `datasets`).

```bash
pyrit-cli redteam prompt-sending-attack \
  --target openai:gpt-4o-mini \
  --dataset hf:imdb \
  --hf-split train \
  --hf-column text \
  --limit 2
```

**E. Batch without harmful content**  
Use any benign `pyrit:` YAML or HF column suitable for your policy; `--limit` keeps cost bounded.

**F. HTTP victim (`HTTPTarget`)**  
Same as the [HTTP victim flags](#http-victim-flags-with---target-http-or---objective-target-http) section: raw request file + response parser. Typical JSON chat APIs use `json:choices[0].message.content` and often `--http-json-body-converter`.

---

## 2. `red-teaming-attack` (multi-turn)

Maps to PyRIT **`RedTeamingAttack`**: an **adversarial** chat model proposes prompts; the **objective** (victim) model responds; a **TrueFalse** scorer decides whether the objective is met; repeats up to `--max-turns`.

### Options (reference)

| Option | Required | Description |
|--------|----------|-------------|
| `--objective-target` | yes | Victim: `<provider>:<model>`, **`http`**, or **http(s) URL** for HTTPTarget (see **HTTP victim flags**). |
| `--objective` | yes | High-level attack goal string |
| `--adversarial-target` | no | Adversarial LLM; default = `--objective-target` (**required** chat spec when victim is HTTP) |
| `--http-request` / `--http-response-parser` | with HTTP victim | Same as prompt-sending; required for HTTP victim |
| `--http-*` | optional | Same as **HTTP victim flags** |
| `--max-turns` | no | Default `5`, minimum `1` |
| `--rta-prompt` | no | Adversarial system template: `text_generation` (default), `image_generation`, `naive_crescendo`, `violent_durian`, `crucible` |
| `--memory-labels-json` | no | JSON object of string labels for memory (e.g. `{"harm_category":"demo"}`) |
| `--scorer-preset` | no | `self-ask-tf` (default) or `self-ask-refusal` |
| `--true-description` | for `self-ask-tf` | Text criterion for scorer **True** = “objective achieved” |
| `--refusal-mode` | no | `default` or `strict` — **PyRIT 0.11.x**: ignored for refusal preset; newer PyRIT may use distinct prompts |
| `--scorer-chat-target` | no | Scorer LLM `<provider>:<model>`; default = adversarial target spec |
| `--request-converter` | no | Repeatable; stateless converter keys (order matters). **Disallowed** with **`--http-json-body-converter`** when victim is HTTP. |
| `--response-converter` | no | Repeatable; applied to responses (works with HTTP victim; stacks after any HTTP request converter). |
| `--include-adversarial-conversation` | flag | Include red-team LLM transcript in printed report |

### Stateless `--request-converter` / `--response-converter` keys

These are the built-in CLI registry keys (no extra LLM for conversion):

`ascii-art`, `atbash`, `base64`, `binary`, `braille`, `ecoji`, `emoji`, `first-letter`, `morse`, `rot13`, `string-join`, `unicode-confusable`

LLM-based converters (e.g. variation, translation) are **not** wired in the CLI yet (including **`converters run`** — stateless keys only; see [Text-to-text converters](https://azure.github.io/PyRIT/code/converters/text-to-text-converters/)).

### Flavors

**A. Minimal (same provider/model chain)**  
Good for labs: one target spec for victim + adversary + default scorer chain, explicit success criterion.

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "Get the assistant to say the capital of France is Paris." \
  --true-description "The response states that Paris is the capital of France." \
  --max-turns 3
```

**B. Different adversarial model or provider**  
Use a different `--adversarial-target` spec (another `openai:` model, or e.g. `groq:…` with `GROQ_API_KEY` set). The victim still uses `--objective-target`.

```bash
export GROQ_API_KEY=...   # required for groq:
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o \
  --adversarial-target groq:llama-3.3-70b-versatile \
  --objective "..." \
  --true-description "..."
```

**C. Different scorer target**  
Scoring LLM can be a third `<provider>:<model>` (e.g. cheaper OpenAI model while victim/adversary use Groq).

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o \
  --adversarial-target groq:llama-3.3-70b-versatile \
  --scorer-chat-target openai:gpt-4o-mini \
  --objective "..." \
  --true-description "..."
```

**D. Adversarial “persona” template (`--rta-prompt`)**  
Aligns with `RTASystemPromptPaths` in PyRIT (text vs image-oriented templates, etc.).

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --rta-prompt text_generation \
  --objective "..." \
  --true-description "..."
```

**E. Refusal-oriented scorer**  
`--scorer-preset self-ask-refusal` — interprets refusal detection (see `pyrit-cli scorers list`). Pair with objectives that make sense for refusal testing.

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "..." \
  --scorer-preset self-ask-refusal \
  --refusal-mode default
```

**F. Request obfuscation stack (multi-turn + converters)**  
Same idea as PyRIT’s parallel converter example: transforms applied before the victim sees the prompt.

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "..." \
  --true-description "..." \
  --request-converter emoji \
  --request-converter rot13
```

**G. Memory labels + verbose report**  
Labels are passed through to `execute_async` like the upstream doc’s `memory_labels` argument.

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "..." \
  --true-description "..." \
  --memory-labels-json '{"lab":"workshop","run":"demo"}' \
  --include-adversarial-conversation
```

**H. HTTP victim + chat red-team LLM**  
Victim is **`http`**; adversarial and scorer chains stay **chat** targets. You **must** set **`--adversarial-target`** (cannot default to `http`).

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target http \
  --http-request ./my.req \
  --http-response-parser 'json:choices[0].message.content' \
  --http-json-body-converter \
  --adversarial-target openai:gpt-4o-mini \
  --objective "Benign lab objective text." \
  --true-description "Criterion for success in plain language." \
  --max-turns 3
```

**I. All-Ollama (local lab)**  
Victim, adversary, and default scorer chain all use the same **`ollama:`** spec when you omit `--adversarial-target` and `--scorer-chat-target`. Ollama must be serving the model tag.

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target ollama:llama3.2 \
  --objective "Get the assistant to say the capital of France is Paris." \
  --true-description "The response states that Paris is the capital of France." \
  --max-turns 3
```

**J. OpenAI victim + Ollama adversary**  
Cloud or workshop victim with a **local** red-team model (set **`OLLAMA_HOST`** if not on `127.0.0.1:11434`).

```bash
pyrit-cli redteam red-teaming-attack \
  --objective-target openai:gpt-4o-mini \
  --adversarial-target ollama:llama3.2 \
  --objective "Benign lab objective text." \
  --true-description "Criterion for success in plain language." \
  --max-turns 3
```

---

## 3. `tap-attack` (Tree of Attacks with Pruning)

Maps to PyRIT **`TAPAttack`** (`TreeOfAttacksWithPruningAttack`): multiple adversarial branches explore prompts in parallel; breadth-first expansion with pruning; scoring uses **`FloatScaleThresholdScorer`** wrapping **`SelfAskScaleScorer`** by default (threshold **0.7**), matching the [upstream TAP doc](https://azure.github.io/PyRIT/code/executor/attack/tap-attack/).

All target flags use the same **`<provider>:<model>`** syntax as **red-teaming-attack**.

### Options (reference)

| Option | Required | Description |
|--------|----------|-------------|
| `--objective-target` | yes | Chat victim `<provider>:<model>` only — **HTTP victim** (`http` or http(s) URL) **is not allowed** (PyRIT TAPAttack requires PromptChatTarget). |
| `--objective` | yes | Conversation objective string |
| `--adversarial-target` | no | Red-team LLM; default = `--objective-target` |
| `--adversarial-temperature` | no | e.g. `1.1` for a hotter adversarial `OpenAIChatTarget` |
| `--tree-width` | no | Parallel branches (default `4`, doc example) |
| `--tree-depth` | no | Max iterations (default `5`) |
| `--branching-factor` | no | Children per parent (default `2`) |
| `--on-topic-checking` / `--no-on-topic-checking` | flag | On-topic relevance checks (default on) |
| `--desired-response-prefix` | no | Success signal prefix (default `Sure, here is`) |
| `--batch-size` | no | Nodes per batch (default `10`) |
| `--memory-labels-json` | no | JSON object of string labels for memory |
| `--scorer-chat-target` | no | `SelfAskScaleScorer` chat `<provider>:<model>`; if both this and `--score-threshold` are omitted, PyRIT’s default scorer (adversarial chat, threshold 0.7) is used |
| `--score-threshold` | no | Jailbreak threshold 0–1; if either this or `--scorer-chat-target` is set, builds custom `TAPAttackScoringConfig` |
| `--include-adversarial-conversation` | flag | Print red-team transcript (default on) |
| `--include-pruned-conversations` | flag | Print pruned branches (default on) |

### Example (lab-style, same model)

```bash
pyrit-cli redteam tap-attack \
  --objective-target openai:gpt-4o-mini \
  --objective "Get the assistant to state the capital of France is Paris." \
  --tree-width 4 \
  --tree-depth 3 \
  --adversarial-temperature 1.1
```

### Example (local Ollama, smaller tree)

Same **`ollama:`** OpenAI-compatible endpoint as prompt-sending / red-teaming; smaller **`--tree-width`** / **`--tree-depth`** reduce load on a local GPU or CPU.

```bash
pyrit-cli redteam tap-attack \
  --objective-target ollama:llama3.2 \
  --objective "Get the assistant to state the capital of France is Paris." \
  --tree-width 2 \
  --tree-depth 2 \
  --adversarial-temperature 1.0
```

---

## Limitations (vs full PyRIT)

Not exposed in the CLI today (use Python / notebooks for these):

- **`OpenAIResponseTarget`** and the [Responses API](https://azure.github.io/PyRIT/code/targets/openai-responses-target/) workflow (reasoning traces, web search tools, etc.).
- Custom **`AttackAdversarialConfig.seed_prompt`** (still default template with `{{ objective }}`).
- Custom **filesystem** `system_prompt_path` beyond the `--rta-prompt` enum.
- Extra OpenAI-compatible hosts **beyond** `compat:` + env (no arbitrary per-flag URL without `compat` or code changes).
- **`HTTPTarget`** is only wired for **`prompt-sending-attack`** and **`red-teaming-attack`** (victim **`http`** or an **http(s) URL** + `--http-*` flags). Other non-chat victims (`AzureMLChatTarget`, `TextTarget`, `OpenAIImageTarget`, …), **prepended conversations**, and advanced HTTP flows still need Python.
- **LLM-backed** prompt converters.
- **`tap-attack`**: no `--request-converter` / `--response-converter` wiring yet (use Python for `AttackConverterConfig`).
- **`datasets inspect`**: previews only (text truncation); does not run attacks. Registered built-ins may download/cache on first fetch (same as PyRIT `SeedDatasetProvider`).

---

## Getting `--help`

Typer/Rich may **truncate** option lists in a narrow terminal. If flags look cut off, widen the terminal or run with a larger width, e.g. `COLUMNS=120 pyrit-cli redteam red-teaming-attack --help`.

```bash
pyrit-cli setup --help
pyrit-cli setup configure --help
pyrit-cli redteam --help
pyrit-cli redteam prompt-sending-attack --help
pyrit-cli redteam red-teaming-attack --help
pyrit-cli redteam tap-attack --help
pyrit-cli ask-ai --help
pyrit-cli datasets list --help
pyrit-cli datasets inspect --help
pyrit-cli targets list
pyrit-cli converters list-keys
```
