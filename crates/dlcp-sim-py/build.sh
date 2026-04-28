#!/usr/bin/env bash
# Post-build helper: symlink the cdylib produced by
# `cargo build --release` into a `dlcp_sim_native.so` inside
# this crate directory so `python -c "import dlcp_sim_native"`
# works after `cd crates/dlcp-sim-py`.
#
# Why this exists:
#   * The Cargo workspace puts artifacts under
#     `<workspace_root>/target/release/`, NOT the crate dir.
#   * The cdylib is named `libdlcp_sim_native.dylib` on
#     macOS / `libdlcp_sim_native.so` on Linux, but Python's
#     C-extension import looks for `dlcp_sim_native.so`
#     (no `lib` prefix, `.so` extension on both platforms
#     because PyO3's extension module convention follows
#     CPython's import machinery, not the OS dynamic-loader
#     naming).
#   * Maturin handles all of this automatically, but per
#     P4.1's verify command we use plain `cargo build`
#     and a small shell script to keep the toolchain
#     surface area minimal until P4.2 lands the Python
#     facade.
#
# Idempotent: re-running creates a fresh symlink.
# Cross-platform: handles both macOS (.dylib) and Linux
# (.so) cdylib outputs.

set -euo pipefail

# Resolve the workspace target directory relative to this
# script.  Using $0 makes the script callable from any cwd
# (the verify command happens to run from the crate dir,
# but Make targets / CI may not).
script_dir="$(cd "$(dirname "$0")" && pwd)"
workspace_target="$script_dir/../../target/release"

# Find the cdylib.  Cargo's output naming is platform-
# specific; we accept both extensions.
candidates=(
    "$workspace_target/libdlcp_sim_native.dylib"
    "$workspace_target/libdlcp_sim_native.so"
)
src=""
for candidate in "${candidates[@]}"; do
    if [ -f "$candidate" ]; then
        src="$candidate"
        break
    fi
done
if [ -z "$src" ]; then
    echo "build.sh: ERROR: no cdylib found under $workspace_target" >&2
    echo "  expected one of: ${candidates[*]}" >&2
    echo "  did you run 'cargo build --release' first?" >&2
    exit 1
fi

# Symlink (or replace existing symlink) so the import works
# from this crate dir.  Using `ln -sf` rather than copying
# avoids stale artifacts after `cargo clean` -- the broken
# symlink will fail import loudly rather than silently
# loading an old build.
target="$script_dir/dlcp_sim_native.so"
ln -sf "$src" "$target"
echo "build.sh: $target -> $src"
