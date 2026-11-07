class UmwayiError(Exception):
    """A clear, safe error. Messages must never contain file content."""


class UsageError(UmwayiError):
    """The command was called the wrong way. The command line exits 64."""
