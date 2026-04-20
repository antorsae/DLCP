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

# Use jq if available; without it the hook becomes a no-op rather
# than risk a false-positive parse via grep.  jq is a hard dependency
# for reliable behavior.
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

cmd="$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
hook_cwd="$(echo "$input" | jq -r '.cwd // empty' 2>/dev/null || true)"

# Quick exit if Bash command didn't include `git commit`.  Word-boundary
# match on grep -E so "git committed" or "git commit-tree" don't trigger.
if ! echo "$cmd" | grep -qE '\bgit[[:space:]]+commit\b'; then
  exit 0
fi

# Resolve the repo to inspect.  Prefer the hook envelope's cwd (the
# directory the Bash tool ran in), fall back to CLAUDE_PROJECT_DIR,
# fall back to PWD.  All three may point at the same directory.
target_cwd="${hook_cwd:-${CLAUDE_PROJECT_DIR:-$PWD}}"
[ -d "$target_cwd" ] || exit 0

# Confirm the directory is a git working tree with a reachable HEAD.
HASH="$(git -C "$target_cwd" log -1 --format=%H 2>/dev/null || true)"
[ -z "$HASH" ] && exit 0

short_hash="$(git -C "$target_cwd" log -1 --format=%h 2>/dev/null || echo "$HASH")"
subj="$(git -C "$target_cwd" log -1 --format=%s 2>/dev/null | head -c 200)"

# State file: per-repo, per-HEAD dedup.  Lives under .claude/ in the
# target repo (NOT the hook's source repo) so each checkout tracks
# its own review history.
state_dir="$target_cwd/.claude"
state_file="$state_dir/.codex-last-reviewed-head"

last_reviewed=""
if [ -f "$state_file" ]; then
  last_reviewed="$(head -c 64 "$state_file" 2>/dev/null | tr -d '[:space:]' || true)"
fi

# If HEAD hasn't moved since the last review, the bash invocation
# was either a failed commit, an unrelated git command that mentioned
# `git commit` in passing, or a no-op like `git commit --dry-run`.
if [ "$HASH" = "$last_reviewed" ]; then
  exit 0
fi

# Update the state file (best-effort; never fail the hook).
mkdir -p "$state_dir" 2>/dev/null || true
echo "$HASH" > "$state_file" 2>/dev/null || true

# Compose the reminder body.  Emit as JSON via jq so newlines, quotes,
# and special chars in the subject line are escaped correctly.
remind=$(cat <<EOF
[CODEX REVIEW REQUIRED] HEAD = $short_hash ("$subj")

Per CLAUDE.md (-> AGENTS.md) section "Per-Commit Codex Review", you
MUST now invoke the codex-cli MCP tool to dry-run review the just-
landed commit BEFORE starting any new task.  Tool call template:

  mcp__codex-cli__codex(
      cwd="$target_cwd",
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
