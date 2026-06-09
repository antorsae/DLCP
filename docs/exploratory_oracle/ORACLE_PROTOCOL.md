# Exploratory-oracle protocol (model-agnostic)

Last updated: 2026-06-09

This directory holds the **model-agnostic** instructions for the LLM "semantic
oracle" that judges DLCP exploratory-simulation session cards. The instructions do
not depend on which model or agent runs them — Claude, codex, or any LLM CLI can
execute the exact same judge/verify/synth prompts against the exact same inputs.

## Design: instructions vs. orchestration

The hunt has two layers, deliberately separated:

1. **Instructions (agnostic, committed here):**
   - `prompts/judge.md` — black-box per-card judge → findings JSON
   - `prompts/verify_artifact.md` — adversarial "is this a harness artifact?" → verdict JSON
   - `prompts/verify_correctness.md` — adversarial "is this intended firmware behavior?" → verdict JSON
   - `prompts/synthesize.md` — dedup + rank confirmed/needs-human → markdown report
   - `schemas/findings.schema.json`, `schemas/verdict.schema.json` — the output contracts
   - Each prompt ends with an explicit "output ONLY a JSON object" contract, so any
     model's reply can be parsed. Placeholders (`{{CARD}}`, `{{RUBRIC}}`,
     `{{TAXONOMY}}`, `{{MAIN_ASM}}`, `{{CONTROL_ASM}}`, `{{TESTS_DIR}}`,
     `{{FINDING_JSON}}`, `{{FINDINGS_SCHEMA}}`, `{{VERDICT_SCHEMA}}`,
     `{{CONFIRMED_JSON}}`, `{{NEEDS_HUMAN_JSON}}`) are filled by the runner.

2. **Orchestration (pluggable):**
   - `scripts/exploratory_oracle_run.py` — generic runner: loops cards, fills the
     prompt templates, and shells out to **any** model via `--model-cmd`. This is
     the portable path (codex / Claude / any CLI).
   - `artifacts/.../oracle_workflow.js` — a Claude-Code `Workflow` backend. It is an
     *optional* convenience that implements the same judge→verify→synth shape using
     Claude Code's parallel agent runtime. It is NOT required; the canonical
     instructions are the prompt files here.

The supporting inputs are all plain artifacts with no model assumptions:
- Session cards: `scripts/sim_exploratory_oracle_format.py` (pure Python; renders
  raw sim JSONL into markdown cards).
- Card selection / triage: `scripts/sim_exploratory_select_cards.py`.
- Rubric: `docs/SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md` §"Oracles and Bug Classifiers".
- Taxonomy: `docs/SIM_EXPLORATORY_BUG_TAXONOMY.md`.

## End-to-end (any model)

```bash
# 1. generate corpus (pure sim, no LLM)
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m --campaign all --out-dir artifacts/sim/current/exploratory/hunt

# 2. triage + render the most interesting cards (pure Python, no LLM)
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_exploratory_select_cards.py \
  artifacts/sim/current/exploratory/hunt --out /tmp/cards --realistic --top 14 --sample 10

# 3a. run the oracle with codex
PYTHONPATH=src .venv_ep0/bin/python scripts/exploratory_oracle_run.py \
  --cards-index /tmp/cards/workflow_args.json \
  --model-cmd 'codex exec --skip-git-repo-check -' \
  --out artifacts/sim/current/exploratory/oracle_codex.json

# 3b. or run the same hunt with Claude
PYTHONPATH=src .venv_ep0/bin/python scripts/exploratory_oracle_run.py \
  --cards-index /tmp/cards/workflow_args.json \
  --model-cmd 'claude -p --permission-mode acceptEdits' \
  --out artifacts/sim/current/exploratory/oracle_claude.json
```

## `--model-cmd` contract

The command reads the filled prompt on **stdin** and prints the model's reply to
**stdout**. The runner extracts the JSON object from that reply (tolerant of agent
preamble and ```json fences), so the model only has to honor the prompt's "output
ONLY JSON" contract. The verify-correctness step asks the model to read firmware
source and tests, so the model command should be one that can read repo files
(both `codex exec` and `claude -p` run as agents in the repo and can).

## Adding another model

Nothing to change here — just pass a different `--model-cmd`. If a model wraps its
output (e.g. `claude -p --output-format json`), either point `--model-cmd` at a
small wrapper that unwraps it to the raw reply, or rely on the runner's brace
extractor. Keep the prompt files as the single source of truth; do not fork them
per model.
