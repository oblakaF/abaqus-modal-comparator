"""WINDOWS PORTABLE RC4 (as in RC1-RC3-F2): the entry script of the portable new interface (PyInstaller, onedir).

It only starts ``new_gui`` as ``python -m new_gui`` does; the program's modules are frozen with it.
"""

from new_gui.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
