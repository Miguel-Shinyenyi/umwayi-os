"""W49 and W50: signing a provenance record and `umwayi verify` (umwayi/provsign.py), with throwaway keys made by the test.

Each test makes its own ed25519 key in a temporary folder (no passphrase, never the owner's key, never `~/.ssh`), starts its own `ssh-agent`
on a socket in that folder, and adds the key. Skipped with a reason when `ssh-keygen` or `ssh-agent` is missing. Real `ssh-keygen -Y sign`
and `-Y verify` run; nothing here is a fake of them. What it does not show: a hardware key, a key with a passphrase, other ssh-keygen versions.

  * sign: the signature file and the signed entry appear together or not at all; every refusal writes neither; the owner's `yes` is needed;
    no private key is read by umwayi (a private key given as the public key is refused).
  * verify: unchanged 0, a real change 3, a comment in a `.py` file 0 with the structure line, no task made it 2, a record never signed 2,
    a flipped signature byte, a changed record byte, another key and a broken chain each 2 and never an older record; it writes nothing.
"""
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import logbook, provenance, provsign
from umwayi.errors import UmwayiError

REPO = Path(__file__).resolve().parent.parent
try:
    TOOLS = provsign.find_ssh_keygen() and shutil.which("ssh-agent") and shutil.which("ssh-add")
except provsign.SignError:
    TOOLS = None
DATE = "2026-11-23"


@unittest.skipUnless(TOOLS, "ssh-keygen, ssh-agent and ssh-add are needed")
class SignCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ups", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "root"
        self.wt = self.base / "wt"
        self.root.mkdir()
        (self.wt / "umwayi").mkdir(parents=True)
        self.keys = self.base / "keys"
        self.keys.mkdir(mode=0o700)
        self.sock = self.keys / "agent.sock"
        out = subprocess.run([shutil.which("ssh-agent"), "-a", str(self.sock)], capture_output=True, text=True, check=True).stdout
        self.agent_pid = int(next(l for l in out.splitlines() if "SSH_AGENT_PID" in l).split("=")[1].split(";")[0])
        self.addCleanup(lambda: os.kill(self.agent_pid, signal.SIGTERM))
        self.env_old = os.environ.get("SSH_AUTH_SOCK")
        os.environ["SSH_AUTH_SOCK"] = str(self.sock)
        self.addCleanup(self.restore_env)
        self.pub = self.make_key("k1", add=True)
        logbook.append(self.root, logbook.Entry(DATE, "test", "start", "x", "x"))
        logbook.seal(self.root, DATE, "test", start_chain=True)

    def restore_env(self):
        if self.env_old is None:
            os.environ.pop("SSH_AUTH_SOCK", None)
        else:
            os.environ["SSH_AUTH_SOCK"] = self.env_old

    def make_key(self, name, add):
        key = self.keys / name
        subprocess.run([provsign.find_ssh_keygen(), "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", str(key)], check=True)
        if add:
            subprocess.run([shutil.which("ssh-add"), "-q", str(key)], check=True, env=dict(os.environ, SSH_AUTH_SOCK=str(self.sock)))
        return Path(str(key) + ".pub")

    def record(self, goal="G-0001", task="T-01", content=b"x = 1\n", rel="umwayi/a.py"):
        (self.wt / rel).write_bytes(content)
        provenance.make(self.root, goal, task, "b" * 40, "t" * 40, "p" * 64, [("A", rel)], str(self.wt), DATE)

    def sign(self, goal="G-0001", task="T-01", key=None, yes=True):
        return provsign.sign_task(self.root, goal, task, DATE, key or self.pub, lambda lines: yes)

    def verify(self, rel="umwayi/a.py", key=None, anchor=None):
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        return provsign.verify_path(self.root, rel, key or self.pub, anchor)

    def put(self, rel, content):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    def snapshot(self):
        out = {}
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                out[str(p.relative_to(self.root))] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out


class SignTests(SignCase):
    def test_a_signed_record_has_a_signature_file_and_a_signed_entry_that_agree(self):
        self.record()
        got = self.sign()
        sig = provsign.sig_path(self.root, "G-0001", "T-01")
        self.assertEqual(oct(sig.stat().st_mode & 0o777), "0o600")
        entry = [e for e in logbook.read_checked(self.root) if provsign.parse_signed(e)][0]
        s = provsign.parse_signed(entry)
        self.assertEqual((s["goal"], s["task"], s["key"]), ("G-0001", "T-01", got["key"]))
        self.assertEqual(s["signature"], hashlib.sha256(sig.read_bytes()).hexdigest())
        self.assertNotIn("umwayi/a.py", entry.added + entry.checked + entry.not_done)

    def test_every_refusal_writes_neither_a_signature_nor_an_entry(self):
        self.record()
        before = (self.snapshot(), len(logbook.read_checked(self.root)))
        other = self.make_key("k2", add=False)
        cases = {"declined": lambda: self.sign(yes=False), "not in the agent": lambda: self.sign(key=other),
                 "no record": lambda: self.sign(task="T-09"), "private key as the key": lambda: self.sign(key=Path(str(self.pub)[:-4]))}
        for name, fn in cases.items():
            with self.subTest(case=name), self.assertRaises(provsign.SignError):
                fn()
            self.assertEqual((self.snapshot(), len(logbook.read_checked(self.root))), before)

    def test_no_agent_no_key_file_and_a_kill_switch_are_refusals(self):
        self.record()
        os.environ.pop("SSH_AUTH_SOCK")
        with self.assertRaises(provsign.SignError) as cm:
            self.sign()
        self.assertEqual(cm.exception.reason, "no_agent")
        os.environ["SSH_AUTH_SOCK"] = str(self.sock)
        with self.assertRaises(provsign.SignError) as cm:
            self.sign(key=self.base / "missing.pub")
        self.assertEqual(cm.exception.reason, "no_key")
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        with self.assertRaises(provsign.SignError) as cm:
            self.sign()
        self.assertEqual(cm.exception.reason, "kill_switch")

    def test_a_record_signed_once_is_not_signed_again_and_a_changed_record_is_not_signed(self):
        self.record()
        self.sign()
        with self.assertRaises(provsign.SignError) as cm:
            self.sign()
        self.assertEqual(cm.exception.reason, "signed_already")
        self.record(goal="G-0002", content=b"y = 2\n")
        p = provenance.record_path(self.root, "G-0002", "T-01")
        p.write_bytes(p.read_bytes().replace(b"\n", b" \n"))
        with self.assertRaises(provsign.SignError) as cm:
            self.sign(goal="G-0002")
        self.assertEqual(cm.exception.reason, "no_record")

    def test_a_logbook_without_a_chain_is_refused(self):
        self.record()
        text = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        # a fresh root with no chain: nothing to sign against
        other = self.base / "root2"
        other.mkdir()
        logbook.append(other, logbook.Entry(DATE, "test", "start", "x", "x"))
        with self.assertRaises(provsign.SignError) as cm:
            provsign.sign_task(other, "G-0001", "T-01", DATE, self.pub, lambda l: True)
        self.assertEqual(cm.exception.reason, "no_chain")

    def test_read_public_key_takes_one_allowed_public_line_only(self):
        for text in ("", "ssh-rsa AAAA x\n", "ssh-ed25519 AAAA\nssh-ed25519 BBBB\n", "-----BEGIN OPENSSH PRIVATE KEY-----\nx\n"):
            p = self.base / "k.pub"
            p.write_text(text, encoding="utf-8")
            with self.subTest(text=text[:20]), self.assertRaises(provsign.SignError):
                provsign.read_public_key(p)
        line, fp = provsign.read_public_key(self.pub)
        self.assertTrue(line.startswith("ssh-ed25519 ") and fp.startswith("SHA256:"))
        # the fingerprint equals ssh-keygen's own
        shown = subprocess.run([provsign.find_ssh_keygen(), "-lf", str(self.pub)], capture_output=True, text=True).stdout
        self.assertIn(fp, shown)


class VerifyTests(SignCase):
    def signed(self, content=b"x = 1\n"):
        self.record(content=content)
        self.sign()
        self.put("umwayi/a.py", content)

    def test_unchanged_is_0_and_a_real_change_is_3(self):
        self.signed()
        code, lines = self.verify()
        self.assertEqual(code, 0, lines)
        self.assertIn("made by umwayi and unchanged", lines[0])
        self.put("umwayi/a.py", b"x = 1\nprint(1)\n")  # a real change (a comment alone is the next test)
        code, lines = self.verify()
        self.assertEqual(code, 3, lines)
        self.assertIn("changed since", lines[0])

    def test_a_comment_in_a_python_file_is_0_with_the_structure_line(self):
        self.signed()
        self.put("umwayi/a.py", b"# note\nx = 1\n")
        code, lines = self.verify()
        self.assertEqual(code, 0, lines)
        self.assertIn("same structure; comments or formatting changed", lines[0])

    def test_a_file_no_task_made_and_a_record_never_signed_are_2_with_no_record(self):
        self.put("umwayi/other.py", b"z = 3\n")
        self.assertEqual(self.verify("umwayi/other.py")[0], 2)
        self.record(goal="G-0002", rel="umwayi/b.py", content=b"b = 1\n")  # made, never signed
        self.put("umwayi/b.py", b"b = 1\n")
        code, lines = self.verify("umwayi/b.py")
        self.assertEqual((code, lines[0]), (2, "no record: no signed record names this file."))

    def test_a_flipped_signature_byte_a_changed_record_and_another_key_are_2_never_0(self):
        self.signed()
        sig = provsign.sig_path(self.root, "G-0001", "T-01")
        good_sig, rec = sig.read_bytes(), provenance.record_path(self.root, "G-0001", "T-01")
        good_rec = rec.read_bytes()
        mid = len(good_sig) // 2
        sig.write_bytes(good_sig[:mid] + (b"A" if good_sig[mid:mid + 1] != b"A" else b"B") + good_sig[mid + 1:])
        code, lines = self.verify()
        self.assertEqual(code, 2, lines)
        self.assertIn("signed but not trusted", lines[0])
        sig.write_bytes(good_sig)
        rec.write_bytes(good_rec.replace(b'"version":1', b'"version":2'))
        self.assertEqual(self.verify()[0], 2)
        rec.write_bytes(good_rec)
        self.assertEqual(self.verify()[0], 0)  # restored: trusted again
        other = self.make_key("k2", add=False)
        self.assertEqual(self.verify(key=other)[0], 2)

    def test_a_newer_untrusted_record_never_falls_back_to_an_older_one(self):
        self.signed()
        self.record(goal="G-0002", content=b"x = 1\n")
        self.sign(goal="G-0002")
        sig2 = provsign.sig_path(self.root, "G-0002", "T-01")
        data = sig2.read_bytes()
        sig2.write_bytes(data.replace(data.splitlines()[2].encode() if isinstance(data.splitlines()[2], str) else data.splitlines()[2], b"A" * len(data.splitlines()[2]), 1))
        self.assertEqual(self.verify()[0], 2)

    def test_changed_by_a_later_task_and_put_back_names_the_older_record(self):
        self.signed(content=b"x = 1\n")
        self.record(goal="G-0002", content=b"x = 2\n")
        self.sign(goal="G-0002")
        self.put("umwayi/a.py", b"x = 1\n")  # put back to the first task's bytes
        code, lines = self.verify()
        self.assertEqual(code, 3, lines)
        self.assertIn("older record (G-0001 T-01) matches", lines[0])

    def test_a_broken_chain_and_a_wrong_anchor_are_2(self):
        self.signed()
        self.assertEqual(self.verify(anchor=(1, "0" * 64))[0], 2)
        text = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        (self.root / "LOGBOOK.md").write_text(text.replace("start", "begin", 1), encoding="utf-8")
        self.assertEqual(self.verify()[0], 2)

    def test_verify_writes_nothing(self):
        self.signed()
        self.put("umwayi/a.py", b"x = 1\nprint(1)\n")  # a changed file, so the answer is 3 and the code reaches every branch
        before = self.snapshot()
        self.verify()
        self.assertEqual(self.snapshot(), before)  # no file of the root changed, no entry, no temporary file left


@unittest.skipUnless(TOOLS, "ssh-keygen, ssh-agent and ssh-add are needed")
class CommandTests(SignCase):
    def run_cmd(self, *args, stdin=subprocess.DEVNULL):
        p = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args], capture_output=True, text=True, stdin=stdin,
                           timeout=60, env=dict(os.environ, PYTHONPATH=str(REPO)), cwd=str(self.root))
        self.assertIn(p.returncode, (0, 2, 3, 64), p.stdout + p.stderr)
        return p

    def config(self, key=True):
        import json
        doc = {"memory_dir": "m", "private_paths": [], "provenance": {"record": True}}
        if key:
            doc["provenance"]["public_key"] = str(self.pub)
        (self.root / "umwayi.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_verify_by_the_command_0_3_and_the_usage_cases_64(self):
        self.config()
        self.record()
        self.sign()
        self.put("umwayi/a.py", b"x = 1\n")
        self.assertEqual(self.run_cmd("verify", "umwayi/a.py").returncode, 0)
        self.put("umwayi/a.py", b"x = 9\n")
        self.assertEqual(self.run_cmd("verify", "umwayi/a.py").returncode, 3)
        os.symlink(self.root / "umwayi" / "a.py", self.root / "link.py")
        for bad in ("link.py", "umwayi", "../outside.py", "nope.py"):
            with self.subTest(path=bad):
                self.assertEqual(self.run_cmd("verify", bad).returncode, 64)

    def test_no_key_configured_is_usage(self):
        self.config(key=False)
        self.put("umwayi/a.py", b"x = 1\n")
        self.assertEqual(self.run_cmd("verify", "umwayi/a.py").returncode, 64)

    def test_signing_needs_the_owners_terminal(self):
        self.config()
        self.record()
        p = self.run_cmd("provenance", "sign", "G-0001", "T-01")
        self.assertEqual(p.returncode, 2)
        self.assertIn("refused: signing is the owner's, at the owner's terminal", p.stdout)
        self.assertFalse(provsign.sig_path(self.root, "G-0001", "T-01").exists())


class SourceTests(unittest.TestCase):
    def test_umwayi_never_reads_a_private_key_and_runs_only_ssh_keygen_sign_and_verify(self):
        src = (REPO / "umwayi" / "provsign.py").read_text(encoding="utf-8")
        self.assertEqual(src.count('"-Y", "sign", "-U"'), 1)
        self.assertEqual(src.count('"-Y", "verify"'), 1)
        for bad in ("ssh-add", "shell=True", "os.system", "id_ed25519", ".ssh"):
            self.assertNotIn(bad, src.split('"""', 2)[2])
        self.assertEqual(src.count("subprocess.run("), 1)


if __name__ == "__main__":
    unittest.main()
