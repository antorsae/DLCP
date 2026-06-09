You are an LLM synthesizing the results of a multi-agent semantic-oracle bug hunt
over exploratory DLCP firmware chain simulations. You are model-agnostic.

Below is JSON with two buckets:
- "confirmed": both an artifact-skeptic and a firmware-correctness-skeptic FAILED to
  refute the finding (both returned is_real=true).
- "needs_human": exactly one skeptic refuted it (the two lenses disagree).

Produce a tight markdown report:
1. Executive summary: how many candidates, grouped by bug_class and severity.
   Distinguish clearly between "0 confirmed because everything was refuted as
   expected/artifact" (firmware looks robust on these cards) and "empty input"
   (pipeline produced nothing) — they are NOT the same; say which one this is.
2. A ranked table of the CONFIRMED candidates (most likely real first): class,
   severity, symptom, the session card path, and the one-line repro idea.
3. For the top up-to-8 confirmed candidates, a short paragraph each: the stimulus,
   observed vs expected, why both skeptics believed it, and the concrete next step
   (the deterministic reproducer to build under the project's test directory).
4. A short "needs human review" section listing the disputed ones with the
   disagreement.
5. Dedup aggressively: if many sessions show the same class+symptom signature,
   collapse them into one entry and note the count + example sessions.

Keep it under 1200 words. Be concrete and cite the card paths. Do not soften: if
something looks like a real intermittent bug, say so; if the confirmed list is
empty, say that plainly and note what was checked.

OUTPUT CONTRACT (model-agnostic): output the markdown report only (no JSON wrapper).

Confirmed bucket:
{{CONFIRMED_JSON}}

Needs-human bucket:
{{NEEDS_HUMAN_JSON}}
