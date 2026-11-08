class UmwayiError(Exception):
    """A clear, safe error. Messages must never contain file content. The command line exits 1."""


class UsageError(UmwayiError):
    """The command was called the wrong way, or an argument value is not allowed. The command line exits 64."""


class ConfigError(UsageError):
    """A configuration file (umwayi.json, a jobs file, a workflow file) is missing or invalid. Exits 64."""
