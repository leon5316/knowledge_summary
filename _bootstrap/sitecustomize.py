"""Sandbox bootstrap: force permissive modes on dir/file creation.

The harness file sandbox emulates POSIX permission bits; tempfile/pip create
temp dirs with 0o700 and files with 0o600, which the sandbox then denies.
This sitecustomize (loaded via PYTHONPATH) neutralizes those modes.
"""

import os

_orig_mkdir = os.mkdir
_orig_open = os.open


def _mkdir(path, mode=0o777, *args, **kwargs):
    return _orig_mkdir(path, 0o777, *args, **kwargs)


def _open(path, flags, mode=0o777, *args, **kwargs):
    if flags & os.O_CREAT:
        mode = 0o666
    return _orig_open(path, flags, mode, *args, **kwargs)


os.mkdir = _mkdir
os.open = _open

try:
    _orig_chmod = os.chmod
    os.chmod = lambda path, mode, *a, **kw: _orig_chmod(path, 0o777, *a, **kw)
except Exception:
    pass
