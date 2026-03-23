# pyrit-cli documentation

Workshop-oriented guides for the CLI. **Authoritative flags, env vars, and edge cases:** bundled [HELP.md](../src/pyrit_cli/HELP.md) (also injected into **`ask-ai`**).

## Reading order (basic → advanced)

| Order | Guide | What you learn |
|-------|--------|----------------|
| 1 | [Workshop track](workshop-track.md) | Install → **`setup configure`** (OpenAI vs Groq-compatible) → **discover** (`targets`, `datasets list`, **`datasets inspect`**, **`converters run`**, **`jailbreak-templates list`**, scorers) → **red team** (prompt-sending, datasets, multi-turn, HTTP / Ollama raw API, TAP) → **`ask-ai`** (including HTTP file attachments) |

## Topics at a glance

| Topic | Where |
|--------|--------|
| Groq / `openai:` model mismatch (404) | [workshop-track.md](workshop-track.md) Level 2; HELP **Setup** + **Environment variables** |
| Preview objectives before attacks | HELP **`datasets inspect`**; workshop Level 3 |
| Stateless converter pipeline on text | HELP **`converters run`**; workshop Level 3 |
| Jailbreak YAML names + image converter docs | HELP **Discover** (jailbreak-templates, image converters link); [PyRIT: Image converters](https://azure.github.io/PyRIT/code/converters/image-converters/) |
| Raw HTTP victim (`http`, URL, parsers, Ollama `.req`) | HELP **HTTP victim flags**; workshop Level 4.7 |
| Full command matrices | [HELP.md](../src/pyrit_cli/HELP.md) only |

## Adding more guides later

1. Add a new Markdown file in this directory (e.g. `scoring-deep-dive.md`, `02-custom-targets.md`).
2. Link it from this **README** in a new row in the table above (or a new subsection).
3. Keep one **canonical** reference for flags: [HELP.md](../src/pyrit_cli/HELP.md). Long guides should explain *when* and *why*; HELP stays the *what* for every option.

**Naming suggestions**

- `workshop-track.md` — linear path for new users (current).
- `topic-<name>.md` — focused deep dives.
- `lab-<n>-<title>.md` — per-lab handouts.

## Related links

- Package overview: [README.md](../README.md) (short copy-paste examples).
- PyRIT library: [https://azure.github.io/PyRIT/](https://azure.github.io/PyRIT/)
- PyRIT datasets (registered names, loading): [Loading built-in datasets](https://azure.github.io/PyRIT/code/datasets/loading-datasets/)
- PyRIT image converters: [Image converters](https://azure.github.io/PyRIT/code/converters/image-converters/)

Use only on targets and data you are allowed to test.
