"""WINDOWS PORTABLE RC6 (as in RC1-RC5): the entry script of the portable new interface (PyInstaller, onedir).

It starts ``new_gui`` as ``python -m new_gui`` does; the program's modules are frozen with it.

WINDOWS-PREVIEW-01-SOLID-WORKER-FIX: the packaged program is also the supervised solid worker of Research Tuning (in
the source tree that worker is ``python -m services.solid_forward_runner --child``; the packaged program has no
``-m``). The worker question is asked FIRST, before any interface module is imported: a worker invocation, well formed
or not, ends here with an exit code and never opens a window.
"""

import sys


def main() -> int:
    from services.solid_forward_runner import frozen_worker_dispatch

    code = frozen_worker_dispatch(sys.argv[1:])
    if code is not None:
        return code
    from new_gui.__main__ import main as start_interface

    return start_interface()


if __name__ == "__main__":
    raise SystemExit(main())
