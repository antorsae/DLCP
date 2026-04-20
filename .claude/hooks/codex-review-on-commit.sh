#!/usr/bin/env bash
# .claude/hooks/codex-review-on-commit.sh
#
# PostToolUse hook for the Bash tool.  When Claude Code runs a Bash
# command that contains `git commit`, AND the working tree HEAD has
# advanced (commit actually landed, not just staged), emit a stdout
# message that Claude Code surfaces back to the model as a system
# reminder.  The reminder instructs the model to invoke the codex-cli
# MCP tool on the new HEAD before continuing with any other work.
#
# Hook input contract: Claude Code pipes a JSON envelope on stdin
# describing the tool call.  The envelope's tool_input.command field
# holds the Bash command string for Bash invocations.
#
# Exit codes:
#   0  -- no action needed (or message emitted; non-blocking)
#   non-zero would be treated as a hook failure and may abort the
#          tool call, which we explicitly DO NOT want here -- the
#          commit already landed; we just want to nudge the model.

set -uo pipefail

# Read the JSON envelope; bail quietly if jq isn't available or input
# isn't JSON-shaped.  We never want a hook failure to block tool use.
input="$(cat 2>/dev/null || true)"
if [ -z "$input" ]; then
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  # No jq -- fall back to grep against the raw input.  The Bash command
  # string sits inside a JSON value so this is approximate but works.
  if echo "$input" | grep -qE '"command"[^"]*:[^"]*"[^"]*git[[:space:]]+commit'; then
    cmd_matched=1
  else
    cmd_matched=0
  fi
else
  cmd="$(echo "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)"
  if echo "$cmd" | grep -qE '\bgit[[:space:]]+commit\b'; then
    cmd_matched=1
  else
    cmd_matched=0
  fi
fi

if [ "$cmd_matched" -ne 1 ]; then
  exit 0
fi

# Confirm a commit actually landed -- if the bash invocation included
# `git commit` but the commit itself failed (e.g. pre-commit hook
# rejected it, no staged files, --dry-run), we don't want to ask for
# a codex review of a non-existent change.
#
# Compare HEAD against the value Claude Code's tool envelope was
# operating on.  We don't have that pre-state directly, so use a
# heuristic: HEAD must exist AND be reachable AND the most recent
# commit's timestamp must be within the last 5 minutes (covers the
# normal case of the commit having JUST happened in this tool call).
HASH="$(git -C "$(pwd)" log -1 --format=%h 2>/dev/null || true)"
if [ -z "$HASH" ]; then
  exit 0
fi

NOW=$(date +%s)
COMMIT_TS=$(git -C "$(pwd)" log -1 --format=%ct 2>/dev/null || echo 0)
AGE=$((NOW - COMMIT_TS))
# 300s = 5 min; if the most recent commit is older than that, this
# Bash invocation didn't actually create a new commit.
if [ "$AGE" -gt 300 ]; then
  exit 0
fi

SUBJ="$(git -C "$(pwd)" log -1 --format=%s 2>/dev/null | head -c 200)"
REPO_ROOT="$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null || pwd)"

# Emit the reminder.  Claude Code will surface stdout from PostToolUse
# hooks back to the model on the next turn.
cat <<EOF
[CODEX REVIEW REQUIRED] HEAD = $HASH ("$SUBJ")

Per CLAUDE.md §"Per-Commit Codex Review" in this repo, you MUST now
invoke the codex-cli MCP tool to dry-run review the just-landed
commit BEFORE starting any new task.  Use this exact tool call:

  mcp__codex-cli__codex(
      cwd="$REPO_ROOT",
      sandbox="read-only",
      approval-policy="never",
      prompt=<<<see CLAUDE.md template; include the HEAD hash, the
              subject line, and a one-line context describing what
              area this commit touches>>>
  )

After codex reports findings:
  * HIGH or MEDIUM -> fix in a follow-up commit before moving on,
                      OR explicitly defer with the user's confirmation.
  * LOW             -> may be deferred but must be tracked (TaskCreate
                      or noted in the next commit message).
  * No findings     -> acknowledge "codex: clean" in your response and
                      proceed.

Do not silently skip this step.  If the user explicitly asks you to
defer the codex review for a particular commit, say so and continue.
EOF
exit 0
