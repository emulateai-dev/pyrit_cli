"""Typer entry: setup, redteam, discover."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv

from pyrit_cli import __version__
from pyrit_cli.discover.converter_run import run_converter_pipeline_sync
from pyrit_cli.discover.converter_image_run import (
    run_image_add_image_text_sync,
    run_image_add_text_image_sync,
    run_image_compress_sync,
    run_image_qrcode_sync,
    run_image_transparency_sync,
)
from pyrit_cli.discover.converters_list import list_converters_json, list_converters_text
from pyrit_cli.discover.jailbreak_templates_list import (
    list_jailbreak_templates_json,
    list_jailbreak_templates_text,
    jailbreak_template_warnings,
)
from pyrit_cli.discover.jailbreak_templates_inspect import run_jailbreak_template_inspect
from pyrit_cli.discover.datasets_inspect import run_dataset_inspect
from pyrit_cli.discover.datasets_list import list_datasets_text
from pyrit_cli.discover.scorers_eval import run_scorer_eval
from pyrit_cli.discover.scorers_list import list_scorers_text
from pyrit_cli.discover.targets_list import list_targets_text
from pyrit_cli.ask_ai import run_ask_ai
from pyrit_cli.env_status import (
    GUIDE_TEXT,
    ensure_pyrit_dir,
    env_path,
    format_setup_report,
    load_for_cli,
    parse_env_file,
    pyrit_dir,
)
from pyrit_cli.env_write import save_openai_compatible, save_openai_native
from pyrit_cli.redteam.http_target_cli import is_http_victim_spec
from pyrit_cli.redteam.prompt_sending import collect_objectives, run_prompt_sending
from pyrit_cli.redteam.red_teaming import parse_memory_labels_json, run_red_teaming
from pyrit_cli.redteam.tap_attack import run_tap_attack
from pyrit_cli.redteam.crescendo_attack import run_crescendo_attack
from pyrit_cli.redteam.targets import TARGET_SPEC_HELP
from pyrit_cli.telemetry import setup_phoenix_tracing


def _validate_http_flags(
    victim: str,
    *,
    http_request: str | None,
    http_response_parser: str | None,
    http_prompt_placeholder: str,
    http_regex_base_url: str | None,
    http_timeout: float | None,
    http_use_tls: bool,
    http_json_body_converter: bool,
    http_model_name: str,
) -> None:
    is_http = is_http_victim_spec(victim)
    if is_http:
        if not http_request or not http_response_parser:
            raise ValueError(
                "With HTTP victim (`http` or an http(s) URL), --http-request and --http-response-parser are required."
            )
        return
    if http_request or http_response_parser:
        raise ValueError(
            "--http-request / --http-response-parser are only valid with HTTP victim "
            "(`http` or an http(s) URL for --target / --objective-target)."
        )
    if http_json_body_converter:
        raise ValueError(
            "--http-json-body-converter is only valid with HTTP victim (`http` or an http(s) URL)."
        )
    if http_regex_base_url:
        raise ValueError(
            "--http-regex-base-url is only valid with HTTP victim (`http` or an http(s) URL)."
        )
    if http_timeout is not None:
        raise ValueError("--http-timeout is only valid with HTTP victim (`http` or an http(s) URL).")
    if not http_use_tls:
        raise ValueError("--no-http-use-tls is only valid with HTTP victim (`http` or an http(s) URL).")
    if http_prompt_placeholder != "{PROMPT}":
        raise ValueError(
            "--http-prompt-placeholder is only valid with HTTP victim (`http` or an http(s) URL)."
        )
    if http_model_name.strip():
        raise ValueError("--http-model-name is only valid with HTTP victim (`http` or an http(s) URL).")


def _version_callback(value: bool) -> None:
    if not value:
        return
    try:
        pyrit_ver = importlib.metadata.version("pyrit")
    except importlib.metadata.PackageNotFoundError:
        pyrit_ver = "unknown"
    typer.echo(f"pyrit-cli {__version__}, pyrit {pyrit_ver}")
    raise typer.Exit()


app = typer.Typer(
    no_args_is_help=True,
    help=(
        "AISec workshop CLI for PyRIT setup and red-team flows. "
        "Try: pyrit-cli ask-ai | setup configure | converters list | converters run"
    ),
)


def _run_uv_tool_install(force: bool) -> None:
    cmd = ["uv", "tool", "install", "--editable"]
    if force:
        cmd.append("--force")
    cmd.append(".")
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as e:
        raise RuntimeError("`uv` is not installed or not on PATH.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"uv command failed with exit code {e.returncode}") from e


@app.callback()
def _main(
    _version: bool = typer.Option(
        False,
        "--version",
        help="Show versions and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """AISec workshop CLI for PyRIT setup and red-team flows."""
    # Project-local env first (for local docker/services), then ~/.pyrit loaded by specific modules.
    load_dotenv(Path.cwd() / ".env", override=False)
    load_dotenv(Path.cwd() / ".env.local", override=True)
    setup_phoenix_tracing(
        service_name="pyrit-cli",
        log=lambda s: typer.secho(s, err=True, fg=typer.colors.BRIGHT_BLACK),
    )
    return


@app.command("uv-install")
def uv_install_cmd() -> None:
    """Install pyrit-cli into uv tool environment from current repo."""
    try:
        _run_uv_tool_install(force=False)
    except RuntimeError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    typer.secho("uv-install complete.", fg=typer.colors.GREEN)


@app.command("uv-update")
def uv_update_cmd() -> None:
    """Reinstall/update pyrit-cli into uv tool environment from current repo."""
    try:
        _run_uv_tool_install(force=True)
    except RuntimeError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    typer.secho("uv-update complete.", fg=typer.colors.GREEN)


@app.command("ask-ai")
def ask_ai_cmd(
    query: str = typer.Argument(..., help="Describe what you want to do with pyrit-cli."),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Chat model for this helper call (default: gpt-4o-mini or OPENAI_CHAT_MODEL).",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="API key for the helper call (else OPENAI_API_KEY / OPENAI_CHAT_KEY after loading ~/.pyrit).",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Chat API base URL (else OPENAI_CHAT_ENDPOINT or https://api.openai.com/v1).",
    ),
    http_request_file: Path | None = typer.Option(
        None,
        "--http-request-file",
        help=(
            "Optional path to a raw HTTP request template for HTTPTarget; contents are read and sent "
            "to the chat API (redact secrets). Max 64 KiB, UTF-8."
        ),
    ),
    http_response_sample: Path | None = typer.Option(
        None,
        "--http-response-sample",
        help=(
            "Optional path to a sample HTTP response body to derive --http-response-parser; contents "
            "are sent to the chat API (redact secrets). Max 64 KiB, UTF-8."
        ),
    ),
    log_level: str = typer.Option(
        "error",
        "--log-level",
        help="ask-ai diagnostics verbosity: error | info | debug",
    ),
) -> None:
    """Suggest a pyrit-cli command using bundled HELP.md and a chat API (authorized use only)."""
    typer.secho(
        "Suggestions are for authorized testing only; verify commands before running.",
        err=True,
        fg=typer.colors.YELLOW,
    )
    if http_request_file is not None or http_response_sample is not None:
        typer.secho(
            "HTTP attachment file contents are sent to your configured chat API; redact secrets first.",
            err=True,
            fg=typer.colors.YELLOW,
        )
    level = log_level.strip().lower()
    if level not in {"error", "info", "debug"}:
        typer.secho("--log-level must be one of: error, info, debug", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    show_diagnostics = level in {"info", "debug"}
    show_http_diagnostics = level == "debug"
    try:
        typer.echo(
            run_ask_ai(
                query,
                model=model,
                api_key=api_key,
                base_url=base_url,
                http_request_file=http_request_file,
                http_response_sample=http_response_sample,
                diagnostics=show_diagnostics,
                http_diagnostics=show_http_diagnostics,
                diagnostics_logger=(
                    (lambda s: typer.secho(s, err=True, fg=typer.colors.BLUE))
                    if show_http_diagnostics
                    else (lambda s: typer.secho(s, err=True, fg=typer.colors.BRIGHT_BLACK))
                ),
            )
        )
    except (ValueError, FileNotFoundError, IsADirectoryError, RuntimeError) as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


setup_app = typer.Typer(help="Inspect and configure ~/.pyrit env (aligned with aisec-gradio Setup).")
app.add_typer(setup_app, name="setup")


def _print_setup_status() -> None:
    typer.echo(format_setup_report(load_for_cli()))


@setup_app.callback(invoke_without_command=True)
def _setup_group(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _print_setup_status()


@setup_app.command("status")
def setup_status() -> None:
    _print_setup_status()


@setup_app.command("guide")
def setup_guide() -> None:
    typer.echo(GUIDE_TEXT)


@setup_app.command("configure")
def setup_configure() -> None:
    """Interactive wizard: write OpenAI or OpenAI-compatible credentials to ~/.pyrit/.env and .env.local."""
    ensure_pyrit_dir()
    root = pyrit_dir()
    typer.echo(f"PyRIT config directory: {root}")
    main = parse_env_file(env_path(".env"))
    has_native = bool(main.get("OPENAI_API_KEY", "").strip())
    has_platform = bool(main.get("PLATFORM_OPENAI_CHAT_ENDPOINT", "").strip())
    if has_native or has_platform:
        if not typer.confirm(
            "Existing API configuration found in .env. Replace it with this wizard?",
            default=False,
        ):
            raise typer.Exit(0)

    choice = typer.prompt("Provider [1] OpenAI (api.openai.com)  [2] OpenAI-compatible (e.g. Groq)", default="1")
    c = choice.strip()
    if c not in ("1", "2"):
        typer.secho("Invalid choice; use 1 or 2.", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if c == "2":
        endpoint = typer.prompt("API base URL", default="https://api.groq.com/openai/v1")
        key = typer.prompt("API key", hide_input=True)
        if not key.strip():
            typer.secho("API key is required.", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1)
        model = typer.prompt("Model name", default="llama-3.3-70b-versatile")
        m1, m2 = save_openai_compatible(endpoint, key, model)
        typer.secho(m1, fg=typer.colors.GREEN)
        typer.secho(m2, fg=typer.colors.GREEN)
        configured_compatible = True
    else:
        key = typer.prompt("OpenAI API key", hide_input=True)
        if not key.strip():
            typer.secho("API key is required.", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1)
        model = typer.prompt("Default chat model", default="gpt-4.1-mini")
        m1, m2 = save_openai_native(key, model=model)
        typer.secho(m1, fg=typer.colors.GREEN)
        typer.secho(m2, fg=typer.colors.GREEN)
        configured_compatible = False

    typer.echo("")
    typer.echo("Current status (masked):")
    typer.echo(format_setup_report(load_for_cli()))
    typer.echo("")
    model_tag = model.strip()
    typer.echo(
        f'Example: pyrit-cli redteam prompt-sending-attack --target openai:{model_tag} --objective "Reply: OK"'
    )
    typer.echo(
        "Use the same model id in openai:<model> that your OPENAI_CHAT_ENDPOINT accepts "
        "(Groq model names when using Groq, OpenAI names when using api.openai.com)."
    )
    if configured_compatible:
        typer.echo(
            "Alternative: export GROQ_API_KEY=... and use --target groq:<model> for an explicit Groq target."
        )


redteam_app = typer.Typer(
    help="Run PyRIT attacks. Stateless converter keys: pyrit-cli converters list-keys.",
)
app.add_typer(redteam_app, name="redteam")


@redteam_app.callback(invoke_without_command=True)
def _redteam_group(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo("Commands:")
        typer.echo("  prompt-sending-attack — single-turn PromptSendingAttack.")
        typer.echo("  red-teaming-attack    — multi-turn RedTeamingAttack.")
        typer.echo("  crescendo-attack      — multi-turn CrescendoAttack with backtracking.")
        typer.echo("  tap-attack            — Tree of Attacks with Pruning (TAPAttack).")
        typer.echo(
            "Discover: converters list | converters run | jailbreak-templates list | jailbreak-templates inspect | "
            "scorers list | scorers eval | targets list | datasets list | datasets inspect"
        )
        typer.echo("Full workshop UI: pip install aisec-gradio && aisec-gradio")


@redteam_app.command("prompt-sending-attack")
def redteam_prompt_sending(
    target: str = typer.Option(..., "--target", help=TARGET_SPEC_HELP),
    objective: str | None = typer.Option(None, "--objective", help="Single objective string."),
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="pyrit:relative/path.yaml under PyRIT datasets, or hf:org/dataset",
    ),
    hf_split: str = typer.Option("train", "--hf-split"),
    hf_column: str = typer.Option("text", "--hf-column"),
    hf_config: str | None = typer.Option(None, "--hf-config"),
    limit: int | None = typer.Option(None, "--limit", help="Max objectives (after load).", min=1),
    http_request: str | None = typer.Option(
        None,
        "--http-request",
        help="Path to raw HTTP template when --target is `http` or an http(s) URL (Burp-style; include {PROMPT}).",
    ),
    http_response_parser: str | None = typer.Option(
        None,
        "--http-response-parser",
        help="json:KEYPATH | regex:PATTERN | jq:EXPR (see HELP). Required for HTTP victim target.",
    ),
    http_prompt_placeholder: str = typer.Option(
        "{PROMPT}",
        "--http-prompt-placeholder",
        help="Substring/regex matched in the raw request for prompt injection (PyRIT HTTPTarget).",
    ),
    http_regex_base_url: str | None = typer.Option(
        None,
        "--http-regex-base-url",
        help="Prefix for regex parser matches (optional; e.g. Bing-style flows).",
    ),
    http_timeout: float | None = typer.Option(
        None,
        "--http-timeout",
        help="httpx client timeout seconds for HTTPTarget.",
    ),
    http_use_tls: bool = typer.Option(
        True,
        "--http-use-tls/--no-http-use-tls",
        help="Infer https vs http from Host when the request line is a path (HTTPTarget use_tls).",
    ),
    http_json_body_converter: bool = typer.Option(
        False,
        "--http-json-body-converter",
        help="Apply JsonStringConverter on requests (JSON bodies with HTTP victim target).",
    ),
    http_model_name: str = typer.Option(
        "",
        "--http-model-name",
        help="Optional model label for HTTPTarget identifier metadata.",
    ),
    scoring_mode: str = typer.Option(
        "auto",
        "--scoring-mode",
        help="auto | off | configured. auto uses non-refusal objective scoring.",
    ),
    scorer_preset: str = typer.Option(
        "non-refusal",
        "--scorer-preset",
        help="non-refusal | refusal | self-ask-tf (used when scoring mode is configured).",
    ),
    true_description: str | None = typer.Option(
        None,
        "--true-description",
        help="Criterion for True when --scorer-preset=self-ask-tf.",
    ),
    scorer_chat_target: str | None = typer.Option(
        None,
        "--scorer-chat-target",
        help=f"Scorer LLM target; required for HTTP victim scoring. {TARGET_SPEC_HELP}",
    ),
    jailbreak_template: str | None = typer.Option(
        None,
        "--jailbreak-template",
        help="Optional TextJailBreak template: bundled basename (e.g. dan_1.yaml) or path to a .yaml file.",
    ),
    jailbreak_template_param: list[str] | None = typer.Option(
        None,
        "--jailbreak-template-param",
        help="Template parameter as key=value (repeatable). Requires --jailbreak-template.",
    ),
    input_image: list[str] | None = typer.Option(
        None,
        "--input-image",
        help="Repeatable image path to attach to each prompt as image_path piece (vision targets).",
    ),
    input_text: str | None = typer.Option(
        None,
        "--input-text",
        help="Optional extra user text piece to send before image pieces.",
    ),
) -> None:
    try:
        objectives = collect_objectives(
            objective,
            dataset,
            hf_split=hf_split,
            hf_column=hf_column,
            hf_config=hf_config,
            limit=limit,
        )
    except (ValueError, FileNotFoundError, ImportError) as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    try:
        _validate_http_flags(
            target,
            http_request=http_request,
            http_response_parser=http_response_parser,
            http_prompt_placeholder=http_prompt_placeholder,
            http_regex_base_url=http_regex_base_url,
            http_timeout=http_timeout,
            http_use_tls=http_use_tls,
            http_json_body_converter=http_json_body_converter,
            http_model_name=http_model_name,
        )
    except ValueError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    typer.secho(
        "Authorized red-teaming only. You are responsible for targets, credentials, and policy.",
        err=True,
        fg=typer.colors.YELLOW,
    )
    try:
        run_prompt_sending(
            target,
            objectives,
            http_request_path=http_request,
            http_response_parser=http_response_parser,
            http_prompt_placeholder=http_prompt_placeholder,
            http_regex_base_url=http_regex_base_url,
            http_timeout=http_timeout,
            http_use_tls=http_use_tls,
            http_json_body_converter=http_json_body_converter,
            http_model_name=http_model_name,
            scoring_mode=scoring_mode,
            scorer_preset=scorer_preset,
            true_description=true_description,
            scorer_chat_target=scorer_chat_target,
            jailbreak_template=jailbreak_template,
            jailbreak_template_params=list(jailbreak_template_param or []),
            input_images=list(input_image or []),
            input_text=input_text,
        )
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@redteam_app.command("red-teaming-attack")
def redteam_red_teaming(
    objective_target: str = typer.Option(
        ...,
        "--objective-target",
        help=f"Victim model: {TARGET_SPEC_HELP}",
    ),
    objective: str = typer.Option(..., "--objective", help="Attack objective string."),
    adversarial_target: str | None = typer.Option(
        None,
        "--adversarial-target",
        help=(
            "Red-team LLM; default: same as --objective-target, except local victims "
            "(ollama/lmstudio/compat) auto-fallback to openai:${OPENAI_CHAT_MODEL} when available. "
            f"{TARGET_SPEC_HELP}"
        ),
    ),
    max_turns: int = typer.Option(5, "--max-turns", min=1),
    rta_prompt: str = typer.Option(
        "text_generation",
        "--rta-prompt",
        help="text_generation | image_generation | naive_crescendo | violent_durian | crucible",
    ),
    memory_labels_json: str | None = typer.Option(
        None,
        "--memory-labels-json",
        help='Optional JSON object of string labels, e.g. \'{"harm_category":"demo"}\'',
    ),
    scorer_preset: str = typer.Option(
        "self-ask-tf",
        "--scorer-preset",
        help="self-ask-tf | self-ask-refusal",
    ),
    true_description: str | None = typer.Option(
        None,
        "--true-description",
        help="Required for self-ask-tf: criterion for True (objective met).",
    ),
    refusal_mode: str = typer.Option(
        "default",
        "--refusal-mode",
        help="For self-ask-refusal: default | strict",
    ),
    scorer_chat_target: str | None = typer.Option(
        None,
        "--scorer-chat-target",
        help=(
            "Scorer LLM; default: adversarial target (including auto-fallback behavior). "
            f"{TARGET_SPEC_HELP}"
        ),
    ),
    request_converter: list[str] | None = typer.Option(
        None,
        "--request-converter",
        help="Stack stateless converters (order matters). Run: pyrit-cli converters list-keys",
    ),
    response_converter: list[str] | None = typer.Option(
        None,
        "--response-converter",
        help="Response-side converter stack.",
    ),
    include_adversarial_conversation: bool = typer.Option(
        False,
        "--include-adversarial-conversation",
        help="Print red-team LLM conversation in the report.",
    ),
    http_request: str | None = typer.Option(
        None,
        "--http-request",
        help="Path to raw HTTP template when --objective-target is `http` or an http(s) URL.",
    ),
    http_response_parser: str | None = typer.Option(
        None,
        "--http-response-parser",
        help="json:KEYPATH | regex:PATTERN | jq:EXPR. Required for HTTP victim.",
    ),
    http_prompt_placeholder: str = typer.Option(
        "{PROMPT}",
        "--http-prompt-placeholder",
        help="Prompt placeholder in raw HTTP request (HTTPTarget).",
    ),
    http_regex_base_url: str | None = typer.Option(
        None,
        "--http-regex-base-url",
        help="Optional URL prefix for regex response parsing.",
    ),
    http_timeout: float | None = typer.Option(
        None,
        "--http-timeout",
        help="httpx timeout seconds for HTTPTarget.",
    ),
    http_use_tls: bool = typer.Option(
        True,
        "--http-use-tls/--no-http-use-tls",
        help="HTTPTarget use_tls when building URL from Host + path.",
    ),
    http_json_body_converter: bool = typer.Option(
        False,
        "--http-json-body-converter",
        help="JsonStringConverter on victim requests (cannot combine with --request-converter).",
    ),
    http_model_name: str = typer.Option(
        "",
        "--http-model-name",
        help="Optional HTTPTarget model_name metadata.",
    ),
    jailbreak_template: str | None = typer.Option(
        None,
        "--jailbreak-template",
        help="Optional TextJailBreak template: bundled basename (e.g. dan_1.yaml) or path to a .yaml file.",
    ),
    jailbreak_template_param: list[str] | None = typer.Option(
        None,
        "--jailbreak-template-param",
        help="Template key=value (repeatable). Requires --jailbreak-template.",
    ),
    input_image: list[str] | None = typer.Option(
        None,
        "--input-image",
        help="Repeatable image path to attach as image_path piece (vision targets).",
    ),
    input_text: str | None = typer.Option(
        None,
        "--input-text",
        help="Optional extra user text piece sent with image pieces.",
    ),
) -> None:
    try:
        memory_labels = parse_memory_labels_json(memory_labels_json)
    except (ValueError, json.JSONDecodeError) as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    try:
        _validate_http_flags(
            objective_target,
            http_request=http_request,
            http_response_parser=http_response_parser,
            http_prompt_placeholder=http_prompt_placeholder,
            http_regex_base_url=http_regex_base_url,
            http_timeout=http_timeout,
            http_use_tls=http_use_tls,
            http_json_body_converter=http_json_body_converter,
            http_model_name=http_model_name,
        )
    except ValueError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    typer.secho(
        "Authorized red-teaming only. You are responsible for targets, credentials, and policy.",
        err=True,
        fg=typer.colors.YELLOW,
    )
    try:
        run_red_teaming(
            objective_target_spec=objective_target,
            adversarial_target_spec=adversarial_target,
            objective=objective,
            max_turns=max_turns,
            rta_prompt=rta_prompt,
            memory_labels=memory_labels,
            scorer_preset=scorer_preset,
            true_description=true_description,
            refusal_mode=refusal_mode,
            scorer_chat_spec=scorer_chat_target,
            request_converter_keys=list(request_converter or []),
            response_converter_keys=list(response_converter or []),
            include_adversarial_conversation=include_adversarial_conversation,
            http_request_path=http_request,
            http_response_parser=http_response_parser,
            http_prompt_placeholder=http_prompt_placeholder,
            http_regex_base_url=http_regex_base_url,
            http_timeout=http_timeout,
            http_use_tls=http_use_tls,
            http_json_body_converter=http_json_body_converter,
            http_model_name=http_model_name,
            jailbreak_template=jailbreak_template,
            jailbreak_template_params=list(jailbreak_template_param or []),
            input_images=list(input_image or []),
            input_text=input_text,
        )
    except ValueError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@redteam_app.command("tap-attack")
def redteam_tap_attack(
    objective_target: str = typer.Option(
        ...,
        "--objective-target",
        help=f"Victim model: {TARGET_SPEC_HELP}",
    ),
    objective: str = typer.Option(..., "--objective", help="Conversation objective for TAP."),
    adversarial_target: str | None = typer.Option(
        None,
        "--adversarial-target",
        help=f"Red-team LLM; default: same as --objective-target. {TARGET_SPEC_HELP}",
    ),
    adversarial_temperature: float | None = typer.Option(
        None,
        "--adversarial-temperature",
        help="Optional temperature for adversarial OpenAIChatTarget (e.g. 1.1).",
    ),
    tree_width: int = typer.Option(4, "--tree-width", min=1),
    tree_depth: int = typer.Option(5, "--tree-depth", min=1),
    branching_factor: int = typer.Option(2, "--branching-factor", min=1),
    on_topic_checking_enabled: bool = typer.Option(
        True,
        "--on-topic-checking/--no-on-topic-checking",
        help="Enable on-topic relevance checks (PyRIT TAP).",
    ),
    desired_response_prefix: str = typer.Option(
        "Sure, here is",
        "--desired-response-prefix",
        help="Prefix TAP treats as strong signal of jailbreak success.",
    ),
    batch_size: int = typer.Option(10, "--batch-size", min=1),
    memory_labels_json: str | None = typer.Option(
        None,
        "--memory-labels-json",
        help='Optional JSON object of string labels.',
    ),
    scorer_chat_target: str | None = typer.Option(
        None,
        "--scorer-chat-target",
        help=f"Scorer for SelfAskScaleScorer; default: adversarial. {TARGET_SPEC_HELP}",
    ),
    score_threshold: float | None = typer.Option(
        None,
        "--score-threshold",
        help="Jailbreak score threshold (0-1). If set with defaults, builds custom TAP scoring.",
    ),
    include_adversarial_conversation: bool = typer.Option(
        True,
        "--include-adversarial-conversation/--no-include-adversarial-conversation",
    ),
    include_pruned_conversations: bool = typer.Option(
        True,
        "--include-pruned-conversations/--no-include-pruned-conversations",
    ),
) -> None:
    if is_http_victim_spec(objective_target):
        typer.secho(
            "tap-attack does not support HTTP victim targets (--objective-target `http` or an http(s) URL); "
            "PyRIT TAPAttack requires PromptChatTarget.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    try:
        memory_labels = parse_memory_labels_json(memory_labels_json)
    except (ValueError, json.JSONDecodeError) as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    typer.secho(
        "Authorized red-teaming only. TAP is high-cost and high-risk; use only on approved targets.",
        err=True,
        fg=typer.colors.YELLOW,
    )
    try:
        run_tap_attack(
            objective_target_spec=objective_target,
            objective=objective,
            adversarial_target_spec=adversarial_target,
            adversarial_temperature=adversarial_temperature,
            tree_width=tree_width,
            tree_depth=tree_depth,
            branching_factor=branching_factor,
            on_topic_checking_enabled=on_topic_checking_enabled,
            desired_response_prefix=desired_response_prefix,
            batch_size=batch_size,
            memory_labels=memory_labels,
            scorer_chat_spec=scorer_chat_target,
            score_threshold=score_threshold,
            include_adversarial_conversation=include_adversarial_conversation,
            include_pruned_conversations=include_pruned_conversations,
        )
    except ValueError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@redteam_app.command("crescendo-attack")
def redteam_crescendo_attack(
    objective_target: str = typer.Option(
        ...,
        "--objective-target",
        help=f"Victim model: {TARGET_SPEC_HELP}",
    ),
    objective: str = typer.Option(..., "--objective", help="Conversation objective for Crescendo."),
    adversarial_target: str | None = typer.Option(
        None,
        "--adversarial-target",
        help=f"Red-team LLM; default: same as --objective-target. {TARGET_SPEC_HELP}",
    ),
    max_turns: int = typer.Option(7, "--max-turns", min=1),
    max_backtracks: int = typer.Option(4, "--max-backtracks", min=0),
    memory_labels_json: str | None = typer.Option(
        None,
        "--memory-labels-json",
        help='Optional JSON object of string labels.',
    ),
    scorer_preset: str = typer.Option(
        "self-ask-tf",
        "--scorer-preset",
        help="self-ask-tf | self-ask-refusal",
    ),
    true_description: str | None = typer.Option(
        None,
        "--true-description",
        help="Required for self-ask-tf: criterion for True (objective met).",
    ),
    refusal_mode: str = typer.Option(
        "default",
        "--refusal-mode",
        help="For self-ask-refusal: default | strict",
    ),
    scorer_chat_target: str | None = typer.Option(
        None,
        "--scorer-chat-target",
        help=f"Scorer LLM target; default: adversarial target. {TARGET_SPEC_HELP}",
    ),
    request_converter: list[str] | None = typer.Option(
        None,
        "--request-converter",
        help="Stack stateless converters (order matters). Run: pyrit-cli converters list-keys",
    ),
    response_converter: list[str] | None = typer.Option(
        None,
        "--response-converter",
        help="Response-side converter stack.",
    ),
    include_adversarial_conversation: bool = typer.Option(
        True,
        "--include-adversarial-conversation/--no-include-adversarial-conversation",
    ),
    include_pruned_conversations: bool = typer.Option(
        True,
        "--include-pruned-conversations/--no-include-pruned-conversations",
    ),
) -> None:
    if is_http_victim_spec(objective_target):
        typer.secho(
            "crescendo-attack does not support HTTP victim targets (--objective-target `http` or an http(s) URL); "
            "use a chat target.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    try:
        memory_labels = parse_memory_labels_json(memory_labels_json)
    except (ValueError, json.JSONDecodeError) as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    typer.secho(
        "Authorized red-teaming only. Crescendo may be high-cost and high-risk; use only on approved targets.",
        err=True,
        fg=typer.colors.YELLOW,
    )
    try:
        run_crescendo_attack(
            objective_target_spec=objective_target,
            objective=objective,
            adversarial_target_spec=adversarial_target,
            max_turns=max_turns,
            max_backtracks=max_backtracks,
            scorer_preset=scorer_preset,
            true_description=true_description,
            refusal_mode=refusal_mode,
            scorer_chat_spec=scorer_chat_target,
            request_converter_keys=list(request_converter or []),
            response_converter_keys=list(response_converter or []),
            include_adversarial_conversation=include_adversarial_conversation,
            include_pruned_conversations=include_pruned_conversations,
            memory_labels=memory_labels,
        )
    except ValueError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


converters_app = typer.Typer(
    help="Discover PyRIT prompt converters and run stateless text/image converter commands.",
)
app.add_typer(converters_app, name="converters")


@converters_app.command("list")
def converters_list(json_out: bool = typer.Option(False, "--json", help="JSON output")) -> None:
    try:
        typer.echo(list_converters_json() if json_out else list_converters_text())
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@converters_app.command("list-keys")
def converters_list_keys() -> None:
    from pyrit_cli.registries.converters import list_converter_keys

    typer.echo("Stateless CLI keys for --request-converter / --response-converter:")
    for k in list_converter_keys():
        typer.echo(f"  {k}")


@converters_app.command("run")
def converters_run_cmd(
    text: str | None = typer.Argument(
        None,
        help="Input text. Omit to read stdin (trailing newlines stripped).",
    ),
    converter: list[str] = typer.Option(
        [],
        "--converter",
        "-c",
        help="Stateless converter key, same as `converters list-keys` (repeat for stack order).",
    ),
) -> None:
    """Apply stateless converters to text (positional or stdin). Not for LLM-based converters."""
    if not converter:
        typer.secho("At least one --converter / -c is required.", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if text is None:
        raw = sys.stdin.read()
        if raw == "":
            typer.secho(
                "No input text: pass TEXT as an argument or pipe non-empty stdin.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)
        text = raw.rstrip("\n\r")
    try:
        typer.echo(run_converter_pipeline_sync(text, converter), nl=False)
        typer.echo()
    except ValueError as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


converters_image_app = typer.Typer(help="Run selected PyRIT image converters from the CLI.")
converters_app.add_typer(converters_image_app, name="image")


@converters_image_app.command("list-keys")
def converters_image_list_keys() -> None:
    typer.echo("Image converter commands:")
    typer.echo("  qrcode          text -> image path")
    typer.echo("  compress        image path -> image path")
    typer.echo("  add-text-image  image path + text -> image path")
    typer.echo("  add-image-text  base image + text -> image path")
    typer.echo("  transparency    benign image + attack image -> blended image path")


@converters_image_app.command("qrcode")
def converters_image_qrcode(
    text: str = typer.Argument(..., help="Text to encode into a QR image."),
) -> None:
    try:
        typer.echo(run_image_qrcode_sync(text))
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@converters_image_app.command("compress")
def converters_image_compress(
    input_path: Path = typer.Option(..., "--input", exists=True, file_okay=True, dir_okay=False),
    quality: int = typer.Option(50, "--quality", min=1, max=100),
) -> None:
    try:
        typer.echo(run_image_compress_sync(input_path, quality=quality))
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@converters_image_app.command("add-text-image")
def converters_image_add_text_image(
    image: Path = typer.Option(..., "--image", exists=True, file_okay=True, dir_okay=False),
    text: str = typer.Option(..., "--text", help="Text to overlay onto the image."),
) -> None:
    try:
        typer.echo(run_image_add_text_image_sync(image, text=text))
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@converters_image_app.command("add-image-text")
def converters_image_add_image_text(
    base_image: Path = typer.Option(..., "--base-image", exists=True, file_okay=True, dir_okay=False),
    text: str = typer.Option(..., "--text", help="Text prompt rendered with the converter onto base image."),
) -> None:
    try:
        typer.echo(run_image_add_image_text_sync(base_image, text=text))
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@converters_image_app.command("transparency")
def converters_image_transparency(
    benign: Path = typer.Option(..., "--benign", exists=True, file_okay=True, dir_okay=False),
    attack: Path = typer.Option(..., "--attack", exists=True, file_okay=True, dir_okay=False),
    size: int = typer.Option(150, "--size", min=16, max=4096, help="Output width/height (square)."),
    steps: int = typer.Option(1500, "--steps", min=1, help="Optimization steps."),
    learning_rate: float = typer.Option(0.001, "--learning-rate", min=0.000001, help="Optimizer learning rate."),
) -> None:
    try:
        typer.echo(
            run_image_transparency_sync(
                benign,
                attack,
                size=size,
                steps=steps,
                learning_rate=learning_rate,
            )
        )
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


jailbreak_templates_app = typer.Typer(
    help="List PyRIT jailbreak YAML templates (for pyrit.datasets.TextJailBreak in Python).",
)
app.add_typer(jailbreak_templates_app, name="jailbreak-templates")


@jailbreak_templates_app.command("list")
def jailbreak_templates_list_cmd(
    json_out: bool = typer.Option(False, "--json", help="JSON output (name + relative_path per file)."),
    include_multi_parameter: bool = typer.Option(
        False,
        "--include-multi-parameter",
        help="Include templates under multi_parameter/ (often need extra kwargs beyond prompt).",
    ),
) -> None:
    """List template basenames under PyRIT's jailbreak templates (excludes multi_parameter/ by default)."""
    warnings = jailbreak_template_warnings(include_multi_parameter=include_multi_parameter)
    for w in warnings:
        typer.secho(w, err=True, fg=typer.colors.YELLOW)
    try:
        typer.echo(
            list_jailbreak_templates_json(include_multi_parameter=include_multi_parameter)
            if json_out
            else list_jailbreak_templates_text(include_multi_parameter=include_multi_parameter)
        )
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


@jailbreak_templates_app.command("inspect")
def jailbreak_templates_inspect_cmd(
    name_or_path: str = typer.Argument(
        ...,
        help="Template basename (e.g. dan_1.yaml), path under jailbreak root, or absolute path to a .yaml file.",
    ),
    relative_path: str | None = typer.Option(
        None,
        "--relative-path",
        help="Disambiguate duplicate basenames: path relative to PyRIT jailbreak templates root.",
    ),
    include_multi_parameter: bool = typer.Option(
        False,
        "--include-multi-parameter",
        help="Allow resolving templates under multi_parameter/ when matching by basename.",
    ),
    param: list[str] | None = typer.Option(
        None,
        "--param",
        help="Template placeholder key=value (repeatable). Required for non-prompt parameters.",
    ),
    preview_chars: int = typer.Option(
        4096,
        "--preview-chars",
        min=80,
        max=8000,
        help="Max characters for rendered preview (single-line, collapsed).",
    ),
    json_out: bool = typer.Option(False, "--json", help="JSON output with metadata + preview."),
) -> None:
    """Preview a jailbreak template: parameters, path, and rendered system prompt (truncated)."""
    try:
        typer.echo(
            run_jailbreak_template_inspect(
                name_or_path,
                include_multi_parameter=include_multi_parameter,
                relative_path=relative_path,
                param_pairs=list(param or []),
                preview_chars=preview_chars,
                json_out=json_out,
            )
        )
    except (ValueError, FileNotFoundError) as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


scorers_app = typer.Typer(help="Scorer presets and PyRIT score exports.")
app.add_typer(scorers_app, name="scorers")


@scorers_app.command("list")
def scorers_list_cmd() -> None:
    typer.echo(list_scorers_text())


@scorers_app.command("eval")
def scorers_eval_cmd(
    preset: str = typer.Option(
        ...,
        "--preset",
        help="Objective scorer preset: self-ask-tf | self-ask-refusal (same as red-teaming-attack).",
    ),
    text: str | None = typer.Option(
        None,
        "--text",
        help='Text to score. Use "-" to read from stdin.',
    ),
    text_file: Path | None = typer.Option(
        None,
        "--text-file",
        help="Read text from this file (UTF-8). Mutually exclusive with --text.",
    ),
    objective: str | None = typer.Option(
        None,
        "--objective",
        help="Optional task / attacker objective (passed to the scorer; useful for refusal detection).",
    ),
    scorer_chat_target: str | None = typer.Option(
        None,
        "--scorer-chat-target",
        help=(
            f"Chat model for self-ask scoring. {TARGET_SPEC_HELP} "
            "If omitted, uses openai:<OPENAI_CHAT_MODEL> when that env var is set."
        ),
    ),
    true_description: str | None = typer.Option(
        None,
        "--true-description",
        help="Criterion for True when --preset=self-ask-tf (required for that preset).",
    ),
    refusal_mode: str = typer.Option(
        "default",
        "--refusal-mode",
        help="When --preset=self-ask-refusal: default | strict.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print scores as a JSON array."),
) -> None:
    """Score arbitrary text with CLI True/False presets (PyRIT score_text_async).

    Uses the same SelfAskTrueFalseScorer / SelfAskRefusalScorer wiring as red-teaming. The wrapped
    message uses a single user-role piece (see PyRIT scoring docs).
    """
    try:
        run_scorer_eval(
            preset=preset,
            text=text,
            text_file=text_file,
            objective=objective,
            scorer_chat_target=scorer_chat_target,
            true_description=true_description,
            refusal_mode=refusal_mode,
            json_out=json_out,
        )
    except (ValueError, FileNotFoundError) as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e


targets_app = typer.Typer(help="CLI-supported target patterns.")
app.add_typer(targets_app, name="targets")


@targets_app.command("list")
def targets_list_cmd() -> None:
    typer.echo(list_targets_text())


datasets_app = typer.Typer(
    help="PyRIT seed paths, built-in registered datasets (SeedDatasetProvider), and HF previews.",
)
app.add_typer(datasets_app, name="datasets")


@datasets_app.command("list")
def datasets_list_cmd(
    glob_pattern: str | None = typer.Option(
        None,
        "--glob",
        help="fnmatch pattern against path under seed_datasets (e.g. '*airt*')",
    ),
) -> None:
    typer.echo(list_datasets_text(glob_pattern=glob_pattern))


@datasets_app.command("inspect")
def datasets_inspect_cmd(
    spec: str = typer.Argument(
        ...,
        help=(
            "pyrit:path under DATASETS_PATH (e.g. seed_datasets/local/airt/illegal.prompt), "
            "pyrit:registered_name (e.g. airt_illegal), or hf:org/dataset"
        ),
    ),
    limit: int = typer.Option(5, "--limit", min=1, max=500, help="Max rows/seeds to show."),
    hf_split: str = typer.Option("train", "--hf-split", help="HF split (hf: specs only)."),
    hf_column: str = typer.Option("text", "--hf-column", help="HF column name (hf: specs only)."),
    hf_config: str | None = typer.Option(
        None,
        "--hf-config",
        help="HF dataset config / subset name when required.",
    ),
) -> None:
    """Preview dataset text: local PyRIT YAML, PyRIT built-in registered names, or Hugging Face (streaming).

    See https://azure.github.io/PyRIT/code/datasets/loading-datasets/
    """
    try:
        typer.echo(
            run_dataset_inspect(
                spec,
                limit=limit,
                hf_split=hf_split,
                hf_column=hf_column,
                hf_config=hf_config,
            )
        )
    except (ValueError, FileNotFoundError, ImportError, RuntimeError) as e:
        typer.secho(str(e), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
