#!/usr/bin/env python3
"""Model-agnostic runner for the exploratory-oracle bug hunt.

Drives judge -> dual adversarial verify -> synthesize over DLCP session cards using
ANY large-language-model command line.  The judge/verify/synth INSTRUCTIONS live in
`docs/exploratory_oracle/prompts/*.md` and the JSON schemas in
`docs/exploratory_oracle/schemas/*.json`; this runner only fills the templates and
shells out.  Nothing here is tied to a specific model or agent harness.

The `--model-cmd` is a shell command that receives the filled prompt on STDIN and
writes the model's response to STDOUT.  Examples:

    # OpenAI codex CLI (agentic; can read the repo's files referenced in the prompt)
    --model-cmd 'codex exec --skip-git-repo-check -'

    # Anthropic Claude CLI (agentic; can read files)
    --model-cmd 'claude -p --permission-mode acceptEdits'

    # any chat CLI that reads a prompt on stdin and prints the reply
    --model-cmd 'llm -m gpt-4o'

The prompts instruct the model to emit ONLY a JSON object; the runner extracts the
JSON from whatever the command prints (tolerant of agent preamble / code fences).

Cards come from `scripts/sim_exploratory_select_cards.py` (its workflow_args.json or
a render-all index.json), or any directory of rendered `*.md` cards.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PROMPTS = REPO / "docs" / "exploratory_oracle" / "prompts"
SCHEMAS = REPO / "docs" / "exploratory_oracle" / "schemas"


# --- model invocation -------------------------------------------------------

def call_model(model_cmd: str, prompt: str, timeout: int) -> str:
    proc = subprocess.run(
        model_cmd, shell=True, input=prompt,
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"model-cmd exited {proc.returncode}: {proc.stderr[:500]}")
    return proc.stdout


def _truthy(value: Any) -> bool:
    """Strict truthiness for schema-loose model output: the string "false" is False.

    A model that emits ``"is_real": "false"`` must NOT be read as real (plain
    ``bool("false")`` is True), or a refutation gets promoted to a confirmation.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return False


def extract_json(text: str) -> dict[str, Any]:
    """Best-effort: pull the last balanced top-level JSON object out of model output.

    The brace scan is string-aware (braces and the ``}`` char inside JSON string
    literals are ignored) so evidence text containing braces does not break it.
    """
    text = text.strip()
    # strip ```json ... ``` fences if present
    if "```" in text:
        for chunk in text.split("```"):
            c = chunk.strip()
            if c.startswith("json"):
                c = c[4:].strip()
            if c.startswith("{"):
                try:
                    return json.loads(c)
                except json.JSONDecodeError:
                    pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # string-aware scan for the last balanced {...}
    depth = 0
    start = -1
    candidate = None
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start:i + 1]
    if candidate:
        return json.loads(candidate)
    raise ValueError("no JSON object found in model output")


# --- template loading -------------------------------------------------------

def load_templates() -> dict[str, str]:
    return {
        name: (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
        for name in ("judge", "verify_artifact", "verify_correctness", "synthesize")
    }


def fill(tmpl: str, **kw: str) -> str:
    for k, v in kw.items():
        tmpl = tmpl.replace("{{" + k + "}}", v)
    return tmpl


# --- card loading -----------------------------------------------------------

def load_cards(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.cards_index:
        data = json.loads(Path(args.cards_index).read_text(encoding="utf-8"))
        rows = data["cards"] if isinstance(data, dict) and "cards" in data else data
        return list(rows)
    cards = []
    for p in sorted(Path(args.cards_dir).glob("*.md")):
        cards.append({"card": str(p), "run_id": p.stem, "session_id": 0})
    return cards


# --- pipeline ---------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    tmpl = load_templates()
    findings_schema = (SCHEMAS / "findings.schema.json").read_text(encoding="utf-8")
    verdict_schema = (SCHEMAS / "verdict.schema.json").read_text(encoding="utf-8")
    cards = load_cards(args)
    if args.max_cards:
        cards = cards[: args.max_cards]
    common = dict(
        RUBRIC=args.rubric, TAXONOMY=args.taxonomy,
        MAIN_ASM=args.main_asm, CONTROL_ASM=args.control_asm,
        TESTS_DIR=args.tests_dir,
        FINDINGS_SCHEMA=findings_schema, VERDICT_SCHEMA=verdict_schema,
    )

    def judge(card: dict[str, Any]) -> dict[str, Any]:
        prompt = fill(tmpl["judge"], CARD=card["card"], **common)
        try:
            res = extract_json(call_model(args.model_cmd, prompt, args.timeout))
        except Exception as exc:  # a dead judge yields no findings, not a crash
            return {"card": card, "overall": "error", "findings": [], "error": repr(exc)}
        return {"card": card, **res}

    def verify(card: dict[str, Any], finding: dict[str, Any], lens: str) -> dict[str, Any]:
        prompt = fill(
            tmpl[f"verify_{lens}"],
            CARD=card["card"], FINDING_JSON=json.dumps(finding, indent=2), **common,
        )
        try:
            return extract_json(call_model(args.model_cmd, prompt, args.timeout))
        except Exception as exc:
            return {"is_real": False, "confidence": 0.0, "reasoning": "",
                    "refutation": f"verify error: {exc!r}", "source_evidence": "",
                    "repro_sketch": "", "_error": repr(exc)}

    print(f"[oracle] judging {len(cards)} cards with: {args.model_cmd}", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        judged = list(pool.map(judge, cards))

    # collect findings, verify each with both lenses
    pending: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for j in judged:
        for f in (j.get("findings") or [])[: args.max_findings_per_card]:
            pending.append((j["card"], f))
    print(f"[oracle] verifying {len(pending)} findings (x2 lenses)", file=sys.stderr)

    def verify_both(item: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
        card, finding = item
        return {
            "card": card, "finding": finding,
            "artifact": verify(card, finding, "artifact"),
            "correctness": verify(card, finding, "correctness"),
        }

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        verified = list(pool.map(verify_both, pending))

    # M1 observability: a broken run must NOT look like a clean firmware pass.
    judge_errors = [
        {"card": j["card"].get("card"), "error": j.get("error")}
        for j in judged if j.get("overall") == "error" or "error" in j
    ]
    verify_errors = sum(
        1 for v in verified
        for lens in ("artifact", "correctness") if "_error" in v[lens]
    )

    confirmed, needs_human, refuted = [], [], []
    for v in verified:
        a, c = _truthy(v["artifact"].get("is_real")), _truthy(v["correctness"].get("is_real"))
        bucket = "confirmed" if (a and c) else ("needs_human" if (a or c) else "refuted")
        rec = {
            "bug_class": v["finding"].get("bug_class"),
            "severity": v["finding"].get("severity"),
            "symptom": v["finding"].get("symptom"),
            "stimulus": v["finding"].get("stimulus"),
            "evidence": v["finding"].get("evidence"),
            "card": v["card"].get("card"),
            "session_id": v["card"].get("session_id"),
            "artifact_verdict": v["artifact"],
            "correctness_verdict": v["correctness"],
        }
        {"confirmed": confirmed, "needs_human": needs_human, "refuted": refuted}[bucket].append(rec)

    print(f"[oracle] confirmed={len(confirmed)} needs_human={len(needs_human)} "
          f"refuted={len(refuted)} | judge_errors={len(judge_errors)} "
          f"verify_errors={verify_errors}", file=sys.stderr)
    if judge_errors or verify_errors:
        print("[oracle] WARNING: model/parse errors occurred — a low confirmed count "
              "may reflect a broken run, not clean firmware.", file=sys.stderr)

    synth_prompt = fill(
        tmpl["synthesize"],
        CONFIRMED_JSON=json.dumps(confirmed, indent=2),
        NEEDS_HUMAN_JSON=json.dumps(needs_human, indent=2),
    )
    try:
        report = call_model(args.model_cmd, synth_prompt, args.timeout)
    except Exception as exc:
        report = f"(synthesis failed: {exc!r})"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "model_cmd": args.model_cmd,
        "cards_judged": len(cards),
        "confirmed": confirmed,
        "needs_human": needs_human,
        "refuted_count": len(refuted),
        "judge_errors": judge_errors,
        "verify_error_count": verify_errors,
        "run_ok": not judge_errors and not verify_errors,
    }, indent=2) + "\n", encoding="utf-8")
    Path(str(out) + ".report.md").write_text(report, encoding="utf-8")
    print(f"[oracle] wrote {out} and {out}.report.md", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--cards-index", help="workflow_args.json or index.json listing cards")
    src.add_argument("--cards-dir", help="directory of rendered *.md cards")
    ap.add_argument("--model-cmd", required=True,
                    help="shell command: reads prompt on stdin, prints model reply on stdout")
    ap.add_argument("--rubric", default=str(REPO / "docs" / "SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md"))
    ap.add_argument("--taxonomy", default=str(REPO / "docs" / "SIM_EXPLORATORY_BUG_TAXONOMY.md"))
    ap.add_argument("--main-asm", default=str(REPO / "src" / "dlcp_fw" / "asm" / "dlcp_main_v34.asm"))
    ap.add_argument("--control-asm", default=str(REPO / "src" / "dlcp_fw" / "asm" / "dlcp_control_v173.asm"))
    ap.add_argument("--tests-dir", default=str(REPO / "tests" / "sim"))
    ap.add_argument("--out", default=str(REPO / "artifacts" / "sim" / "current" / "exploratory" / "oracle_run.json"))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--max-cards", type=int, default=0)
    ap.add_argument("--max-findings-per-card", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
