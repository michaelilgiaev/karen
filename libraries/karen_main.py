"""Frozen entry point for the `karen` binary (Nuitka --onefile).

This is the top-level module Nuitka freezes; compile.sh points at it and adds
libraries/ to the module search path. It lives IN libraries/ next to the flat
modules (no package), so it imports the CLI entry FLAT -- `import
command_line_interface` -- and the modules load as bare siblings. It puts its own
directory on sys.path first so the import resolves both frozen and run straight
from source; inside the frozen binary __file__ resolves into the bundled
extraction dir, so the siblings load from there.

Crucially we do NOT chdir: karen's subcommands act on the git repository in the
caller's CURRENT WORKING DIRECTORY, and the frozen bootstrap leaves cwd untouched,
so a `karen` invoked inside /some/project acts on THAT project -- preserved through
freezing, exactly as qvm preserves its CWD-derived VM identity.

Run from source (unfrozen) the same way compile.sh freezes it:
    PYTHONPATH=libraries python3 libraries/karen_main.py <args>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from command_line_interface import main  # noqa: E402  (after the sys.path bootstrap above)

if __name__ == "__main__":
    sys.exit(main())
