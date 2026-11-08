"""Layer 10 part 7a, task 10.24: adapters/claude_acp/ (the pin, the lockfile, .gitignore, canary.py).

canary.py runs as a real child process. Nothing here needs Node, npm or the network.
"""

import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import agents

REPO = Path(__file__).resolve().parents[2]
FOLDER = REPO / "adapters" / "claude_acp"
CANARY = FOLDER / "canary.py"
TOKEN = "0123456789abcdef0123456789abcdef"
EXACT = re.compile(r"^\d+\.\d+\.\d+$")
RANGE_CHARS = set("^~<>=*|xX ")


def read_json(name: str):
    return json.loads((FOLDER / name).read_text(encoding="utf-8"))


class PinTests(unittest.TestCase):
    def test_package_json_has_one_exact_dependency(self):
        pkg = read_json("package.json")
        self.assertIs(pkg["private"], True)
        self.assertEqual(set(pkg), {"name", "private", "description", "license", "dependencies"})
        self.assertEqual(pkg["dependencies"], {agents.CLAUDE_ACP_PACKAGE: agents.CLAUDE_ACP_VERSION})
        for key in ("devDependencies", "optionalDependencies", "peerDependencies", "scripts", "bin"):
            self.assertNotIn(key, pkg)

    def test_the_three_versions_are_equal_and_exact(self):
        pkg = read_json("package.json")
        lock = read_json("package-lock.json")
        want = agents.CLAUDE_ACP_VERSION
        self.assertEqual(pkg["dependencies"][agents.CLAUDE_ACP_PACKAGE], want)
        self.assertEqual(lock["packages"][""]["dependencies"], {agents.CLAUDE_ACP_PACKAGE: want})
        self.assertEqual(lock["packages"]["node_modules/" + agents.CLAUDE_ACP_PACKAGE]["version"], want)
        self.assertEqual(lock["name"], pkg["name"])
        for v in (want, pkg["dependencies"][agents.CLAUDE_ACP_PACKAGE]):
            self.assertRegex(v, EXACT)
            self.assertFalse(set(v) & RANGE_CHARS, v)

    def test_the_lockfile_has_integrity_hashes_and_no_install_script(self):
        lock = read_json("package-lock.json")
        self.assertEqual(lock["lockfileVersion"], 3)
        pkgs = {k: v for k, v in lock["packages"].items() if k}
        self.assertEqual(len(pkgs), 115)
        for name, entry in pkgs.items():
            with self.subTest(package=name):
                self.assertTrue(entry["integrity"].startswith("sha512-"))
                self.assertTrue(entry["resolved"].startswith("https://registry.npmjs.org/"))
                self.assertNotIn("hasInstallScript", entry)
                self.assertNotIn("link", entry)
        optional = sorted(k for k, v in pkgs.items() if v.get("optional"))
        self.assertEqual(len(optional), 8)
        self.assertTrue(all(k.startswith("node_modules/@anthropic-ai/claude-agent-sdk-") for k in optional))

    def test_node_modules_is_ignored_and_not_committed(self):
        lines = (FOLDER / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("node_modules/", lines)
        if not (REPO / ".git").exists() or shutil.which("git") is None:
            self.skipTest("not a git checkout")
        r = subprocess.run(["git", "check-ignore", "-q", "adapters/claude_acp/node_modules/x/index.js"],
                           cwd=REPO, capture_output=True, timeout=30)
        self.assertEqual(r.returncode, 0, "node_modules/ is not ignored")
        r = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, timeout=30, check=True)
        self.assertFalse([f for f in r.stdout.splitlines() if "node_modules" in f.split("/")])

    def test_the_readme_has_the_install_command_and_the_pin_steps(self):
        text = (FOLDER / "README.md").read_text(encoding="utf-8")
        self.assertIn("npm ci --ignore-scripts", text)
        self.assertIn("npm install --package-lock-only --ignore-scripts", text)
        self.assertIn(agents.CLAUDE_ACP_VERSION, text)
        self.assertIn("/login", text)
        self.assertNotIn("\u2014", text)


class CanaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-canary-")
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name).resolve()

    def run_canary(self, *args):
        r = subprocess.run([sys.executable, str(CANARY), *args], capture_output=True, stdin=subprocess.DEVNULL,
                           cwd=str(self.dir), timeout=30, env={"PATH": os.environ.get("PATH", "")})
        self.assertEqual((r.stdout, r.stderr), (b"", b""), "the canary must print nothing")
        return r.returncode

    def test_it_creates_one_empty_private_file(self):
        self.assertEqual(self.run_canary("--dir", str(self.dir), "--token", TOKEN), 0)
        self.assertEqual(os.listdir(self.dir), [TOKEN])
        st = os.lstat(self.dir / TOKEN)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertEqual(st.st_size, 0)
        self.assertEqual(stat.S_IMODE(st.st_mode) & 0o077, 0)

    def test_the_flags_may_come_in_either_order(self):
        self.assertEqual(self.run_canary("--token", TOKEN, "--dir", str(self.dir)), 0)
        self.assertEqual(os.listdir(self.dir), [TOKEN])

    def test_an_existing_file_or_link_is_refused(self):
        (self.dir / TOKEN).write_text("keep", encoding="utf-8")
        self.assertEqual(self.run_canary("--dir", str(self.dir), "--token", TOKEN), 2)
        self.assertEqual((self.dir / TOKEN).read_text(encoding="utf-8"), "keep")
        other = "f" * 32
        os.symlink(self.dir / "elsewhere", self.dir / other)
        self.assertEqual(self.run_canary("--dir", str(self.dir), "--token", other), 2)
        self.assertFalse((self.dir / "elsewhere").exists())

    def test_bad_tokens_are_refused(self):
        for token in ("", "0" * 31, "0" * 33, TOKEN.upper(), "g" * 32, "../" + "0" * 29, "0" * 31 + "/",
                      "0" * 31 + "\u00e9", " " + "0" * 31):
            with self.subTest(token=token):
                self.assertEqual(self.run_canary("--dir", str(self.dir), "--token", token), 2)
                self.assertEqual(os.listdir(self.dir), [])

    def test_bad_folders_are_refused(self):
        a_file = self.dir / "file"
        a_file.write_text("", encoding="utf-8")
        real = self.dir / "real"
        real.mkdir()
        link = self.dir / "link"
        os.symlink(real, link)
        for folder in ("real", "./real", "relative", "", str(self.dir / "missing"), str(a_file), str(link),
                       str(real) + "/../real"):  # the canary runs in self.dir, so "real" exists there
            with self.subTest(folder=folder):
                self.assertEqual(self.run_canary("--dir", folder, "--token", TOKEN), 2)
        self.assertEqual(os.listdir(real), [])
        self.assertFalse((self.dir / TOKEN).exists())

    def test_bad_arguments_are_refused(self):
        d = str(self.dir)
        for args in ((), ("--dir", d), ("--token", TOKEN), ("--dir", d, "--dir", d),
                     ("--token", TOKEN, "--token", TOKEN), ("--dir", d, "--token", TOKEN, "--extra"),
                     ("--dir", d, "--tok", TOKEN), ("--dir=" + d, "--token=" + TOKEN), ("-h",), ("--help",),
                     ("--dir", d, "--token", TOKEN, "--dir", d)):
            with self.subTest(args=args):
                self.assertEqual(self.run_canary(*args), 2)
        self.assertEqual(os.listdir(self.dir), [])

    def test_it_imports_only_the_standard_library(self):
        tree = ast.parse(CANARY.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertTrue(names)
        self.assertTrue(names <= set(sys.stdlib_module_names), names)
        self.assertNotIn("umwayi", names)
        self.assertNotIn("adapters", names)


if __name__ == "__main__":
    unittest.main()
