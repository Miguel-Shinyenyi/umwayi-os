import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from umwayi.cli import main
from umwayi.config import load_config
from umwayi.errors import UmwayiError
from umwayi.memory import is_private, load_bundle

SECRET = "TOP-SECRET-VALUE-123"


def write(root: Path, rel: str, text: str = "x") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class MemoryBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def config(self, private=None, memory_dir="memory"):
        (self.root / "umwayi.json").write_text(
            json.dumps({"memory_dir": memory_dir, "private_paths": private or []}),
            encoding="utf-8",
        )
        return load_config(self.root)


class ConfigTests(MemoryBase):
    def test_missing_config_is_error(self):
        with self.assertRaises(UmwayiError):
            load_config(self.root)

    def test_invalid_configs(self):
        bad = [
            "not json",
            "[]",
            '{"memory_dir": "memory"}',
            '{"private_paths": []}',
            '{"memory_dir": "memory", "private_paths": "x"}',
            '{"memory_dir": "memory", "private_paths": [1]}',
            '{"memory_dir": "memory", "private_paths": ["../x"]}',
            '{"memory_dir": "memory", "private_paths": ["/etc"]}',
            '{"memory_dir": "../out", "private_paths": []}',
            '{"memory_dir": "memory", "private_paths": [], "extra": 1}',
        ]
        for text in bad:
            with self.subTest(text=text):
                (self.root / "umwayi.json").write_text(text, encoding="utf-8")
                with self.assertRaises(UmwayiError):
                    load_config(self.root)

    def test_normalizes_paths(self):
        cfg = self.config(private=["./memory/private/"])
        self.assertEqual(cfg.private_paths, ("memory/private",))


class PrivateMatchTests(unittest.TestCase):
    def test_matching(self):
        priv = ("memory/private", "memory/journal/*-private.md")
        self.assertTrue(is_private("memory/private", priv))
        self.assertTrue(is_private("memory/private/a/b.md", priv))
        self.assertTrue(is_private("memory/PRIVATE/a.md", priv))  # case-insensitive
        self.assertTrue(is_private("memory/journal/2026-11-07-private.md", priv))
        self.assertFalse(is_private("memory/privateer.md", priv))
        self.assertFalse(is_private("memory/journal/2026-11-07.md", priv))


class BundleTests(MemoryBase):
    def test_order_and_sections(self):
        write(self.root, "memory/master.md", "MASTER")
        write(self.root, "memory/projects/b.md", "B")
        write(self.root, "memory/projects/a.md", "A")
        write(self.root, "memory/journal/2026-01-02.md", "J2")
        write(self.root, "memory/journal/2026-01-01.md", "J1")
        bundle = load_bundle(self.config())
        self.assertEqual(
            [e.path for e in bundle.entries],
            [
                "memory/master.md",
                "memory/projects/a.md",
                "memory/projects/b.md",
                "memory/journal/2026-01-01.md",
                "memory/journal/2026-01-02.md",
            ],
        )
        self.assertEqual(bundle.render(), load_bundle(self.config()).render())  # stable

    def test_private_never_in_bundle(self):
        write(self.root, "memory/master.md", "ok")
        write(self.root, "memory/projects/public.md", "public")
        write(self.root, "memory/projects/private/plan.md", SECRET)
        write(self.root, "memory/journal/2026-01-01-private.md", SECRET)
        write(self.root, "memory/journal/2026-01-02.md", "fine")
        bundle = load_bundle(
            self.config(private=["memory/projects/private", "memory/journal/*-private.md"])
        )
        for rendered in (bundle.render(), bundle.to_json()):
            self.assertNotIn(SECRET, rendered)
            self.assertNotIn("plan.md", rendered)
            self.assertNotIn("-private", rendered)
        self.assertEqual(bundle.excluded_count, 2)

    def test_private_master(self):
        write(self.root, "memory/master.md", SECRET)
        bundle = load_bundle(self.config(private=["memory/master.md"]))
        self.assertNotIn(SECRET, bundle.render())

    def test_private_projects_folder_whole(self):
        write(self.root, "memory/projects/a.md", SECRET)
        bundle = load_bundle(self.config(private=["memory/projects"]))
        self.assertEqual(bundle.entries, [])
        self.assertEqual(bundle.excluded_count, 1)

    def test_symlinks_not_followed(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        (outside / "secret.md").write_text(SECRET, encoding="utf-8")
        write(self.root, "memory/master.md", "ok")
        (self.root / "memory/projects").mkdir(parents=True)
        try:
            os.symlink(outside / "secret.md", self.root / "memory/projects/link.md")
            os.symlink(outside, self.root / "memory/journal")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        bundle = load_bundle(self.config())
        self.assertNotIn(SECRET, bundle.render())

    def test_binary_and_other_files_skipped(self):
        write(self.root, "memory/master.md", "ok")
        (self.root / "memory/projects").mkdir(parents=True)
        (self.root / "memory/projects/bad.md").write_bytes(b"\xff\xfe\x00bad")
        write(self.root, "memory/projects/image.png", "not text")
        write(self.root, "memory/projects/.hidden.md", "hidden")
        bundle = load_bundle(self.config())
        self.assertEqual([e.path for e in bundle.entries], ["memory/master.md"])
        self.assertEqual(bundle.skipped_count, 1)

    def test_memory_dir_that_is_a_link_loop_is_a_config_error(self):
        # found by the corrupt state sweep in tests/test_system.py: it used to crash (exit 2)
        try:
            os.symlink("memory", self.root / "memory")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        with self.assertRaises(UmwayiError):
            load_bundle(self.config())
        code, out = MemoryCliTests.run_cli(self, "memory", "bundle")
        self.assertEqual((code, out), (64, ""))

    def test_missing_memory_dir_is_error(self):
        with self.assertRaises(UmwayiError):
            load_bundle(self.config())

    def test_empty_memory_ok(self):
        (self.root / "memory").mkdir()
        bundle = load_bundle(self.config())
        self.assertEqual(bundle.entries, [])
        self.assertIn("(none)", bundle.render())


class MemoryCliTests(MemoryBase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        code = main(["--root", str(self.root), *argv], out=buf)
        return code, buf.getvalue()

    def test_bundle_text_and_json(self):
        write(self.root, "memory/master.md", "HELLO")
        write(self.root, "memory/private/x.md", SECRET)
        self.config(private=["memory/private"])
        code, text = self.run_cli("memory", "bundle")
        self.assertEqual(code, 0)
        self.assertIn("HELLO", text)
        self.assertNotIn(SECRET, text)
        code, js = self.run_cli("memory", "bundle", "--format", "json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(js)["entries"][0]["text"], "HELLO")
        self.assertNotIn(SECRET, js)

    def test_bad_config_prints_nothing_and_exits_64(self):
        write(self.root, "memory/master.md", SECRET)
        (self.root / "umwayi.json").write_text("{broken", encoding="utf-8")
        code, text = self.run_cli("memory", "bundle")
        self.assertEqual(code, 64)
        self.assertEqual(text, "")


if __name__ == "__main__":
    unittest.main()
