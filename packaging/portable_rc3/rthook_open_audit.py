"""WINDOWS PORTABLE RC3 runtime hook (as in RC1 and RC2): an optional record of the files the portable program opens
(acceptance only).

Inactive unless the environment variable AMC_OPEN_AUDIT names a log file. Then every file the program opens is
appended to that log (one path per line), so an acceptance run can show that the portable copy reads neither an
installed Python nor the project's source tree. It changes nothing the program does.
"""

import os
import sys

_LOG = os.environ.get("AMC_OPEN_AUDIT")
if _LOG:
    _seen = set()

    def _audit(event, args):
        if event != "open" or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = os.fsdecode(args[0])
        if path in _seen or path == _LOG:
            return
        _seen.add(path)
        try:
            with open(_LOG, "a", encoding="utf-8") as stream:
                stream.write(path + "\n")
        except OSError:
            pass

    sys.addaudithook(_audit)
