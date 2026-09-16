"""Stdout hash acknowledgment: correlated inject + prove over one process run.

Dual-role adapter (Injector and Prover in one object) for deliveries where
the receiving process cooperates minimally: it reads stdin and prints the
SHA-256 hex of the exact bytes received on stdout.

  inject role (__call__): spawn argv (no shell), write the body to stdin,
    capture THAT run's stdout, store it keyed by item id. Timeout kills and
    raises; spawn failures propagate as OSError. Exit code is ignored.
  prove role (prove): instant local lookup — True only if the expected digest
    of the sent bytes appears in the stdout captured for THAT item id. No
    I/O, no waiting, no external history consulted.

Isolation: captures live in a bounded FIFO (default 256 entries); unique ids
mean one attempt can never read another's stdout. Proof is evidence about a
completed run, never a promise about the injector's return value.
"""
import hashlib
import subprocess
from collections import OrderedDict


class StdoutHashAck:
    """argv: non-empty sequence of program arguments (no shell)."""

    def __init__(self, argv, *, timeout_s=10, encoding="utf-8",
                 max_captures=256):
        if isinstance(argv, (str, bytes)) or not argv:
            raise ValueError("argv must be a non-empty sequence of arguments")
        items = list(argv)
        if any(not isinstance(a, str) for a in items):
            raise ValueError("argv items must be strings")
        self._argv = items
        self._timeout_s = timeout_s
        self._encoding = encoding
        self._max_captures = max_captures
        self._captures = OrderedDict()  # id -> (expected_digest, stdout)

    @staticmethod
    def _digest(data):
        return hashlib.sha256(data).hexdigest()

    def _store(self, item_id, digest, stdout):
        self._captures[item_id] = (digest, stdout)
        while len(self._captures) > self._max_captures:
            self._captures.popitem(last=False)

    def __call__(self, item):
        data = item["body"].encode(self._encoding)
        proc = subprocess.Popen(
            list(self._argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        try:
            out, _ = proc.communicate(data, timeout=self._timeout_s)
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        self._store(item["id"], self._digest(data),
                    out.decode(self._encoding, errors="replace"))
        return None  # success = no exception; exit code intentionally ignored

    def prove(self, item):
        record = self._captures.get(item.get("id") if isinstance(item, dict)
                                    else None)
        if record is None:
            return False
        digest, stdout = record
        return digest in stdout
