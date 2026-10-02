#!/usr/bin/env bash
#
# karen -- build entry point.
#
# Compiles the flat Python modules in libraries/ into a SINGLE self-contained binary with
# Nuitka (--onefile), written to output/karen. Nuitka compiles Python -> C -> a native
# executable: a tighter, faster binary and no .spec file. The whole build is a plain
# user-space run -- there is NO pacman here, so this needs no sudo. It mirrors qvm's
# compile.sh: it truncates its log per launch, keeps a stopwatch that reports the build
# duration on success AND failure, and exports PYTHONDONTWRITEBYTECODE=1 so no __pycache__
# litters the source tree.
#
# The frozen binary runs the entry FLAT (libraries/karen_main.py does `import
# command_line_interface`), so the modules load as bare siblings exactly as from source.
# --include-module names every sibling so Nuitka carries the whole app even though the
# bare `import <sibling>` lines are resolved only at runtime via karen_main's sys.path
# insert. The launcher does NOT chdir: karen acts on the git repo in the caller's CWD, and
# Nuitka's onefile bootstrap leaves cwd untouched, so `karen` inside /some/project acts on
# THAT project -- preserved through freezing.
#
# Nuitka's scratch goes under cache/ (gitignored, wiped by ./clear.sh) via --output-dir;
# the finished binary is copied OUT to output/karen. ZERO build scratch lands in the repo
# root. ARGS: any args pass straight through to Nuitka (e.g. --show-progress). Requires
# (system): python, python-pip, gcc. Self-bootstrapping like tests.sh: it builds cache/venv
# and installs requirements.txt (nuitka + patchelf) on first run.

set -o errexit
set -o nounset
set -o pipefail

REPODIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPODIR"

ENTRY="$REPODIR/libraries/karen_main.py"
OUTDIR="$REPODIR/output"
CACHEDIR="$REPODIR/cache/nuitka"
LOGDIR="$REPODIR/logs"
LOG="$LOGDIR/compile.log"
BINNAME="karen"
mkdir -p "$LOGDIR" "$OUTDIR" "$CACHEDIR"

# Never scatter __pycache__ around the source tree. Exported before any work so every child
# (Nuitka, the Python it runs) inherits it.
export PYTHONDONTWRITEBYTECODE=1

# The build runs out of a self-contained venv under cache/ (gitignored). compile.sh OWNS
# that venv: created on first run, requirements.txt installed into it.
VENV="$REPODIR/cache/venv"
PY="$VENV/bin/python"
REQ="$REPODIR/requirements.txt"
STAMP="$VENV/.requirements.installed"

# Stopwatch: format a whole-second duration as e.g. "1h 04m 09s" / "7m 32s" / "12s".
_format_duration() {
    local secs=$1 h m s
    h=$(( secs / 3600 )); m=$(( (secs % 3600) / 60 )); s=$(( secs % 60 ))
    if   [ "$h" -gt 0 ]; then printf '%dh %02dm %02ds' "$h" "$m" "$s"
    elif [ "$m" -gt 0 ]; then printf '%dm %02ds' "$m" "$s"
    else                      printf '%ds' "$s"
    fi
}

_COMPILE_START="$(date +%s)"
: > "$LOG"

# Report the elapsed time on EVERY exit (success, failure, or Ctrl-C), then let the real
# exit code propagate.
_report() {
    local rc=$?
    local elapsed=$(( $(date +%s) - _COMPILE_START ))
    local line
    if [ "$rc" -eq 0 ]; then
        line="[time] Compile finished in $(_format_duration "$elapsed")."
    else
        line="[time] Compile FAILED after $(_format_duration "$elapsed") (exit $rc)."
    fi
    echo "$line"
    echo "$line" >> "$LOG" 2>/dev/null || true
}
trap _report EXIT

# --- Self-bootstrap the build venv (mirrors tests.sh) ------------------------
if [ ! -x "$PY" ]; then
    BOOT="$(command -v python3 || true)"
    [ -n "$BOOT" ] || { echo "[compile] no python3 to build the venv -- pacman -S python python-pip" | tee -a "$LOG" >&2; exit 1; }
    echo "[compile] creating venv at $VENV" | tee -a "$LOG"
    "$BOOT" -m venv "$VENV" >>"$LOG" 2>&1
fi

# Install requirements only when they change: stamp the venv with a hash of requirements.txt.
REQ_HASH=""
[ -f "$REQ" ] && REQ_HASH="$(sha256sum "$REQ" | cut -d' ' -f1)"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$REQ_HASH" ]; then
    echo "[compile] installing build requirements (nuitka, patchelf, ...)" | tee -a "$LOG"
    _pip_install() {
        local out rc
        out="$("$PY" -m pip install --quiet "$@" 2>&1)"; rc=$?
        printf '%s\n' "$out" >> "$LOG" 2>/dev/null || true
        [ "$rc" -ne 0 ] && { echo "[compile] pip install failed (exit $rc):" >&2; printf '%s\n' "$out" >&2; }
        return "$rc"
    }
    _pip_install --upgrade pip
    [ -f "$REQ" ] && _pip_install -r "$REQ"
    echo "$REQ_HASH" > "$STAMP"
fi

# Nuitka's onefile mode on Linux shells out to `patchelf`; requirements.txt ships it as a
# pip wheel in the venv's bin/. Put that bin dir FIRST on PATH so Nuitka finds it.
export PATH="$VENV/bin:$PATH"

# Safety net: after the bootstrap nuitka should import.
if ! "$PY" -c "import nuitka" >>"$LOG" 2>&1; then
    echo "[compile] Nuitka still not importable for $PY after bootstrap -- see $LOG" | tee -a "$LOG" >&2
    echo "[compile] Try a clean rebuild: ./clear.sh -c && ./compile.sh" | tee -a "$LOG" >&2
    exit 1
fi

# Every sibling module named as an explicit include: the flat `import <sibling>` lines
# resolve only at runtime (via karen_main's sys.path insert), which Nuitka's static analysis
# does not always follow. Naming them all guarantees the frozen binary carries the whole app.
MODULES=(
    checks command_line_interface commit_command configuration git_io llm
    message version version_command
)
INCLUDE_ARGS=()
for m in "${MODULES[@]}"; do INCLUDE_ARGS+=(--include-module="$m"); done

echo "[compile] building $BINNAME (Nuitka --onefile) -> output/$BINNAME" | tee -a "$LOG"
echo "[compile] interpreter: $PY" | tee -a "$LOG"

# --onefile                 : one self-contained executable.
# --output-filename         : the binary is `karen` (the command every caller invokes).
# --output-dir=CACHEDIR     : all build scratch under cache/.
# --assume-yes-for-downloads: onefile may fetch its bootstrap helper -- answer yes.
# --follow-imports          : pull every reachable module into the binary.
# --python-flag=-O          : build with assertions off / __debug__ False (release).
"$PY" -u -m nuitka \
    --onefile \
    --output-filename="$BINNAME" \
    --output-dir="$CACHEDIR" \
    --follow-imports \
    "${INCLUDE_ARGS[@]}" \
    --assume-yes-for-downloads \
    --python-flag=-O \
    --company-name=karen \
    --product-name=karen \
    "$@" \
    "$ENTRY" 2>&1 | tee -a "$LOG"

# PIPESTATUS[0] is Nuitka's own exit (not tee's). Check it explicitly.
rc="${PIPESTATUS[0]}"
if [ "$rc" -ne 0 ]; then
    echo "[compile] Nuitka failed (exit $rc) -- see $LOG" | tee -a "$LOG" >&2
    exit "$rc"
fi

# Nuitka writes the onefile binary as <output-dir>/<output-filename>. Copy it OUT to output/.
BUILT=""
for cand in "$CACHEDIR/$BINNAME" "$CACHEDIR/$BINNAME.bin"; do
    [ -x "$cand" ] && { BUILT="$cand"; break; }
done
if [ -z "$BUILT" ]; then
    echo "[compile] build reported success but no onefile binary found under $CACHEDIR" | tee -a "$LOG" >&2
    exit 1
fi
install -m 755 "$BUILT" "$OUTDIR/$BINNAME"

if [ ! -x "$OUTDIR/$BINNAME" ]; then
    echo "[compile] build reported success but output/$BINNAME is missing" | tee -a "$LOG" >&2
    exit 1
fi

echo "[compile] done: $OUTDIR/$BINNAME" | tee -a "$LOG"
echo "[compile] install it with: sudo install -m 755 output/$BINNAME /usr/bin/" | tee -a "$LOG"
