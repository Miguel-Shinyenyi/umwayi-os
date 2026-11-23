"""W78 step 6 (5b), the first fact: which Landlock ABI does this kernel report?

Reads the version with `landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION)` and writes one line to standard error, so
the CI log shows it: `landlock probe: ABI 4, kernel 6.8.0 ...`, or `landlock probe: not available (reason)`. It creates no ruleset and
restricts no process. On a machine without Landlock (macOS, a kernel with Landlock off, a container that blocks the call) the test is
skipped with a fixed reason and the skip is not a pass of anything: no Landlock code is built on it yet.

This is a measurement, not a rule. It asserts only that a reported ABI is a small positive number.
"""
import ctypes
import os
import platform
import sys
import unittest

NR = 444  # landlock_create_ruleset, the same number on x86_64 and aarch64
VERSION_FLAG = 1 << 0


def read_abi():
    """(abi or None, reason). Reason is one fixed word when there is no ABI."""
    if not sys.platform.startswith("linux"):
        return None, "not linux"
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except OSError:
        return None, "no libc"
    r = libc.syscall(NR, None, 0, VERSION_FLAG)
    if r >= 0:
        return int(r), ""
    err = ctypes.get_errno()
    return None, {38: "not implemented (ENOSYS)", 95: "disabled at boot (EOPNOTSUPP)"}.get(err, f"errno {err}")


ABI, WHY = read_abi()


def setUpModule():
    sys.stderr.write(f"landlock probe: " + (f"ABI {ABI}" if ABI is not None else f"not available ({WHY})")
                     + f", kernel {platform.release()}, machine {platform.machine()}, python {platform.python_version()}\n")
    sys.stderr.flush()


class LandlockProbeTests(unittest.TestCase):
    def test_a_reported_abi_is_a_small_positive_number(self):
        if ABI is None:
            self.skipTest(f"landlock is not available here: {WHY}")
        self.assertGreaterEqual(ABI, 1)
        self.assertLess(ABI, 100)


if __name__ == "__main__":
    unittest.main()
