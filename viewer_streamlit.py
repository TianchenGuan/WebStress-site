import os
import json
from functools import lru_cache
from typing import Any, Dict, List, Optional

import streamlit as st


def list_episodes(log_dir: str) -> List[str]:
    if not os.path.isdir(log_dir):
        return []
    eps = [f[:-9] for f in os.listdir(log_dir) if f.endswith('.log.json')]
    eps.sort()
    return eps


def load_episode(log_dir: str, eid: str) -> Dict[str, Any]:
    path = os.path.join(log_dir, f"{eid}.log.json")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_judge(log_dir: str, eid: str) -> Dict[str, Any]:
    path = os.path.join(log_dir, f"{eid}.judge.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def load_sim_by_step(log_dir: str, eid: str) -> Dict[int, Dict[str, Any]]:
    by_step: Dict[int, Dict[str, Any]] = {}
    sim_path = os.path.join(log_dir, eid, "simulator.log.jsonl")
    if not os.path.exists(sim_path):
        return by_step
    try:
        with open(sim_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                step = rec.get('step')
                if isinstance(step, int):
                    by_step[step] = rec
    except Exception:
        pass
    return by_step


def _describe_features(cfg: Optional[Dict[str, Any]]) -> str:
    if not isinstance(cfg, dict) or not cfg:
        return "default"
    parts: List[str] = []
    gran = cfg.get('observation_granularity')
    if isinstance(gran, str):
        parts.append(f"gran={gran}")
    bool_flags = sorted([k for k, v in cfg.items() if isinstance(v, bool) and v])
    if bool_flags:
        parts.append("flags=" + ",".join(bool_flags))
    failure = cfg.get('failure_feedback')
    if isinstance(failure, dict):
        fb_flags = sorted([k for k, v in failure.items() if isinstance(v, bool) and v])
        if fb_flags:
            parts.append("failure=" + ",".join(fb_flags))
    return "; ".join(parts) if parts else "custom"


def _selected_element(obs: Dict[str, Any], element_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(obs, dict) or not element_id:
        return None
    uis = obs.get('ui_elements') or []
    if isinstance(uis, list):
        for e in uis:
            if isinstance(e, dict) and str(e.get('element_id')) == str(element_id):
                return e
    return None


def _llm_payload_path(log_dir: str, eid: str, role: str, step: int) -> Optional[str]:
    if not log_dir or not eid:
        return None
    base = os.path.join(log_dir, str(eid), 'llm')
    if role == 'agent':
        fname = f"agent_step_{step:04d}.json"
    elif role == 'simulator':
        fname = 'simulator_reset.json' if step < 0 else f"simulator_step_{step:04d}.json"
    else:
        return None
    return os.path.join(base, fname)


@lru_cache(maxsize=256)
def _read_json_file(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    try:
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def step_rows(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for i, s in enumerate(steps):
        action = s.get('action') or {}
        atype = action.get('type') if isinstance(action, dict) else None
        tgt = action.get('target') if isinstance(action, dict) else None
        tid = tgt.get('element_id') if isinstance(tgt, dict) else None
        if not tid and isinstance(tgt, dict) and ('x' in tgt or 'y' in tgt):
            tid = f"({tgt.get('x')},{tgt.get('y')})"
        res = (s.get('internal_result') or {}).get('result') if isinstance(s.get('internal_result'), dict) else None
        reason = (s.get('internal_result') or {}).get('reason') if isinstance(s.get('internal_result'), dict) else None
        page = None
        obs = s.get('observation') or {}
        if isinstance(obs, dict):
            meta = obs.get('meta') or {}
            if isinstance(meta, dict):
                page = meta.get('page')
        diff = s.get('state_diff')
        if isinstance(diff, list):
            diff = ', '.join(diff)
        rows.append({
            '#': i,
            'time': s.get('t'),
            'action': atype,
            'target': tid,
            'result': res,
            'reason': reason,
            'page': page,
            'diff_keys': diff,
        })
    return rows


def render_episode(title: str, ep: Dict[str, Any], jd: Dict[str, Any], log_dir: str):
    st.subheader(title)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric('Instruction', str(ep.get('instruction_id')))
    with col2:
        st.metric('Score', jd.get('score', '-'))
    with col3:
        st.metric('Steps', len(ep.get('steps') or []))
    st.caption(jd.get('feedback', ''))
    # Instruction block
    instr = ep.get('instruction') if isinstance(ep.get('instruction'), dict) else None
    with st.expander('Instruction', expanded=True):
        if instr:
            st.write(instr.get('description'))
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric('ID', str(instr.get('id')))
            with c2:
                st.metric('Template', str(instr.get('template')))
            with c3:
                st.metric('Difficulty', str(instr.get('difficulty')))
            with c4:
                st.metric('Time Limit (s)', str(instr.get('time_limit')))
            # Success criteria
            crit = instr.get('success_criteria') or []
            if isinstance(crit, list) and crit:
                rows = []
                for c in crit:
                    if not isinstance(c, dict):
                        continue
                    rows.append({
                        'predicate': c.get('predicate'),
                        'weight': c.get('weight'),
                        'notes': c.get('notes'),
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True)
            with st.expander('Raw instruction JSON'):
                st.json(instr)
        else:
            st.info('No embedded instruction. Upgrade logs to include instruction metadata.')
    # Settings block (folded)
    with st.expander('Settings'):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric('Seed', str(ep.get('seed', '-')))
        with c2:
            st.metric('Fidelity', str(ep.get('fidelity', '-')))
        with c3:
            feat_cfg = ep.get('sim_feature_config') if isinstance(ep.get('sim_feature_config'), dict) else None
            st.metric('Sim Features', _describe_features(feat_cfg))
        c4, c5, c6 = st.columns(3)
        with c4:
            st.metric('Agent History', str(ep.get('agent_history', '-')))
        with c5:
            st.metric('Sim History', str(ep.get('sim_history', '-')))
        with c6:
            st.metric('Include State', str(ep.get('sim_include_state', '-')))
        st.caption('Components')
        st.json(ep.get('components', {}))
        st.caption('Simulator feature config')
        if feat_cfg:
            st.json(feat_cfg)
        else:
            st.info('default feature set')
    # Judge subscores (folded)
    if isinstance(jd.get('subscores'), dict) and jd.get('subscores'):
        with st.expander('Judge subscores'):
            subs = jd.get('subscores') or {}
            rows = [{'metric': k, 'value': v} for k, v in subs.items()]
            st.dataframe(rows, use_container_width=True, hide_index=True)
    steps = ep.get('steps') or []
    rows = step_rows(steps)
    st.dataframe(rows, use_container_width=True, hide_index=True)
    # Step details
    st.subheader('Step Details')
    if not steps:
        st.info('No steps recorded.')
    else:
        eid = str(ep.get('episode_id'))
        sim_by_step = load_sim_by_step(log_dir, eid)
        idx = st.slider('Select step', min_value=0, max_value=len(steps) - 1, value=len(steps) - 1, step=1)
        st.caption(f'Showing details for step {idx}')
        s = steps[idx]
        action = s.get('action') or {}
        obs = s.get('observation') or {}
        # Action target element id (for highlighting)
        target_id = None
        if isinstance(action, dict):
            tgt = action.get('target') if isinstance(action.get('target'), dict) else {}
            if isinstance(tgt, dict):
                target_id = tgt.get('element_id')
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('Action')
            st.write('- type:', action.get('type'))
            tgt = action.get('target') if isinstance(action.get('target'), dict) else {}
            if isinstance(tgt, dict):
                if 'element_id' in tgt:
                    st.write('- target element_id:', tgt.get('element_id'))
                if 'x' in tgt or 'y' in tgt:
                    st.write('- target coords:', (tgt.get('x'), tgt.get('y')))
            if action.get('text'):
                st.write('- text:', action.get('text'))
            if isinstance(action.get('keys'), list):
                st.write('- keys:', ', '.join(action.get('keys') or []))
            if 'delta_x' in action or 'delta_y' in action:
                st.write('- delta:', action.get('delta_x'), action.get('delta_y'))
            with st.expander('Raw action JSON'):
                st.json(action)
            # Internal result / event log
            ir = s.get('internal_result') or {}
            if isinstance(ir, dict):
                st.markdown('Internal Result')
                st.write('- result:', ir.get('result'))
                if ir.get('reason'):
                    st.write('- reason:', ir.get('reason'))
            if isinstance(s.get('event_log'), list):
                st.caption(f"event_log: {len(s.get('event_log') or [])} entries")
        with c2:
            st.markdown('Observation')
            meta = obs.get('meta') or {}
            st.write('- time:', obs.get('timestamp'))
            st.write('- page:', meta.get('page') if isinstance(meta, dict) else None)
            st.write('- screenshot_id:', obs.get('screenshot_id'))
            uis = obs.get('ui_elements') or []
            st.write('- ui elements:', len(uis) if isinstance(uis, list) else 0)
            # UI table (subset)
            ui_rows = []
            if isinstance(uis, list):
                for e in uis[:20]:
                    if not isinstance(e, dict):
                        continue
                    ui_rows.append({'element_id': e.get('element_id'), 'role': e.get('role'), 'text': e.get('text')})
            if ui_rows:
                st.dataframe(ui_rows, use_container_width=True, hide_index=True)
            sel = _selected_element(obs, target_id)
            if isinstance(sel, dict):
                st.markdown('Selected element')
                st.json(sel)
            with st.expander('Raw observation JSON'):
                st.json(obs)
        # State details
        st.markdown('State')
        sim_entry = sim_by_step.get(idx)
        if isinstance(sim_entry, dict) and isinstance(sim_entry.get('state_snapshot'), dict):
            snap = sim_entry.get('state_snapshot')
            page = snap.get('page')
            windows = len(snap.get('windows') or []) if isinstance(snap.get('windows'), list) else 0
            ui_count = len(snap.get('ui_elements') or []) if isinstance(snap.get('ui_elements'), list) else 0
            fs = snap.get('filesystem') if isinstance(snap.get('filesystem'), dict) else {}
            st.write('- page:', page, '| windows:', windows, '| ui elements:', ui_count, '| fs keys:', list(fs.keys())[:8])
            st.write('- diff_keys:', s.get('state_diff'))
            st.write('- digest:', s.get('state_digest'))
            with st.expander('Raw state snapshot JSON'):
                st.json(snap)
        else:
            st.write('- diff_keys:', s.get('state_diff'))
            st.write('- digest:', s.get('state_digest'))
        agent_path = _llm_payload_path(log_dir, eid, 'agent', idx)
        agent_payload = _read_json_file(agent_path)
        with st.expander('Agent LLM input (real system prompt + payload)', expanded=False):
            if agent_payload:
                if agent_path:
                    st.caption(f'Source: {agent_path}')
                system_prompt = agent_payload.get('system_prompt')
                if system_prompt:
                    st.markdown('**System prompt**')
                    st.code(system_prompt, language='markdown')
                st.markdown('**User payload JSON**')
                st.json(agent_payload.get('user_json'))
            else:
                st.info('Agent input payload not found. Enable verbose LLM logging to capture it.')
        sim_path = _llm_payload_path(log_dir, eid, 'simulator', idx)
        sim_payload = _read_json_file(sim_path)
        with st.expander('Simulator LLM input (real system prompt + payload)', expanded=False):
            if sim_payload:
                if sim_path:
                    st.caption(f'Source: {sim_path}')
                system_prompt = sim_payload.get('system_prompt')
                if system_prompt:
                    st.markdown('**System prompt**')
                    st.code(system_prompt, language='markdown')
                st.markdown('**User payload JSON**')
                st.json(sim_payload.get('user_json'))
            else:
                st.info('Simulator input payload not found. Enable verbose LLM logging to capture it.')
    with st.expander('Raw episode JSON'):
        st.json(ep)
    if jd:
        with st.expander('Raw judge JSON'):
            st.json(jd)
    # Links to files
    eid = ep.get('episode_id')
    subdir = os.path.join(log_dir, str(eid))
    if os.path.isdir(subdir):
        st.caption('Files:')
        st.write(f"- {subdir}/agent.readable.log")
        st.write(f"- {subdir}/simulator.readable.log")
        st.write(f"- {subdir}/judge.readable.log")


def main():
    st.set_page_config(page_title='LLMOS Viewer', layout='wide')
    st.title('LLMOS — Runs Viewer')
    log_dir = st.sidebar.text_input('Log directory', value='runs')
    episodes = list_episodes(log_dir)
    if not episodes:
        st.info('No episodes found. Run `orchestrator.py` to generate logs in runs/.')
        return
    st.sidebar.write(f"Found {len(episodes)} episodes")
    mode = st.sidebar.radio('Mode', ['Single', 'Compare'], horizontal=True)
    if mode == 'Single':
        eid = st.sidebar.selectbox('Episode', episodes, index=len(episodes) - 1)
        ep = load_episode(log_dir, eid)
        jd = load_judge(log_dir, eid)
        render_episode(f'Episode {eid}', ep, jd, log_dir)
    else:
        c1, c2 = st.columns(2)
        with c1:
            eid1 = st.selectbox('Episode A', episodes, index=max(0, len(episodes) - 2), key='a')
        with c2:
            eid2 = st.selectbox('Episode B', episodes, index=len(episodes) - 1, key='b')
        ep1, jd1 = load_episode(log_dir, eid1), load_judge(log_dir, eid1)
        ep2, jd2 = load_episode(log_dir, eid2), load_judge(log_dir, eid2)
        c1, c2 = st.columns(2)
        with c1:
            render_episode(f'Episode {eid1}', ep1, jd1, log_dir)
        with c2:
            render_episode(f'Episode {eid2}', ep2, jd2, log_dir)
        # Simple diff summary
        st.subheader('Quick Comparison')
        r1 = step_rows(ep1.get('steps') or [])
        r2 = step_rows(ep2.get('steps') or [])
        st.write(f"Steps: {len(r1)} vs {len(r2)} | Score: {jd1.get('score','-')} vs {jd2.get('score','-')}")

    # Export HTML via the same exporter utility
    from tools.export_html import export_episode_html
    st.sidebar.markdown('---')
    if st.sidebar.button('Export latest episode → HTML'):
        out = export_episode_html(log_dir, None)
        if out:
            st.sidebar.success(f'Exported {out}')
        else:
            st.sidebar.error('Nothing exported.')


if __name__ == '__main__':
    main()
