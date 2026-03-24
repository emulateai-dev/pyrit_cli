"""HTML/JSON report generation for benchmark-attack."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPORT_DIR = Path(__file__).resolve().parent


def _benchmark_path_overview_script() -> str:
    return (_REPORT_DIR / "benchmark_path_overview.js").read_text(encoding="utf-8")


def _pct(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return (100.0 * num) / den


def _preview(text: str, max_len: int = 100) -> str:
    t = text.replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _path_overview_json_for_script(payload: dict[str, Any]) -> str:
    ov = payload.get("attack_path_overview") or {"sankey": {"nodes": [], "links": []}, "path_signatures": []}
    raw = json.dumps(ov, ensure_ascii=False)
    return raw.replace("</script>", "<\\/script>")


def _path_signatures_table_html(overview: dict[str, Any] | None) -> str:
    ov = overview if isinstance(overview, dict) else {}
    rows = ov.get("path_signatures") or []
    total_d = int(ov.get("path_signature_total_distinct") or 0)
    if not rows:
        return "<p class='meta'>No path signatures to list.</p>"
    body = "".join(
        "<tr>"
        f"<td>{html.escape(str(r.get('signature', '')))}</td>"
        f"<td class='num'>{int(r.get('count', 0))}</td>"
        f"<td class='ok'>{int(r.get('final_success', 0))}</td>"
        f"<td class='bad'>{int(r.get('final_failure', 0))}</td>"
        "</tr>"
        for r in rows
    )
    note = (
        f"<p class='meta'>Showing top {len(rows)} of {total_d} distinct path shapes (sorted by count).</p>"
        if total_d > len(rows)
        else "<p class='meta'>Distinct path shapes in this run (sorted by count).</p>"
    )
    return (
        note
        + "<table class='data path-signatures-table'><thead><tr>"
        "<th>Path shape (logged steps → final outcome)</th>"
        "<th>Count</th><th>Final PASS</th><th>Final FAIL</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def build_benchmark_html(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    metrics = payload["metrics"]
    templates = payload["templates"]
    prompt_rows = payload["prompts"]
    path_overview_json = _path_overview_json_for_script(payload)
    path_signatures_html = _path_signatures_table_html(payload.get("attack_path_overview"))
    path_overview_js = _benchmark_path_overview_script()

    title = html.escape(str(meta.get("report_title") or "LLM security benchmark report"))
    org = meta.get("report_organization")
    org_html = f'<p class="org">{html.escape(str(org))}</p>' if org else ""

    stage = metrics["stage"]
    total = metrics["total_prompts"]
    final_success = metrics["final_success"]
    final_failure = metrics["final_failure"]
    asr = _pct(final_success, total)

    template_rows = "".join(
        f"<tr><td>{html.escape(t['template'])}</td><td>{t['attempted']}</td><td>{t['rescued']}</td>"
        f"<td>{_pct(t['rescued'], t['attempted']):.1f}%</td></tr>"
        for t in templates
    )
    if not template_rows:
        template_rows = "<tr><td colspan='4'>No template retries were executed.</td></tr>"

    final_result_rows: list[str] = []
    for p in prompt_rows:
        idx = p["index"]
        obj = str(p.get("objective") or "")
        pv = html.escape(_preview(obj))
        jb = "Y" if p.get("jailbreak_attempted") else "N"
        tap = "Y" if p.get("tap_applied") else "N"
        status = "PASS" if p["success"] else "FAIL"
        status_cls = "ok" if p["success"] else "bad"
        base = html.escape(obj)
        final_p = html.escape(str(p.get("final_prompt") or obj))
        win_lbl = p.get("winning_step_label")
        win_meta = ""
        if p.get("success") and win_lbl:
            win_meta = (
                f'<p class="meta"><strong>Winning strategy:</strong> {html.escape(str(win_lbl))}</p>'
            )
        resp = html.escape(str(p.get("final_response") or "—"))
        reason = html.escape(str(p.get("outcome_reason") or "—"))
        score_raw = p.get("score_summary")
        score_block = ""
        if score_raw:
            score_block = (
                "<h4>Scorer detail (truncated)</h4>"
                f"<pre>{html.escape(str(score_raw))}</pre>"
            )
        fp_heading = (
            "Final prompt (winning attempt)"
            if p.get("success")
            else "Final prompt (last characterized attempt)"
        )
        final_result_rows.append(
            "<tr class='result-row'>"
            f"<td class='num'>{idx}</td>"
            "<td colspan='4'>"
            "<details class='result-details'>"
            f"<summary><span class='sum-num'>#{idx}</span> "
            f"<span class='sum-preview'>{pv}</span> "
            f"<span class='sum-meta'>Jailbreak: {jb} · TAP: {tap} · "
            f"<span class='{status_cls}'>{status}</span></span></summary>"
            "<div class='detail-body'>"
            "<h4>Base prompt</h4>"
            f"<pre>{base}</pre>"
            f"<h4>{fp_heading}</h4>"
            f"{win_meta}"
            f"<pre>{final_p}</pre>"
            "<h4>Response</h4>"
            f"<pre>{resp}</pre>"
            "<h4>Outcome reason</h4>"
            f"<pre>{reason}</pre>"
            f"{score_block}"
            "</div>"
            "</details>"
            "</td>"
            "</tr>"
        )
    final_results_tbody = "".join(final_result_rows)

    exec_summary = (
        f"This run evaluated <strong>{total}</strong> prompts from the configured dataset against "
        f"<strong>{html.escape(str(meta.get('objective_target', '')))}</strong>, using a staged pipeline: "
        "baseline evaluation, jailbreak-template retries on failures, and tree-based escalation (TAP) on a "
        f"subset of remaining failures (top-{meta.get('tap_top_k', 'K')}). "
        f"Final attack success rate (ASR) was <strong>{asr:.1f}%</strong> "
        f"({final_success} passed, {final_failure} failed). "
        "Outcomes use automated scorers and are indicative; interpret alongside policy and human review."
    )

    cfg_lines = [
        f"<li><strong>Objective target:</strong> {html.escape(str(meta.get('objective_target', '')))}</li>",
        f"<li><strong>Dataset:</strong> {html.escape(str(meta.get('dataset', '')))}</li>",
        f"<li><strong>Templates (cap):</strong> {meta.get('template_count', '—')}</li>",
        f"<li><strong>TAP top-K:</strong> {meta.get('tap_top_k', '—')}</li>",
    ]
    if meta.get("adversarial_target"):
        cfg_lines.append(
            f"<li><strong>Adversarial (TAP):</strong> {html.escape(str(meta['adversarial_target']))}</li>"
        )
    if meta.get("scorer_target"):
        cfg_lines.append(
            f"<li><strong>Evaluator (scorer):</strong> {html.escape(str(meta['scorer_target']))}</li>"
        )
    if meta.get("converter_fallback"):
        cfg_lines.append(
            "<li><strong>Converter fallback:</strong> enabled "
            f"(max stacks: {html.escape(str(meta.get('max_converter_stacks', '')))})</li>"
        )
    cfg_ul = "".join(cfg_lines)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f4f5f7;
      --surface: #ffffff;
      --fg: #1c1e24;
      --muted: #5c6370;
      --border: #dfe3e8;
      --accent: #0b5fff;
      --ok: #0d8050;
      --bad: #b32525;
    }}
    body {{ margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--fg); line-height: 1.5; font-size: 15px; }}
    .wrap {{ max-width: 1000px; margin: 0 auto; padding: 32px 20px 56px; }}
    header {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
      padding: 22px 24px; margin-bottom: 24px; }}
    h1 {{ font-size: 1.45rem; font-weight: 600; margin: 0 0 6px; color: var(--fg); }}
    .org {{ margin: 0 0 12px; color: var(--muted); font-size: 0.95rem; }}
    .meta {{ margin: 0; font-size: 0.85rem; color: var(--muted); }}
    main section {{ margin-bottom: 28px; }}
    h2 {{ font-size: 1.05rem; font-weight: 600; margin: 0 0 12px; padding-bottom: 8px;
      border-bottom: 1px solid var(--border); }}
    .exec {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
      padding: 16px 18px; }}
    .exec p {{ margin: 0; }}
    ul.method {{ margin: 8px 0 0 1.1rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
    @media (max-width: 820px) {{ .grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
    .card .k {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }}
    .card .v {{ font-size: 1.45rem; font-weight: 600; margin-top: 6px; }}
    .ok {{ color: var(--ok); font-weight: 600; }}
    .bad {{ color: var(--bad); font-weight: 600; }}
    table.data {{ width: 100%; border-collapse: collapse; background: var(--surface);
      border: 1px solid var(--border); border-radius: 10px; overflow: hidden; font-size: 0.88rem; }}
    table.data th, table.data td {{ border-bottom: 1px solid var(--border); padding: 10px 12px; text-align: left; vertical-align: top; }}
    table.data th {{ background: #f9fafb; font-weight: 600; }}
    table.data tr:last-child td {{ border-bottom: none; }}
    td.num {{ width: 3rem; font-weight: 600; background: #fafbfc; }}
    pre {{ white-space: pre-wrap; word-break: break-word; margin: 6px 0 0; font-size: 0.82rem;
      line-height: 1.45; background: #f9fafb; padding: 10px; border-radius: 8px; border: 1px solid var(--border); }}
    details.result-details summary {{
      cursor: pointer; list-style: none; padding: 8px 0;
    }}
    details.result-details summary::-webkit-details-marker {{ display: none; }}
    .sum-preview {{ color: var(--muted); margin-left: 8px; }}
    .sum-meta {{ margin-left: 12px; font-size: 0.85rem; }}
    .sum-num {{ font-weight: 600; }}
    .detail-body {{ padding: 12px 0 8px; }}
    .detail-body h4 {{ margin: 14px 0 6px; font-size: 0.8rem; text-transform: uppercase;
      letter-spacing: 0.04em; color: var(--muted); }}
    .detail-body h4:first-child {{ margin-top: 0; }}
    footer {{ margin-top: 40px; padding-top: 18px; border-top: 1px solid var(--border);
      font-size: 0.8rem; color: var(--muted); }}
    @media print {{
      body {{ background: #fff; }}
      details.result-details {{ page-break-inside: avoid; }}
      details.result-details summary {{ color: #000; }}
    }}
    #path-overview-sankey-panel {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 16px 16px; margin-top: 10px; }}
    #path-overview-sankey-svg {{ display: block; font: 11px system-ui, sans-serif; max-width: 100%; height: auto; }}
    .path-overview-sankey-link {{ fill: none; }}
    .path-signatures-table td:first-child {{ font-size: 0.82rem; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>{title}</h1>
      {org_html}
      <p class="meta">Generated (UTC): <strong>{html.escape(str(meta.get("generated_at", "")))}</strong></p>
      <ul class="meta" style="list-style:none;padding-left:0;margin-top:10px;">{cfg_ul}</ul>
    </header>
    <main>
      <section>
        <h2>Executive summary</h2>
        <div class="exec"><p>{exec_summary}</p></div>
      </section>
      <section>
        <h2>Methodology</h2>
        <ul class="method">
          <li><strong>Baseline:</strong> Each prompt is evaluated without a jailbreak template; success reflects the configured objective scorer (inverted refusal for prompt-sending in this benchmark).</li>
          <li><strong>Converter fallback (optional):</strong> If enabled for this run, failed prompts are retried with stateless converter stacks on the victim path after baseline, again with templates, and TAP may be attempted once per stack.</li>
          <li><strong>Jailbreak templates:</strong> Prompts that fail baseline are retried with bundled template variants (subject to the configured template cap).</li>
          <li><strong>TAP fallback:</strong> Up to K unresolved prompts are escalated using tree-based search on the <strong>same base objective</strong> as baseline (not jailbreak-template text); success uses the TAP float threshold scorer.</li>
        </ul>
      </section>
      <section>
        <h2>Metric definitions</h2>
        <ul class="method">
          <li><strong>ASR (attack success rate):</strong> Final passes divided by total prompts in this run.</li>
          <li><strong>Stage uplift:</strong> Cumulative success counts after baseline, after templates, and after TAP.</li>
          <li><strong>Outcome reason:</strong> From the attack result when available, plus a short fallback explanation.</li>
        </ul>
      </section>
      <section>
        <h2>Key results</h2>
        <div class="grid">
          <div class="card"><div class="k">Total prompts</div><div class="v">{total}</div></div>
          <div class="card"><div class="k">Final success</div><div class="v ok">{final_success}</div></div>
          <div class="card"><div class="k">Final failure</div><div class="v bad">{final_failure}</div></div>
          <div class="card"><div class="k">Final ASR</div><div class="v">{asr:.1f}%</div></div>
        </div>
      </section>
      <section>
        <h2>Stage uplift</h2>
        <table class="data">
          <thead><tr><th>Stage</th><th>Success count</th><th>ASR</th></tr></thead>
          <tbody>
            <tr><td>Baseline</td><td>{stage['baseline_success']}</td><td>{_pct(stage['baseline_success'], total):.1f}%</td></tr>
            <tr><td>After templates</td><td>{stage['template_success']}</td><td>{_pct(stage['template_success'], total):.1f}%</td></tr>
            <tr><td>After TAP fallback</td><td>{stage['tap_success']}</td><td>{_pct(stage['tap_success'], total):.1f}%</td></tr>
          </tbody>
        </table>
      </section>
      <section>
        <h2>Aggregate path flow</h2>
        <p class="meta">Scaled summary for large runs. The <strong>Sankey</strong> diagram sums how many prompts move between each logged stage and the final outcome (band width = prompt count). Intermediate nodes are keyed by <strong>step index, stage id, and scorer outcome</strong> so the same stage at different depths stays distinct. <span class="ok">Green</span> step nodes: defense held on that attempt; <span class="bad">red</span> step nodes: jailbreak signal on that attempt; terminal nodes are final PASS vs FAIL. Requires JavaScript and the d3-sankey plugin (CDN). The table lists the most frequent full path shapes (exact step labels and outcomes).</p>
        <h3 style="font-size:0.95rem;margin:18px 0 8px;">Flow by stage</h3>
        <div id="path-overview-sankey-panel">
          <svg id="path-overview-sankey-svg" role="img" aria-label="Aggregate path flow Sankey diagram"></svg>
        </div>
        <h3 style="font-size:0.95rem;margin:22px 0 8px;">Top path shapes</h3>
        {path_signatures_html}
      </section>
      <section>
        <h2>Template effectiveness</h2>
        <table class="data">
          <thead><tr><th>Template</th><th>Attempted</th><th>Rescued</th><th>Rescue rate</th></tr></thead>
          <tbody>{template_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Final results</h2>
        <p class="meta" style="margin-bottom:12px;">Click a row to expand base prompt, final prompt, model response, and outcome reason.</p>
        <table class="data">
          <thead><tr><th>#</th><th colspan="4">Result (expand for details)</th></tr></thead>
          <tbody>{final_results_tbody}</tbody>
        </table>
      </section>
    </main>
    <script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js" crossorigin="anonymous"></script>
    <script type="application/json" id="bench-path-overview-json">{path_overview_json}</script>
    <script>
{path_overview_js}
    </script>
    <footer>
      Confidential — for authorized security testing only. Do not distribute outside approved channels.
      Automated scoring may not match human judgment or production safety policies.
    </footer>
  </div>
</body>
</html>
"""


def write_benchmark_artifacts(*, output_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "report.html"
    json_path = output_dir / "results.json"
    html_path.write_text(build_benchmark_html(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return html_path, json_path


def build_meta(
    *,
    objective_target: str,
    dataset: str,
    adversarial_target: str | None,
    scorer_target: str | None,
    template_count: int,
    tap_top_k: int,
    report_title: str | None = None,
    report_organization: str | None = None,
    converter_fallback: bool = False,
    max_converter_stacks: int = 3,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "objective_target": objective_target,
        "dataset": dataset,
        "adversarial_target": adversarial_target,
        "scorer_target": scorer_target,
        "template_count": template_count,
        "tap_top_k": tap_top_k,
        "report_title": report_title or "LLM security benchmark report",
        "report_organization": report_organization,
        "converter_fallback": converter_fallback,
        "max_converter_stacks": max_converter_stacks,
    }
