# Past Implementations

This document records the benchmark/runtime systems that were removed from the active codebase so the repository keeps historical context without carrying stale execution paths.

## Removed Systems

### Legacy single-page benchmark runtime

The repository previously shipped a frozen single-page benchmark line built around static HTML files under `webagentbench/pages/`, page-specific manifest entries, `/pages/*` serving routes, and `/benchmark/{page_id}/evaluate` endpoints.

That system also had supporting tooling:

- page-mode execution paths in `webagentbench/agent_eval.py`
- a standalone page runner in `webagentbench/runner.py`
- page-template generation scripts in `scripts/generate_wab_templates.py` and `scripts/generate_templates_from_eval.py`
- page-derived LLMOS template artifacts in `llmos/templates/wab_*.json`

Those components were removed because the active benchmark is now environment-based rather than page-based.

### Legacy hard-coded Gmail task registry

Before the unified YAML registry, Gmail tasks were also represented in a hard-coded Python registry in `webagentbench/backend/tasks.py`. A template generator script, `scripts/generate_gmail_templates.py`, depended on that legacy registry and on an older `Seeder` API.

That path was removed because it duplicated the canonical YAML task definitions and had already drifted out of sync with the active seeding/runtime stack.

## Current System

The active implementation is:

- YAML task definitions under `webagentbench/tasks/`
- registry loading and validation in `webagentbench/tasks/_registry.py`
- environment seed runners in `webagentbench/backend/seeders/`
- environment APIs such as Gmail in `webagentbench/backend/routes/`
- advanced-environment serving and manifest generation in `webagentbench/app.py`
- environment-task evaluation in `webagentbench/agent_eval.py`

## Historical Notes

- Historical result files and README tables may still refer to earlier page-based benchmark versions. Those are retained as research history, not as executable runtime paths.
- Older result artifacts may still use page-era field names such as `page_id` or `page_meta`. The active runtime now writes task-oriented metadata instead.
