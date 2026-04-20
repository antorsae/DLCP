#!/usr/bin/env bash
# .claude/hooks/codex-review-on-commit.sh
#
# PostToolUse hook for the Bash tool.  When Claude Code runs a Bash
# command containing `git commit` AND that invocation actually
# advanced HEAD (i.e. a fresh commit landed, distinct from the last
# commit this hook reviewed), emit a JSON envelope on stdout that
# Claude Code surfaces back to the model as additionalContext via
# hookSpecificOutput.  The reminder instructs Claude to invoke the
# codex-cli MCP tool on the new HEAD before continuing.
#
# Hook protocol (Claude Code PostToolUse):
#   * stdin: JSON envelope with .cwd, .tool_name, .tool_input.command,
#            .tool_response.output, etc.
#   * stdout: plain text is debug-only for PostToolUse -- to inject
#             context, emit JSON of the form
#                 {"hookSpecificOutput": {
#                    "hookEventName": "PostToolUse",
#                    "additionalContext": "..."
#                 }}
#   * exit code: non-zero would be treated as a hook failure; we
#                always exit 0 so a hook bug never blocks a commit.
#
# State tracking:
#   .claude/.codex-last-reviewed-head -- last HEAD hash this hook
#                                        emitted a reminder for.  A
#                                        reminder only fires when the
#                                        repo's current HEAD differs.
#                                        Handles amends (HEAD changes)
#                                        and prevents re-firing on
#                                        no-op git invocations.
#
# Codex review of HEAD = 46b19d0 (the hook's first commit) flagged
# the original time-based heuristic as both false-positive prone and
# repo-mis-targeting prone; this rewrite addresses both via the
# state-file approach + reading .cwd from the envelope.

set -uo pipefail

input="$(cat 2>/dev/null || true)"
[ -z "$input" ] && exit 0

# jq is a hard dependency.  Without it, emit a visible warning JSON
# envelope so the operator notices the hook is degraded -- silent
# no-op was the LOW finding in codex review of 46dae4f.  printf-built
# JSON (no jq needed) is acceptable here because the message text
# contains no special chars that need escaping.
if ! command -v jq >/dev/null 2>&1; then
  printf '{"systemMessage":"WARNING: codex review hook requires jq on PATH; install jq to enable per-commit codex review automation."}\n'
  exit 0
fi

cmd="$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
hook_cwd="$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null || true)"

# Match any bash command that contains `git` AND `commit` as separate
# words (in either order, with anything in between).  This covers all
# of: `git commit`, `git -C /path commit`, `git -c key=val commit`,
# `cd dir && git commit`, plus shell pipelines.  False positives like
# `git status; mkdir commit` are caught downstream by the state-file
# dedup -- the hook only fires when HEAD actually advanced past the
# last reviewed hash, so a non-commit invocation is silent.
if ! echo "$cmd" | grep -qE '\bgit\b'; then
  exit 0
fi
if ! echo "$cmd" | grep -qE '\bcommit\b'; then
  exit 0
fi

# Resolve the repo to inspect.  Prefer the hook envelope's cwd (the
# directory the Bash tool ran in), fall back to CLAUDE_PROJECT_DIR,
# fall back to PWD.  Then resolve to the repo TOP-LEVEL so the state
# file always lands in the repo root regardless of which subdirectory
# bash was invoked from -- per-subdir state would fragment dedup
# (codex MEDIUM finding against 46dae4f).
target_cwd="${hook_cwd:-${CLAUDE_PROJECT_DIR:-$PWD}}"
[ -d "$target_cwd" ] || exit 0

repo_root="$(git -C "$target_cwd" rev-parse --show-toplevel 2>/dev/null || true)"
[ -z "$repo_root" ] && exit 0

# Confirm a reachable HEAD.
HASH="$(git -C "$repo_root" log -1 --format=%H 2>/dev/null || true)"
[ -z "$HASH" ] && exit 0

short_hash="$(git -C "$repo_root" log -1 --format=%h 2>/dev/null || echo "$HASH")"
subj="$(git -C "$repo_root" log -1 --format=%s 2>/dev/null | head -c 200)"

# State file: per-repo (at repo root), per-HEAD dedup.  Always under
# .claude/ at the repo top-level so subdir invocations don't fragment.
state_dir="$repo_root/.claude"
state_file="$state_dir/.codex-last-reviewed-head"

last_reviewed=""
if [ -f "$state_file" ]; then
  last_reviewed="$(head -c 64 "$state_file" 2>/dev/null | tr -d '[:space:]' || true)"
fi

# If HEAD hasn't moved since the last review, the bash invocation
# was either a failed commit, an unrelated git command that mentioned
# `commit` in passing, or a no-op like `git commit --dry-run`.
if [ "$HASH" = "$last_reviewed" ]; then
  exit 0
fi

# Build a list of unreviewed commits between last_reviewed (exclusive)
# and HEAD (inclusive).  If last_reviewed isn't reachable from HEAD
# (e.g. force-push / branch-switch / first-ever review), fall back to
# just HEAD.  This handles the codex MEDIUM finding that "if a Bash
# tool call lands MULTIPLE commits before the hook fires once, only
# the last hash gets reviewed" -- we now list ALL of them.
#
# `--reverse` so the listed order matches the wording ("oldest-first")
# in the reminder body.  The TOTAL count is computed against the full
# range so a head-truncated display in the reminder doesn't hide the
# tail count from the operator (codex MEDIUM 2026-04-20: pre-truncation
# made the count match the truncated list, recreating the original
# "intermediate commits silently bypass review" bug at a higher
# threshold).
new_commit_count=0
new_commits_full=""
range_used=""
if [ -n "$last_reviewed" ] && \
   git -C "$repo_root" merge-base --is-ancestor "$last_reviewed" "$HASH" 2>/dev/null; then
  range_used="${last_reviewed}..${HASH}"
  new_commit_count="$(git -C "$repo_root" rev-list --count "$range_used" 2>/dev/null || echo 0)"
  new_commits_full="$(git -C "$repo_root" log --reverse --format='%h %s' "$range_used" 2>/dev/null)"
fi
if [ "$new_commit_count" -le 0 ] || [ -z "$new_commits_full" ]; then
  # Fallback: just HEAD.  Counts as 1 commit.
  range_used=""
  new_commit_count=1
  new_commits_full="$(git -C "$repo_root" log -1 --format='%h %s' "$HASH" 2>/dev/null)"
fi

# Display list: bound to 50 entries to keep the reminder JSON
# manageable even on huge batches.  The full count is reported above
# so the operator/model knows when truncation happened.
DISPLAY_LIMIT=50
if [ "$new_commit_count" -gt "$DISPLAY_LIMIT" ]; then
  shown="$(printf '%s\n' "$new_commits_full" | head -$DISPLAY_LIMIT)"
  trunc_note="... (showing first $DISPLAY_LIMIT of $new_commit_count; reach the rest via \`git -C $repo_root log --reverse --format='%h %s' $range_used\`)"
  new_commits="$shown
$trunc_note"
else
  new_commits="$new_commits_full"
fi

# Update the state file (best-effort; never fail the hook).
mkdir -p "$state_dir" 2>/dev/null || true
echo "$HASH" > "$state_file" 2>/dev/null || true

# Compose the reminder body.  Emit as JSON via jq so newlines, quotes,
# and special chars in the subject line are escaped correctly.
#
# When multiple commits landed since the last review (the bash
# invocation included multiple `git commit` calls), list ALL of them
# so codex can review each in turn instead of silently skipping
# intermediates (codex MEDIUM finding against 46dae4f).
if [ "$new_commit_count" -gt 1 ]; then
  multi_note="
This Bash invocation landed $new_commit_count new commits since the
last codex review.  Review each commit individually -- the list
below is in oldest-first chronological order (\`git log --reverse\`):

$new_commits
"
else
  multi_note=""
fi
remind=$(cat <<EOF
[CODEX REVIEW REQUIRED] HEAD = $short_hash ("$subj")
$multi_note
Per CLAUDE.md (-> AGENTS.md) section "Per-Commit Codex Review", you
MUST now invoke the codex-cli MCP tool to dry-run review the just-
landed commit(s) BEFORE starting any new task.  Tool call template:

  mcp__codex-cli__codex(
      cwd="$repo_root",
      sandbox="read-only",
      approval-policy="never",
      prompt=<<<see AGENTS.md template; include HEAD hash $short_hash,
              the subject line, and a one-line context describing
              what area this commit touches>>>
  )

After codex reports findings:
  * HIGH or MEDIUM -> fix in a follow-up commit before moving on,
                      OR explicitly defer with user confirmation.
  * LOW             -> may be deferred but must be tracked
                      (TaskCreate or noted in the next commit message).
  * No findings     -> acknowledge "codex: clean" and proceed.

Do not silently skip this step.
EOF
)

# Emit the JSON envelope Claude Code recognizes for PostToolUse
# additionalContext injection.
jq -n --arg msg "$remind" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: $msg
  }
}'

exit 0
