"""OpenCode run injector: deliver a mediator message to a real opencode run.

Wraps the installed `opencode run` CLI (message as positional argument, per
`opencode run --help` on v1.18.31). One process per delivery; stdout is
discarded here by Injector-role design (proof belongs to a Prover).
Composes the shared spawn helper; knows nothing about Delivery, Flow,
windows, browsers, or private mediators.

Precondition (enforced upstream by Delivery.put): non-empty text.
"""
from adapters._spawn import run


class OpencodeRunInjector:
    """argv0: opencode executable (default "opencode", resolved via PATH).

    project_dir -> `--dir`; model -> `--model`; session -> `--session`;
    extra_args -> appended verbatim before the message (advanced use).
    The message travels as ONE argv element (never shell-joined). All
    options are strings (or None); anything else is rejected fail-closed.
    encoding is reserved (message travels via argv, not stdin) and unused.
    """

    def __init__(self, argv0="opencode", *, project_dir=None, model=None,
                 session=None, extra_args=(), timeout_s=600,
                 encoding="utf-8"):
        if not isinstance(argv0, str) or not argv0:
            raise ValueError("argv0 must be a non-empty string")
        for name, value in (("project_dir", project_dir),
                            ("model", model), ("session", session)):
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be a string or None")
        extra = list(extra_args)
        if any(not isinstance(a, str) for a in extra):
            raise ValueError("extra_args items must be strings")
        base = [argv0, "run"]
        if project_dir is not None:
            base += ["--dir", project_dir]
        if model is not None:
            base += ["--model", model]
        if session is not None:
            base += ["--session", session]
        base += extra
        self._base = base
        self._timeout_s = timeout_s
        self._encoding = encoding

    def argv_for(self, text):
        """Full argv for one delivery (public for inspection/testing)."""
        return list(self._base) + [text]

    def __call__(self, item):
        run(self.argv_for(item["body"]), None, self._timeout_s)
        return None  # success = no exception; exit code intentionally ignored
