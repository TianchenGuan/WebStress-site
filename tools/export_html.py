import json
import os
import html
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple


def _safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def _escape(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return str(val)
    return html.escape(str(val))


def _truncate(s: Any, n: int = 80) -> str:
    if s is None:
        return ""
    t = str(s)
    return t if len(t) <= n else t[: n - 1] + "…"


def _describe_feature_config(cfg: Optional[Dict[str, Any]]) -> str:
    if not isinstance(cfg, dict) or not cfg:
        return "default"
    parts: List[str] = []
    gran = cfg.get("observation_granularity")
    if isinstance(gran, str):
        parts.append(f"gran={gran}")
    bool_flags = sorted([k for k, v in cfg.items() if isinstance(v, bool) and v])
    if bool_flags:
        parts.append("flags=" + ",".join(bool_flags))
    failure = cfg.get("failure_feedback")
    if isinstance(failure, dict):
        fb_flags = sorted([k for k, v in failure.items() if isinstance(v, bool) and v])
        if fb_flags:
            parts.append("failure=" + ",".join(fb_flags))
    return "; ".join(parts) if parts else "custom"


@lru_cache(maxsize=512)
def _read_json_file(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_llm_payload(log_dir: str, episode_id: str, role: str, step: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not log_dir or not episode_id:
        return None, None
    llm_dir = os.path.join(log_dir, str(episode_id), "llm")
    if role == "agent":
        fname = f"agent_step_{step:04d}.json"
    elif role == "simulator":
        fname = f"simulator_step_{step:04d}.json"
    else:
        return None, None
    path = os.path.join(llm_dir, fname)
    payload = _read_json_file(path)
    if not payload:
        return None, None
    rel = f"../{episode_id}/llm/{fname}"
    return payload, rel


def _render_table_rows(steps: List[Dict[str, Any]]) -> str:
    rows = []
    for idx, st in enumerate(steps):
        action = st.get("action") or {}
        atype = action.get("type") if isinstance(action, dict) else None
        tgt = action.get("target") if isinstance(action, dict) else None
        tid = tgt.get("element_id") if isinstance(tgt, dict) else None
        if not tid and isinstance(tgt, dict) and ("x" in tgt or "y" in tgt):
            tid = f"({tgt.get('x')},{tgt.get('y')})"
        res = _safe_get(st, ["internal_result", "result"], "")
        reason = _safe_get(st, ["internal_result", "reason"], "")
        page = _safe_get(st, ["observation", "meta", "page"], "")
        diffs = st.get("state_diff")
        diff_str = ", ".join(diffs) if isinstance(diffs, list) else ""
        t = st.get("t")
        rows.append(
            f"<tr>"
            f"<td>{idx}</td>"
            f"<td>{_escape(t)}</td>"
            f"<td>{_escape(atype)}</td>"
            f"<td>{_escape(tid)}</td>"
            f"<td>{_escape(res)}</td>"
            f"<td class=reason title='{_escape(reason)}'>{_escape(reason)}</td>"
            f"<td>{_escape(page)}</td>"
            f"<td class=diffs title='{_escape(diff_str)}'>{_escape(diff_str)}</td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _pretty(obj: Any) -> str:
    try:
        return html.escape(json.dumps(obj, indent=2, ensure_ascii=False))
    except Exception:
        return html.escape(str(obj))


def _action_block(action: Dict[str, Any]) -> str:
    if not isinstance(action, dict):
        return "<div class=card><div class=empty>no action</div></div>"
    at = _escape(action.get("type"))
    tgt = action.get("target") if isinstance(action.get("target"), dict) else {}
    tid = _escape(tgt.get("element_id")) if isinstance(tgt, dict) else ""
    coords = ""
    if isinstance(tgt, dict) and ("x" in tgt or "y" in tgt):
        coords = f"({_escape(tgt.get('x'))},{_escape(tgt.get('y'))})"
    text = _truncate(action.get("text")) if action.get("text") else None
    keys = ", ".join(action.get("keys", [])) if isinstance(action.get("keys"), list) else None
    deltas = None
    if "delta_y" in action or "delta_x" in action:
        deltas = f"dx={_escape(action.get('delta_x'))} dy={_escape(action.get('delta_y'))}"
    meta_parts = []
    if tid:
        meta_parts.append(f"target {tid}")
    if coords:
        meta_parts.append(coords)
    if text:
        meta_parts.append(f"text: {_escape(text)}")
    if keys:
        meta_parts.append(f"keys: {_escape(keys)}")
    if deltas:
        meta_parts.append(deltas)
    meta = " | ".join(meta_parts)
    return (
        f"<div class=card>"
        f"<div class=title>Action: <span class=badge>{at}</span></div>"
        f"<div class=meta>{_escape(meta)}</div>"
        f"<details><summary>Raw action JSON</summary><pre>{_pretty(action)}</pre></details>"
        f"</div>"
    )


def _obs_block(obs: Dict[str, Any], highlight_element_id: Optional[str] = None) -> str:
    if not isinstance(obs, dict):
        return "<div class=card><div class=empty>no observation</div></div>"
    ts = _escape(obs.get("timestamp"))
    sid = _escape(obs.get("screenshot_id"))
    meta = obs.get("meta") or {}
    page = _escape(meta.get("page")) if isinstance(meta, dict) else ""
    uis = obs.get("ui_elements") or []
    auds = obs.get("audio_events") or []
    count_ui = len(uis) if isinstance(uis, list) else 0
    count_aud = len(auds) if isinstance(auds, list) else 0
    # Build UI table for all elements (folded when long)
    rows_all: List[str] = []
    if isinstance(uis, list):
        for e in uis:
            if not isinstance(e, dict):
                continue
            eid = str(e.get('element_id')) if 'element_id' in e else ''
            cls = ' class=hit' if highlight_element_id and str(highlight_element_id) == eid else ''
            rows_all.append(
                f"<tr{cls}>"
                f"<td>{_escape(eid)}</td>"
                f"<td>{_escape(e.get('role'))}</td>"
                f"<td>{_escape(_truncate(e.get('text'), 80))}</td>"
                f"</tr>"
            )
    if rows_all:
        preview_rows = rows_all[:15]
        preview_table = (
            "<table class=mini>\n<thead><tr><th>element_id</th><th>role</th><th>text</th></tr></thead>\n<tbody>"
            + "\n".join(preview_rows)
            + "</tbody></table>"
        )
        if len(rows_all) > 15:
            details_attr = "" if count_ui and count_ui > 40 else " open"
            full_table = (
                "<table class=mini>\n<thead><tr><th>element_id</th><th>role</th><th>text</th></tr></thead>\n<tbody>"
                + "\n".join(rows_all)
                + "</tbody></table>"
            )
            ui_table = (
                preview_table
                + f"<div class=muted>showing first 15 of {count_ui} elements</div>"
                + f"<details class=ui-elements{details_attr}>"
                + f"<summary>Expand to see all {count_ui} elements</summary>"
                + f"<div class=scroll>{full_table}</div>"
                + "</details>"
            )
        else:
            ui_table = preview_table
    else:
        ui_table = "<div class=muted>no ui elements</div>"
    # Selected element details (if we can locate it)
    sel_html = ""
    if highlight_element_id and isinstance(uis, list):
        sel = None
        for e in uis:
            if isinstance(e, dict) and str(e.get('element_id')) == str(highlight_element_id):
                sel = e
                break
        if isinstance(sel, dict):
            attrs = sel.get('attributes') if isinstance(sel.get('attributes'), dict) else {}
            attr_rows = []
            for ak, av in list(attrs.items())[:12]:
                attr_rows.append(f"<tr><td>{_escape(ak)}</td><td>{_escape(_truncate(av, 80))}</td></tr>")
            attr_table = (
                "<table class=mini><thead><tr><th>attr</th><th>value</th></tr></thead><tbody>" + "".join(attr_rows) + "</tbody></table>"
                if attr_rows
                else "<div class=muted>no attributes</div>"
            )
            sel_html = (
                f"<div class=card>"
                f"<div class=title>Selected element: {_escape(sel.get('element_id'))}</div>"
                f"<div class=meta>role {_escape(sel.get('role'))} | text {_escape(_truncate(sel.get('text'), 120))}</div>"
                f"{attr_table}"
                f"</div>"
            )
    return (
        f"<div class=card>"
        f"<div class=title>Observation</div>"
        f"<div class=meta>time {ts} | page {page} | screenshot {sid} | ui {count_ui} | audio {count_aud}</div>"
        f"{ui_table}"
        f"{sel_html}"
        f"<details><summary>Raw observation JSON</summary><pre>{_pretty(obs)}</pre></details>"
        f"</div>"
    )


def _state_block(step: Dict[str, Any], sim_entry: Optional[Dict[str, Any]]) -> str:
    digest = _escape(step.get("state_digest"))
    diffs = step.get("state_diff")
    diff_str = ", ".join(diffs) if isinstance(diffs, list) else ""
    # Try to present snapshot if available
    snap = None
    if isinstance(sim_entry, dict):
        snap = sim_entry.get("state_snapshot")
    if isinstance(snap, dict):
        page = _escape(snap.get("page"))
        win_count = len(snap.get("windows", [])) if isinstance(snap.get("windows"), list) else "-"
        ui_count = len(snap.get("ui_elements", [])) if isinstance(snap.get("ui_elements"), list) else "-"
        fs = snap.get("filesystem")
        fs_keys = ", ".join(list(fs.keys())[:8]) if isinstance(fs, dict) else "-"
        clip = snap.get("clipboard")
        clip_len = len(clip) if isinstance(clip, str) else 0
        meta_line = f"page {page} | windows {win_count} | ui {ui_count} | fs keys [{_escape(fs_keys)}] | clipboard {clip_len} chars"
        details = f"<details><summary>State snapshot (raw)</summary><pre>{_pretty(snap)}</pre></details>"
        diff_line = f"diff: {_escape(diff_str)} | digest: {digest}" if diff_str or digest else ""
        return f"<div class=card><div class=title>State</div><div class=meta>{meta_line}</div><div class=muted>{diff_line}</div>{details}</div>"
    # Fallback: only diff/digest
    if diff_str or digest:
        return f"<div class=card><div class=title>State</div><div class=meta>digest {digest}</div><div class=muted>diff { _escape(diff_str) }</div></div>"
    return "<div class=card><div class=empty>no state info</div></div>"


def _llm_context_block(title: str, payload: Optional[Dict[str, Any]], rel_path: Optional[str]) -> str:
    if not payload:
        return (
            f"<details class=ctx>"
            f"<summary>{_escape(title)}</summary>"
            f"<div class=card><div class=empty>payload not found (enable verbose LLM logging)</div></div>"
            f"</details>"
        )
    meta_bits: List[str] = []
    model = payload.get("model")
    if model:
        meta_bits.append(f"model {_escape(model)}")
    ts = payload.get("ts")
    if ts:
        meta_bits.append(f"ts {_escape(ts)}")
    if rel_path:
        meta_bits.append(f"<a href=\"{_escape(rel_path)}\">source JSON</a>")
    meta_html = f"<div class=meta>{' | '.join(meta_bits)}</div>" if meta_bits else ""
    sys_prompt = payload.get("system_prompt")
    sys_html = (
        f"<div><strong>System prompt</strong><pre>{_escape(sys_prompt)}</pre></div>"
        if sys_prompt
        else "<div class=muted>no system prompt recorded</div>"
    )
    user_json = payload.get("user_json")
    user_html = (
        f"<div><strong>User payload JSON</strong><pre>{_pretty(user_json)}</pre></div>"
        if user_json is not None
        else "<div class=muted>no user payload recorded</div>"
    )
    return (
        f"<details class=ctx>"
        f"<summary>{_escape(title)}</summary>"
        f"<div class=card>"
        f"{meta_html}"
        f"{sys_html}"
        f"{user_html}"
        f"</div>"
        f"</details>"
    )


def _instruction_block(instr: Optional[Dict[str, Any]], fallback_id: Optional[str] = None) -> str:
    if not isinstance(instr, dict):
        if fallback_id:
            return f"<div class=card><div class=title>Instruction</div><div class=meta>id {fallback_id}</div></div>"
        return ""
    iid = _escape(instr.get("id"))
    desc = _escape(instr.get("description"))
    template = _escape(instr.get("template"))
    difficulty = _escape(instr.get("difficulty"))
    time_limit = _escape(instr.get("time_limit"))
    crit = instr.get("success_criteria") or []
    items = []
    if isinstance(crit, list):
        for c in crit[:20]:
            if not isinstance(c, dict):
                continue
            pred = _escape(c.get("predicate"))
            weight = c.get("weight")
            notes = c.get("notes")
            suffix = []
            if weight is not None:
                suffix.append(f"w={_escape(weight)}")
            if notes:
                suffix.append(_escape(notes))
            tail = f" <span class=muted>({' | '.join(suffix)})</span>" if suffix else ""
            items.append(f"<li>{pred}{tail}</li>")
    list_html = f"<ul>\n{''.join(items)}\n</ul>" if items else "<div class=muted>no success criteria</div>"
    meta = f"id {iid} | template {template} | difficulty {difficulty} | time_limit {time_limit}s"
    return (
        f"<div class=card>"
        f"<div class=title>Instruction</div>"
        f"<div class=meta>{meta}</div>"
        f"<div>{desc}</div>"
        f"<details><summary>Success criteria</summary>{list_html}</details>"
        f"<details><summary>Raw instruction JSON</summary><pre>{_pretty(instr)}</pre></details>"
        f"</div>"
    )


def _settings_block(ep: Dict[str, Any]) -> str:
    seed = _escape(ep.get("seed"))
    fidelity = _escape(ep.get("fidelity"))
    features = ep.get("sim_feature_config") if isinstance(ep.get("sim_feature_config"), dict) else None
    sim_features = _escape(_describe_feature_config(features))
    ah = _escape(ep.get("agent_history"))
    inc_state = _escape(ep.get("sim_include_state"))
    comps = ep.get("components") if isinstance(ep.get("components"), dict) else {}
    comps_pre = f"<pre>{_pretty(comps)}</pre>" if comps else "<div class=muted>no components info</div>"
    features_pre = f"<details><summary>Simulator feature config</summary><pre>{_pretty(features)}</pre></details>" if features else "<div class=muted>sim features: default</div>"
    items = """
      <ul>
        <li>seed: {seed}</li>
        <li>fidelity: {fidelity}</li>
        <li>sim_features: {sim_features}</li>
        <li>agent_history: {ah}</li>
        <li>sim_include_state: {inc_state}</li>
      </ul>
    """.format(seed=seed, fidelity=fidelity, sim_features=sim_features, ah=ah, inc_state=inc_state)
    return items + comps_pre + features_pre


def _subscores_block(jd: Dict[str, Any]) -> str:
    ss = jd.get("subscores")
    if not isinstance(ss, dict) or not ss:
        return ""
    rows = []
    for k, v in ss.items():
        rows.append(f"<tr><td>{_escape(k)}</td><td>{_escape(v)}</td></tr>")
    table = "<table class=mini><thead><tr><th>metric</th><th>value</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    return f"<details><summary>Judge subscores</summary>{table}</details>"


def _load_sim_by_step(log_dir: str, episode_id: str) -> Dict[int, Dict[str, Any]]:
    by_step: Dict[int, Dict[str, Any]] = {}
    sim_path = os.path.join(log_dir, episode_id, "simulator.log.jsonl")
    if not os.path.exists(sim_path):
        return by_step
    try:
        with open(sim_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                step = rec.get("step")
                if isinstance(step, int):
                    by_step[step] = rec
    except Exception:
        return by_step
    return by_step


def _load_initial_observation(episode: Dict[str, Any], log_dir: str, episode_id: str) -> Optional[Dict[str, Any]]:
    obs = episode.get("initial_observation")
    if isinstance(obs, dict):
        return obs
    sim_path = os.path.join(log_dir, episode_id, "simulator.log.jsonl")
    if not os.path.exists(sim_path):
        return None
    try:
        with open(sim_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("phase") == "reset":
                    init_obs = rec.get("observation")
                    if isinstance(init_obs, dict):
                        return init_obs
                    break
    except Exception:
        return None
    return None


def _render_html(episode: Dict[str, Any], judgement: Dict[str, Any], log_dir: str) -> str:
    eid = episode.get("episode_id", "episode")
    instr_id = _escape(episode.get("instruction_id"))
    score = _escape(judgement.get("score"))
    feedback = _escape(judgement.get("feedback"))
    steps = episode.get("steps") or []
    rows = _render_table_rows(steps)
    # Instruction block (if available)
    instruction = episode.get("instruction") if isinstance(episode.get("instruction"), dict) else None
    instruction_html = _instruction_block(instruction, fallback_id=instr_id)
    # Settings block (folded)
    settings_html = _settings_block(episode)
    # Subscores (folded)
    subscores_html = _subscores_block(judgement)
    # Load sim logs to enrich state snapshots per step
    sim_by_step = _load_sim_by_step(log_dir, str(eid))
    initial_obs = _load_initial_observation(episode, log_dir, str(eid))
    if initial_obs:
        initial_obs_html = f"<section class=initial><h2>Initial Observation</h2>{_obs_block(initial_obs)}</section>"
    else:
        initial_obs_html = ""
    # Build per-step details cards
    detail_cards: List[str] = []
    for idx, st in enumerate(steps):
        action = st.get("action") or {}
        obs = st.get("observation") or {}
        highlight_eid = None
        if isinstance(action, dict):
            tgt = action.get("target") if isinstance(action.get("target"), dict) else {}
            if isinstance(tgt, dict):
                highlight_eid = tgt.get("element_id")
        sim_entry = sim_by_step.get(idx)
        action_html = _action_block(action)
        obs_html = _obs_block(obs, highlight_element_id=highlight_eid)
        state_html = _state_block(st, sim_entry)
        agent_payload, agent_rel = _load_llm_payload(log_dir, str(eid), "agent", idx)
        sim_payload, sim_rel = _load_llm_payload(log_dir, str(eid), "simulator", idx)
        ctx_row = (
            f"<div class=row>"
            f"  <div class=col>{_llm_context_block('Agent LLM input', agent_payload, agent_rel)}</div>"
            f"  <div class=col>{_llm_context_block('Simulator LLM input', sim_payload, sim_rel)}</div>"
            f"</div>"
        )
        detail_cards.append(
            (
                f"<section class=step id='step-{idx}'>"
                f"<h3>Step {idx}</h3>"
                f"<div class=row>"
                f"  <div class=col>{action_html}</div>"
                f"  <div class=col>{obs_html}</div>"
                f"</div>"
                f"<div class=row>"
                f"  <div class=col>{state_html}</div>"
                f"</div>"
                f"{ctx_row}"
                f"</section>"
            )
        )
    details_html = "\n".join(detail_cards)
    # Link to raw logs
    base = f"../{eid}"
    html_log = f"../{eid}.log.json"
    html_judge = f"../{eid}.judge.json"
    agent_readable = f"{base}/agent.readable.log"
    sim_readable = f"{base}/simulator.readable.log"
    judge_readable = f"{base}/judge.readable.log"
    llm_dir = f"{base}/llm/"
    style = """
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,'Helvetica Neue',Arial,'Noto Sans',sans-serif;margin:20px;color:#1b1f23}
      h1{font-size:22px;margin:0 0 8px}
      h2{font-size:18px;margin-top:28px}
      .meta{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px}
      .tag{background:#f4f6f8;border:1px solid #e5e7eb;border-radius:6px;padding:6px 10px}
      table{border-collapse:collapse;width:100%;font-size:13px}
      th,td{border:1px solid #e5e7eb;padding:6px 8px;vertical-align:top}
      th{background:#f9fafb;text-align:left;position:sticky;top:0}
      .reason{max-width:320px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .diffs{max-width:320px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .links{margin:8px 0 16px}
      .links a{margin-right:12px;}
      .footer{margin-top:18px;color:#6b7280;font-size:12px}
      .row{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0}
      .col{flex:1 1 360px}
      .card{border:1px solid #e5e7eb;border-radius:8px;padding:10px;background:#fff}
      .card .title{font-weight:600;margin-bottom:4px}
      .badge{display:inline-block;background:#eef2ff;border:1px solid #dbeafe;border-radius:999px;padding:2px 8px;font-size:12px}
      .meta, .muted{color:#6b7280;font-size:12px}
      .empty{color:#9ca3af}
      .initial{margin:24px 0}
      pre{background:#0b1020;color:#e5e7eb;padding:10px;border-radius:6px;overflow:auto;max-height:300px}
      table.mini{border-collapse:collapse;width:100%;font-size:12px;margin-top:6px}
      table.mini th, table.mini td{border:1px solid #eef2f7;padding:4px 6px}
      table.mini tr.hit{background:#fffbeb}
      details{margin:10px 0}
      details > summary{cursor:pointer;font-weight:600}
      .scroll{max-height:320px;overflow:auto;margin-top:6px}
    </style>
    """
    script = """
    <script>
      // future JS hooks if needed
    </script>
    """
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset='utf-8'/>
    <title>LLMOS Episode {eid} Summary</title>
    {style}
  </head>
  <body>
    <h1>Episode {eid}</h1>
    <div class=meta>
      <div class=tag><b>Instruction</b>: {instr_id}</div>
      <div class=tag><b>Score</b>: {score}</div>
      <div class=tag><b>Steps</b>: {len(steps)}</div>
    </div>
    {initial_obs_html}
    {instruction_html}
    <details><summary>Settings</summary>
      {settings_html}
    </details>
    <div class=links>
      <a href='{html_log}'>raw episode JSON</a>
      <a href='{html_judge}'>raw judge JSON</a>
      <a href='{agent_readable}'>agent.readable.log</a>
      <a href='{sim_readable}'>simulator.readable.log</a>
      <a href='{judge_readable}'>judge.readable.log</a>
      <a href='{llm_dir}'>llm/ dumps</a>
    </div>
    {subscores_html}
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Time</th>
          <th>Action</th>
          <th>Target</th>
          <th>Result</th>
          <th>Reason</th>
          <th>Page</th>
          <th>Diff keys</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    <h2>Detailed Per-Step</h2>
    {details_html}
    <div class=footer>
      Feedback: {feedback}
    </div>
    {script}
  </body>
</html>
"""


def export_episode_html(log_dir: str, episode_id: Optional[str] = None) -> Optional[str]:
    os.makedirs(log_dir, exist_ok=True)
    # Determine episode_id if not provided: pick latest *.log.json
    if not episode_id:
        candidates = [f for f in os.listdir(log_dir) if f.endswith('.log.json')]
        if not candidates:
            return None
        candidates.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)), reverse=True)
        latest = candidates[0]
        episode_id = latest.replace('.log.json', '')
    # Load episode and judge
    ep_path = os.path.join(log_dir, f"{episode_id}.log.json")
    jd_path = os.path.join(log_dir, f"{episode_id}.judge.json")
    if not os.path.exists(ep_path):
        return None
    with open(ep_path, 'r', encoding='utf-8') as f:
        episode = json.load(f)
    judgement: Dict[str, Any] = {}
    if os.path.exists(jd_path):
        with open(jd_path, 'r', encoding='utf-8') as f:
            judgement = json.load(f)
    # Where to write
    out_dir = os.path.join(log_dir, episode_id)
    os.makedirs(out_dir, exist_ok=True)
    html_out = os.path.join(out_dir, 'index.html')
    content = _render_html(episode, judgement, log_dir)
    with open(html_out, 'w', encoding='utf-8') as f:
        f.write(content)
    return html_out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Export compact HTML for a saved episode")
    p.add_argument('--log-dir', type=str, default='runs')
    p.add_argument('--episode-id', type=str, default=None, help='Episode id (defaults to latest)')
    args = p.parse_args()
    out = export_episode_html(args.log_dir, args.episode_id)
    if out:
        print(out)
    else:
        print("No episode exported.")
