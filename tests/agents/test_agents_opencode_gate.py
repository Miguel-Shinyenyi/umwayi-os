"""Layer 10 part 8, task 10.46: the six gate checks of an OpenCode agent (requirement 10.R13.8, design.md part 8).

Written before the code. Every test runs `python -m umwayi ... agent check|chat ...` as a real child process, with a fake
`opencode` (tests/agents/fake_opencode.py) first on PATH that answers --version and records every call, and a copy of the
umwayi source tree (so a test can plant a link or a file in it without touching the repository).

The checks, in this order, the first failure ends it (exit 2, one logbook entry "Refused agent NAME: not gated (CHECK:
...)", nothing started):

    command         opencode on PATH
    version         `opencode --version` (15 s, 64 KB at most) names 2.2.3 or newer
    files           the generic adapter's hook.py and the plugin's index.js: regular files, no link anywhere on the way,
                    inside the umwayi source tree; and the plugin folder holds nothing else (OC21)
    managed config  no /etc/opencode, no macOS managed folder or plist
    other config    no opencode.json, opencode.jsonc or .opencode from the workdir up to /; the global config folder has no
                    plugins, plugin, agents or agent entry and no opencode.json(c) that holds a key that widens the gate
    route           the provider is an offered route

Until the chat itself is built (10.48), an agent that passes every check is still not started: `agent chat` refuses with
exit 2 and says so. `agent check` says it is gated and starts nothing.
"""

import json
import os
import re
import sys
import unittest

from umwayi import agents

from tests.agents.support import REPO, SECRET, AgentCase, copy_src, tree_state
from tests.agents.test_agents_opencode_file import ROUTES, oc

ORDER = ["command", "version", "files", "managed config", "other config", "route"]
GLOBAL_KEYS = ["permissions", "permission", "policies", "plugins", "plugin", "agents", "agent", "experimental",
               "enabled_providers", "disabled_providers"]
ALLOW_LIST = set(agents.OPENCODE_ENV_NAMES) | {"OPENCODE_CONFIG_CONTENT"}
YES_RULE = """rules:
  - id: o-yes
    title: o may start
    text: The agent o may start.
    verdict: yes
    matchers:
      type: agent_run
      agent: o
"""


class GateCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.src = copy_src(self.tmp / "src")
        self.fake_opencode()
        self.deep = self.tmp / "a" / "b" / "work"  # two folders below tmp/a, for a config two levels up
        self.deep.mkdir(parents=True)
        self.xdg = self.home / ".config"
        self.managed = self.tmp / "managed" / "opencode"
        self.plist_root = self.tmp / "managed-prefs"
        self.plugin_dir = self.src / agents.OPENCODE_PLUGIN_DIR
        self.index = self.plugin_dir / "index.js"
        self.hook = self.src / "adapters" / "stdio" / "hook.py"
        self.write_agent()

    def write_agent(self, provider="ollama", model=None, workdir=None):
        self.write_agents(oc(provider=provider, model=model or f"{provider}/m", workdir=str(workdir or self.deep)))

    def env(self, extra=None, fault=None):
        env = super().env(None, fault)
        env["XDG_CONFIG_HOME"] = str(self.xdg)
        env["UMWAYI_TEST_OPENCODE_MANAGED"] = json.dumps({"dirs": [str(self.managed)], "plist_root": str(self.plist_root)})
        env["UMWAYI_TEST_OPENCODE_VERSION_TIMEOUT"] = "1.5"
        env.update(extra or {})
        return env

    # ----------------------------------------------------------- runs

    def check(self, **kw):
        return self.umwayi("check", "o", **kw)

    def chat(self, rules=True, **kw):
        if rules:
            self.write_rules(YES_RULE)
        return self.umwayi("chat", "o", **kw)

    def lines_of(self, r):
        return {m.group(2): (m.group(1), m.group(3)) for m in
                (re.match(r"^(ok|no|not run): ([a-z ]+): (.*)$", ln) for ln in r.stdout.splitlines()) if m}

    def refused_entries(self):
        return [e for e in self.run_entries() if e.added.startswith("Refused agent o")]

    def assert_refused(self, name, words, **kw):
        """The check `name` refuses, in `agent check` and in `agent chat`, and nothing is started either time."""
        before = len(self.refused_entries())  # a test may refuse several times in turn
        r = self.check(**kw)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        lines = self.lines_of(r)
        for earlier in ORDER[:ORDER.index(name)]:
            self.assertEqual(lines[earlier][0], "ok", f"{earlier}: {r.stdout}")
        self.assertEqual(lines[name][0], "no", r.stdout)
        self.assertIn(words, lines[name][1], r.stdout)
        for later in ORDER[ORDER.index(name) + 1:]:
            self.assertEqual(lines[later], ("not run", "an earlier check failed"), r.stdout)
        self.assertIn("Not gated: agent o would be refused (exit 2). Nothing was started.", r.stdout)
        self.assertEqual(len(self.refused_entries()), before, "agent check writes nothing")
        c = self.chat(**kw)
        self.assertEqual(c.returncode, 2, c.stdout + c.stderr)
        self.assertEqual(self.lines_of(c)[name][0], "no", c.stdout)
        self.assertIn("Refused: agent o cannot be gated, so it was not started (exit 2).", c.stdout)
        self.assertEqual(len(self.refused_entries()), before + 1)  # one logbook entry for the refusal
        entry = self.refused_entries()[-1]
        self.assertTrue(entry.added.startswith(f"Refused agent o: not gated ({name}: "), entry.added)
        self.assertIn(words, entry.added)
        self.assertEqual([e for e in self.run_entries() if "Started" in e.added], [])
        self.assertEqual(self.started(), [], "a program was started")
        return r, c

    def assert_passes(self, **kw):
        r = self.check(**kw)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = self.lines_of(r)
        self.assertEqual([lines[n][0] for n in ORDER], ["ok"] * 6, r.stdout)
        return r


# ------------------------------------------------------------------------------------------------ all pass


class AllPassTests(GateCase):
    def test_every_check_is_ok_and_agent_check_says_gated_and_starts_nothing(self):
        r = self.assert_passes()
        lines = self.lines_of(r)
        self.assertIn("opencode found at", lines["command"][1])
        self.assertEqual(lines["version"][1], "2.2.7 (at least 2.2.3)")
        self.assertIn("hook.py", lines["files"][1])
        self.assertIn("index.js", lines["files"][1])
        self.assertIn("ollama", lines["route"][1])
        self.assertIn("Agent o: opencode, transport acp, workdir", r.stdout)
        self.assertIn("Gated: the checks for an OpenCode chat of agent o passed. Nothing was started.", r.stdout)
        self.assertEqual([c["argv"] for c in self.calls()], [["--version"]])  # nothing but the version flag
        self.assertEqual(self.started(), [])

    def test_the_version_runs_in_the_workdir_with_the_allow_listed_environment_and_an_empty_config(self):
        planted = {"ANTHROPIC_API_KEY": SECRET, "OPENAI_API_KEY": SECRET, "OPENCODE_API_KEY": SECRET,
                   "OPENCODE_CONFIG": "/evil", "OPENCODE_CONFIG_DIR": "/evil", "OPENCODE_DB": "/evil",
                   "OPENCODE_PASSWORD": SECRET, "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "AWS_SECRET_ACCESS_KEY": SECRET,
                   "HF_TOKEN": SECRET, "GITHUB_TOKEN": SECRET, "NODE_OPTIONS": "--require=/evil.js",
                   "OPENCODE_CONFIG_CONTENT": '{"permissions":[]}'}
        self.assert_passes(extra=planted)
        [call] = self.calls()
        self.assertEqual(call["cwd"], str(self.deep))
        self.assertLessEqual(set(call["env_keys"]), ALLOW_LIST, sorted(set(call["env_keys"]) - ALLOW_LIST))
        for name in planted:
            if name != "OPENCODE_CONFIG_CONTENT":
                self.assertNotIn(name, call["env_keys"])
        self.assertEqual(call["config_content"], "{}")  # umwayi's own, never the planted one

    def test_every_offered_route_passes(self):
        for provider, model in ROUTES.items():
            with self.subTest(provider=provider):
                self.write_agent(provider, model)
                r = self.assert_passes()
                self.assertIn(provider, self.lines_of(r)["route"][1])

    def test_agent_check_writes_nothing_and_logs_nothing(self):
        before = tree_state(self.root, self.work, self.deep)
        self.check()
        self.assertEqual(tree_state(self.root, self.work, self.deep), before)

    def test_a_pass_with_the_chat_not_built_yet_is_refused_with_one_entry_and_nothing_started(self):
        c = self.chat()
        self.assertEqual(c.returncode, 2, c.stdout + c.stderr)
        self.assertIn("the OpenCode chat is not built yet", c.stdout)
        [entry] = self.refused_entries()
        self.assertIn("the OpenCode chat is not built yet", entry.added)
        self.assertEqual(self.started(), [])
        self.assertEqual([e for e in self.run_entries() if e.added.startswith("Started agent")], [])


# ------------------------------------------------------------------------------------------------ 1 command


class CommandTests(GateCase):
    def test_no_opencode_on_path(self):
        (self.bin / "opencode").unlink()
        self.assert_refused("command", "opencode was not found on PATH", extra={"PATH": str(self.bin)})

    def test_a_relative_path_entry_does_not_count(self):
        (self.bin / "opencode").unlink()
        (self.tmp / "opencode").write_text("#!/bin/sh\necho opencode v2.2.7\n", encoding="utf-8")
        (self.tmp / "opencode").chmod(0o755)
        # PATH is "." and umwayi runs in self.tmp: which() finds ./opencode, a relative path, and it is not accepted
        r = self.check(extra={"PATH": "."})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.lines_of(r)["command"][0], "no")

    def test_the_command_word_is_fixed_by_the_platform_table(self):
        self.write_agents(oc(command="/usr/bin/opencode"))
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64)


# ------------------------------------------------------------------------------------------------ 2 version


class VersionTests(GateCase):
    def say(self, text, **cfg):
        """The fake answers `text` to --version. Returns the extra environment to pass (none)."""
        self.fake_opencode(version=text, **cfg)
        return None

    def test_versions_that_pass(self):
        for text in ("opencode v2.2.3", "opencode v2.2.7", "2.2.3", "opencode 2.3.0", "v2.10.0", "opencode v3.0.0",
                     "opencode v2.2.3-beta.1", "OpenCode 2.2.7 (build 1.2.3)"):
            with self.subTest(text=text):
                self.say(text)
                self.assert_passes()

    def test_v1_and_older_v2_are_refused(self):
        for text, shown in (("opencode v1.18.30", "1.18.30"), ("opencode v2.2.2", "2.2.2"), ("opencode v2.1.9", "2.1.9"),
                            ("opencode v2.0.0", "2.0.0"), ("1.0.0", "1.0.0"), ("opencode v0.9.9", "0.9.9")):
            with self.subTest(text=text):
                self.say(text)
                self.assert_refused("version", f"{shown} is older than 2.2.3")

    def test_the_refusal_names_why_the_minimum_is_2_2_3(self):
        self.say("opencode v1.18.30")
        r = self.check()
        self.assertIn("integration.use, mcp.use and plugin.use need OpenCode 2.2.3 or later", r.stdout)

    def test_output_that_cannot_be_read_is_refused(self):
        cases = (("no number", dict(version="opencode (unknown)")), ("empty", dict(version="")),
                 ("two numbers only", dict(version="opencode v2.2")), ("words", dict(version="two point two three")),
                 ("number past the first 4096 bytes", dict(version="opencode v2.2.7", big=5000)))
        for label, cfg in cases:
            with self.subTest(case=label):
                self.fake_opencode(**cfg)
                self.assert_refused("version", "no version number in the output of opencode --version")

    def test_a_failing_exit_code_is_refused_even_with_a_good_version(self):
        self.fake_opencode(version="opencode v2.2.7", exit=3)
        self.assert_refused("version", "opencode --version exited 3")

    def test_a_version_that_does_not_come_in_time_is_refused(self):
        self.fake_opencode(hang=True)
        self.assert_refused("version", "did not answer within")

    def test_the_limit_is_15_seconds_and_the_flag_is_version(self):
        self.assertEqual(agents.OPENCODE_VERSION_TIMEOUT, 15.0)
        self.assertEqual(agents.PLATFORMS["opencode"].version_flag, "--version")

    def test_the_hook_files_are_not_looked_at_when_the_version_is_refused(self):
        self.index.unlink()
        self.say("opencode v1.0.0")
        r = self.check()
        lines = self.lines_of(r)
        self.assertEqual(lines["version"][0], "no")
        self.assertEqual(lines["files"], ("not run", "an earlier check failed"))


# ------------------------------------------------------------------------------------------------ 3 files


class FilesTests(GateCase):
    def test_a_link_in_place_of_index_js(self):
        target = self.tmp / "elsewhere.js"
        target.write_text("export default {}\n", encoding="utf-8")
        self.index.unlink()
        self.index.symlink_to(target)
        self.assert_refused("files", str(self.index))

    def test_a_link_in_place_of_the_generic_hook(self):
        target = self.tmp / "hook-copy.py"
        target.write_text(self.hook.read_text(encoding="utf-8"), encoding="utf-8")
        self.hook.unlink()
        self.hook.symlink_to(target)
        self.assert_refused("files", str(self.hook))

    def test_the_plugin_folder_is_a_link_to_a_folder_outside_the_tree(self):
        outside = self.tmp / "outside-plugin"
        os.rename(self.plugin_dir, outside)
        self.plugin_dir.symlink_to(outside)
        self.assert_refused("files", str(self.index))

    def test_the_plugin_folder_is_a_link_to_a_folder_inside_the_tree(self):
        inside = self.src / "adapters" / "opencode" / "plugin-real"
        os.rename(self.plugin_dir, inside)
        self.plugin_dir.symlink_to(inside)
        self.assert_refused("files", str(self.index))  # a link on the way is refused even when it stays inside

    def test_a_parent_folder_of_the_hook_is_a_link(self):
        real = self.src / "adapters" / "stdio-real"
        os.rename(self.src / "adapters" / "stdio", real)
        (self.src / "adapters" / "stdio").symlink_to(real)
        self.assert_refused("files", str(self.hook))

    def test_index_js_is_missing(self):
        self.index.unlink()
        self.assert_refused("files", "is missing or not a regular file")

    def test_the_generic_hook_is_missing(self):
        self.hook.unlink()
        self.assert_refused("files", str(self.hook))

    def test_index_js_is_a_folder(self):
        self.index.unlink()
        self.index.mkdir()
        self.assert_refused("files", "is missing or not a regular file")

    def test_the_plugin_folder_holds_something_besides_index_js(self):
        # OpenCode loads `server` before `index` from a folder without a package.json (NOTES, 10.42 and Nov 11), and a
        # package.json changes how the folder loads: so the folder holds index.js and nothing else (OC21)
        for name in ("server.js", "server.ts", "index.ts", "package.json", "extra.txt", ".hidden", "node_modules"):
            with self.subTest(name=name):
                extra = self.plugin_dir / name
                if name == "node_modules":
                    extra.mkdir()
                else:
                    extra.write_text("x", encoding="utf-8")
                r = self.check()
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertEqual(self.lines_of(r)["files"][0], "no")
                self.assertIn("holds more than index.js", self.lines_of(r)["files"][1])
                self.assertIn(name, self.lines_of(r)["files"][1])
                if name == "node_modules":
                    extra.rmdir()
                else:
                    extra.unlink()

    def test_a_file_name_that_is_not_plain_text_is_not_shown(self):
        weird = self.plugin_dir / ("x\u202e" + "y" * 100)
        weird.write_text("x", encoding="utf-8")
        r = self.check()
        detail = self.lines_of(r)["files"][1]
        self.assertIn("holds more than index.js", detail)
        self.assertNotIn("\u202e", r.stdout)
        self.assertNotIn("y" * 100, r.stdout)

    def test_the_refusal_names_the_path_and_never_the_content(self):
        self.index.write_text(f"export default {{ secret: '{SECRET}' }}\n", encoding="utf-8")
        target = self.tmp / "t.js"
        target.write_text(SECRET, encoding="utf-8")
        self.index.unlink()
        self.index.symlink_to(target)
        r, c = self.assert_refused("files", str(self.index))
        self.assertNotIn(SECRET, r.stdout + r.stderr + c.stdout + c.stderr)
        self.assertNotIn(SECRET, (self.root / "LOGBOOK.md").read_text(encoding="utf-8"))

    def test_the_content_of_index_js_is_not_looked_at(self):
        # 10.46 checks what the file is, not what it says (the gate is proved by the canary at the start, 10.48)
        self.index.write_text("// changed\n", encoding="utf-8")
        self.assert_passes()


# ------------------------------------------------------------------------------------------------ 4 managed config


class ManagedConfigTests(GateCase):
    def test_a_managed_folder_exists(self):
        self.managed.mkdir(parents=True)
        self.assert_refused("managed config", str(self.managed))

    def test_an_empty_managed_folder_counts(self):
        self.managed.mkdir(parents=True)
        r = self.check()
        self.assertEqual(self.lines_of(r)["managed config"][0], "no")

    def test_a_file_or_a_link_at_the_managed_path_counts(self):
        self.managed.parent.mkdir(parents=True)
        self.managed.write_text("x", encoding="utf-8")
        self.assertEqual(self.lines_of(self.check())["managed config"][0], "no")
        self.managed.unlink()
        self.managed.symlink_to(self.tmp / "nowhere")
        self.assertEqual(self.lines_of(self.check())["managed config"][0], "no")

    def test_a_managed_plist_in_the_preferences_folder(self):
        self.plist_root.mkdir()
        (self.plist_root / "ai.opencode.managed.plist").write_text("<plist/>", encoding="utf-8")
        self.assert_refused("managed config", "ai.opencode.managed.plist")

    def test_a_managed_plist_in_a_user_folder_of_the_preferences_folder(self):
        (self.plist_root / "alice").mkdir(parents=True)
        (self.plist_root / "alice" / "ai.opencode.managed.plist").write_text("<plist/>", encoding="utf-8")
        self.assert_refused("managed config", "ai.opencode.managed.plist")

    def test_other_files_in_the_preferences_folder_do_not_count(self):
        (self.plist_root / "alice").mkdir(parents=True)
        (self.plist_root / "alice" / "com.example.other.plist").write_text("<plist/>", encoding="utf-8")
        (self.plist_root / "ai.opencode.managed.plist.bak").write_text("x", encoding="utf-8")
        self.assert_passes()

    def test_a_missing_managed_place_and_a_missing_preferences_folder_are_fine(self):
        self.assert_passes()

    def test_the_real_places_are_the_ones_of_the_spec(self):
        self.assertEqual(agents.OPENCODE_MANAGED_DIRS, ("/etc/opencode", "/Library/Application Support/opencode"))
        self.assertEqual(agents.OPENCODE_MANAGED_PLIST_ROOT, "/Library/Managed Preferences")
        self.assertEqual(agents.OPENCODE_MANAGED_PLIST, "ai.opencode.managed.plist")

    def test_the_check_runs_after_the_files_check_and_before_the_other_config(self):
        self.managed.mkdir(parents=True)
        (self.deep / "opencode.json").write_text("{}", encoding="utf-8")
        r = self.check()
        lines = self.lines_of(r)
        self.assertEqual(lines["managed config"][0], "no")
        self.assertEqual(lines["other config"], ("not run", "an earlier check failed"))


# ------------------------------------------------------------------------------------------------ 5 other config


class ProjectConfigTests(GateCase):
    def test_a_project_config_in_the_workdir_in_each_form(self):
        for name, kind in (("opencode.json", "file"), ("opencode.jsonc", "file"), (".opencode", "dir"),
                           (".opencode", "file")):
            with self.subTest(name=name, kind=kind):
                path = self.deep / name
                if kind == "dir":
                    path.mkdir()
                else:
                    path.write_text("{}", encoding="utf-8")
                self.assert_refused("other config", str(path))
                if kind == "dir":
                    path.rmdir()
                else:
                    path.unlink()

    def test_a_project_config_one_and_two_levels_up(self):
        for up in (self.deep.parent, self.deep.parent.parent):
            with self.subTest(folder=str(up)):
                path = up / "opencode.json"
                path.write_text("{}", encoding="utf-8")
                self.assert_refused("other config", str(path))
                path.unlink()

    def test_a_project_config_in_the_folder_above_the_temporary_root(self):
        # the walk goes on to /: the folder that holds the whole test tree is looked at too
        path = self.tmp / "opencode.jsonc"
        path.write_text("{}", encoding="utf-8")
        self.assert_refused("other config", str(path))

    def test_a_dangling_link_named_like_a_config_counts(self):
        path = self.deep / "opencode.json"
        path.symlink_to(self.tmp / "nowhere.json")
        self.assert_refused("other config", str(path))

    def test_a_workdir_reached_through_a_link_is_walked_by_its_real_path_as_well(self):
        real = self.tmp / "real" / "deeper" / "work"
        real.mkdir(parents=True)
        link = self.tmp / "link-to-work"
        link.symlink_to(real)
        (self.tmp / "real" / "opencode.json").write_text("{}", encoding="utf-8")
        self.write_agent(workdir=link)
        r = self.check()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn(str(self.tmp / "real" / "opencode.json"), self.lines_of(r)["other config"][1])

    def test_a_config_in_a_folder_that_is_not_above_the_workdir_does_not_count(self):
        (self.deep.parent / "sibling").mkdir()
        (self.deep.parent / "sibling" / "opencode.json").write_text("{}", encoding="utf-8")
        (self.deep / "inner").mkdir()
        (self.deep / "inner" / "opencode.json").write_text("{}", encoding="utf-8")  # below the workdir: not found by a walk up
        self.assert_passes()

    def test_files_with_near_names_do_not_count(self):
        for name in ("opencode.yaml", "opencode.json.bak", "my-opencode.json", ".opencodes", "opencode"):
            (self.deep / name).write_text("{}", encoding="utf-8")
        self.assert_passes()


class GlobalConfigTests(GateCase):
    @property
    def gdir(self):
        return self.xdg / "opencode"

    def write(self, name, text):
        self.gdir.mkdir(parents=True, exist_ok=True)
        path = self.gdir / name
        path.write_text(text, encoding="utf-8") if isinstance(text, str) else path.write_bytes(text)
        return path

    def test_each_widening_key_in_each_file_name_is_refused_and_named(self):
        for name in ("opencode.json", "opencode.jsonc"):
            for key in GLOBAL_KEYS:
                with self.subTest(file=name, key=key):
                    path = self.write(name, '{ "%s": [] }' % key)
                    r = self.check()
                    self.assertEqual(r.returncode, 2, r.stdout)
                    detail = self.lines_of(r)["other config"][1]
                    self.assertIn(str(path), detail)
                    self.assertIn(f'"{key}"', detail)
                    path.unlink()

    def test_assert_refused_for_one_key(self):
        self.write("opencode.json", '{ "policies": [{"action": "provider.use"}] }')
        self.assert_refused("other config", '"policies"')

    def test_keys_that_do_not_widen_the_gate_pass(self):
        self.write("opencode.json", '{ "$schema": "https://opencode.ai/config.json", "model": "ollama/m", "theme": "x", '
                                    '"update": "notify", "shell": "/bin/zsh", "snapshots": false, "formatter": true }')
        self.assert_passes()

    def test_the_word_without_quotes_or_inside_another_word_is_not_a_hit(self):
        self.write("opencode.json", '{ "my_plugins_list": 1, "agents_md": 2, "xpolicies": 3, "policies2": 4 }')
        self.write("opencode.jsonc", "// plugins and policies are described elsewhere\n{ \"model\": \"ollama/m\" }\n")
        self.assert_passes()

    def test_a_comment_that_names_a_key_in_quotes_refuses_too(self):
        # a text match, not a parse: the safe direction (10.R13.8, item 5)
        self.write("opencode.jsonc", '// "plugin" is not used here\n{ "model": "ollama/m" }\n')
        self.assert_refused("other config", '"plugin"')

    def test_an_empty_file_and_an_empty_folder_pass(self):
        self.write("opencode.json", "")
        self.assert_passes()

    def test_a_file_that_is_not_utf8_is_refused(self):
        self.write("opencode.json", b'{ "model": "\xff\xfe\xfa" }')
        self.assert_refused("other config", "cannot be read as UTF-8 text")

    def test_a_file_over_one_megabyte_is_refused_unread(self):
        self.write("opencode.json", ('{ "model": "' + "a" * (1024 * 1024) + '" }'))
        self.assert_refused("other config", "larger than 1048576 bytes")

    def test_a_file_of_exactly_one_megabyte_is_read(self):
        text = "{" + " " * (1024 * 1024 - 2) + "}"
        self.assertEqual(len(text), 1024 * 1024)
        self.write("opencode.json", text)
        self.assert_passes()

    def test_a_link_or_a_folder_in_place_of_the_file_is_refused(self):
        real = self.tmp / "real.json"
        real.write_text("{}", encoding="utf-8")
        self.gdir.mkdir(parents=True)
        (self.gdir / "opencode.json").symlink_to(real)
        self.assert_refused("other config", "is a link or not a regular file")
        (self.gdir / "opencode.json").unlink()
        (self.gdir / "opencode.jsonc").mkdir()
        r = self.check()
        self.assertEqual(self.lines_of(r)["other config"][0], "no")

    def test_a_global_folder_entry_that_adds_plugins_or_agents_is_refused(self):
        for name in ("plugins", "plugin", "agents", "agent"):
            for kind in ("dir", "file", "link"):
                with self.subTest(name=name, kind=kind):
                    self.gdir.mkdir(parents=True, exist_ok=True)
                    path = self.gdir / name
                    if kind == "dir":
                        path.mkdir()
                    elif kind == "file":
                        path.write_text("x", encoding="utf-8")
                    else:
                        path.symlink_to(self.tmp / "nowhere")
                    r = self.check()
                    self.assertEqual(r.returncode, 2, r.stdout)
                    self.assertIn(str(path), self.lines_of(r)["other config"][1])
                    if kind == "dir":
                        path.rmdir()
                    else:
                        path.unlink()

    def test_other_entries_in_the_global_folder_are_fine(self):
        self.write("cli.json", '{ "plugins": ["x"] }')  # the terminal settings: a separate file, not the server config
        self.write("service.json", '{ "plugins": 1 }')
        (self.gdir / "commands").mkdir()
        (self.gdir / "skills").mkdir()
        self.assert_passes()

    def test_the_home_dot_opencode_folder_is_refused(self):
        path = self.home / ".opencode"
        path.mkdir()
        self.assert_refused("other config", str(path))

    def test_without_xdg_config_home_the_folder_is_dot_config_opencode_under_home(self):
        path = self.home / ".config" / "opencode" / "opencode.json"
        path.parent.mkdir(parents=True)
        path.write_text('{ "plugins": [] }', encoding="utf-8")
        r = self.check(extra={"XDG_CONFIG_HOME": ""})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn(str(path), self.lines_of(r)["other config"][1])

    def test_with_xdg_config_home_set_the_other_folder_is_not_looked_at(self):
        path = self.home / ".config" / "opencode" / "opencode.json"
        path.parent.mkdir(parents=True)
        path.write_text('{ "plugins": [] }', encoding="utf-8")
        other = self.tmp / "xdg-elsewhere"
        other.mkdir()
        self.assert_passes(extra={"XDG_CONFIG_HOME": str(other)})

    def test_the_refusal_names_the_path_and_the_key_but_never_the_text_of_the_file(self):
        path = self.write("opencode.json", '{ "plugin": ["%s"], "apiKey": "%s" }' % (SECRET, SECRET))
        r, c = self.assert_refused("other config", str(path))
        for text in (r.stdout, r.stderr, c.stdout, c.stderr, (self.root / "LOGBOOK.md").read_text(encoding="utf-8")):
            self.assertNotIn(SECRET, text)

    def test_nothing_in_the_global_config_is_changed_or_created(self):
        path = self.write("opencode.json", '{ "model": "x" }')
        before = tree_state(self.xdg, self.home)
        self.check()
        self.assertEqual(tree_state(self.xdg, self.home), before)
        self.assertEqual(path.read_text(encoding="utf-8"), '{ "model": "x" }')


# ------------------------------------------------------------------------------------------------ 6 route


class RouteTests(GateCase):
    def test_a_provider_that_is_pay_as_you_go_is_refused_with_its_name(self):
        for provider in ("openrouter", "anthropic", "together", "fireworks", "groq", "huggingface", "amazon-bedrock"):
            with self.subTest(provider=provider):
                self.write_agent(provider)
                self.assert_refused("route", f"provider {provider} is not offered")
                self.assertIn("pay as you go is not offered", self.check().stdout)

    def test_opencode_go_is_refused_with_its_own_line(self):
        self.write_agent("opencode-go")
        r, _ = self.assert_refused("route", "provider opencode-go (OpenCode Go) is not offered yet")
        self.assertNotIn("pay as you go is not offered", self.lines_of(r)["route"][1])

    def test_the_route_is_checked_last(self):
        self.write_agent("openrouter")
        (self.deep / "opencode.json").write_text("{}", encoding="utf-8")
        r = self.check()
        lines = self.lines_of(r)
        self.assertEqual(lines["other config"][0], "no")
        self.assertEqual(lines["route"], ("not run", "an earlier check failed"))


# ------------------------------------------------------------------------------------------------ order and wiring


class OrderTests(GateCase):
    def test_the_first_failure_ends_it_and_the_rest_are_not_run(self):
        # five faults at once: a V1 binary, a missing index.js, a managed folder, a project config, a pay as you go provider
        self.write_agent("openrouter")
        self.index.unlink()
        self.managed.mkdir(parents=True)
        (self.deep / "opencode.json").write_text("{}", encoding="utf-8")
        self.fake_opencode(version="opencode v1.18.30")
        r = self.check()
        lines = self.lines_of(r)
        self.assertEqual(lines["command"][0], "ok")
        self.assertEqual(lines["version"][0], "no")
        for later in ORDER[2:]:
            self.assertEqual(lines[later], ("not run", "an earlier check failed"))

    def test_with_the_faults_put_right_one_by_one_the_next_check_in_the_order_is_the_one_that_fails(self):
        self.write_agent("openrouter")
        self.index.unlink()
        self.managed.mkdir(parents=True)
        (self.deep / "opencode.json").write_text("{}", encoding="utf-8")
        self.fake_opencode(version="opencode v1.18.30")
        failing = []
        for fault in ORDER[1:]:  # version, files, managed config, other config, route
            r = self.check()
            lines = self.lines_of(r)
            failing.append([n for n in ORDER if lines[n][0] == "no"])
            if fault == "version":
                self.fake_opencode()
            elif fault == "files":
                self.index.write_text("export default {}\n", encoding="utf-8")
            elif fault == "managed config":
                self.managed.rmdir()
            elif fault == "other config":
                (self.deep / "opencode.json").unlink()
            elif fault == "route":
                self.write_agent("ollama")
        self.assertEqual(failing, [["version"], ["files"], ["managed config"], ["other config"], ["route"]])
        self.assert_passes()

    def test_the_kill_switch_and_the_rules_come_before_the_checks(self):
        r = self.umwayi("chat", "o")  # no rules.yaml: Ask me first
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [], "the version was asked before the rules")
        self.write_rules(YES_RULE)
        self.umwayi_kill_on()
        r = self.umwayi("chat", "o")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])

    def umwayi_kill_on(self):
        import subprocess
        subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "kill", "on"], check=True,
                       capture_output=True, env=self.env(), cwd=str(self.tmp))

    def test_a_rule_that_says_no_stops_the_chat_before_the_checks(self):
        self.write_rules(YES_RULE.replace("verdict: yes", "verdict: no"))
        r = self.umwayi("chat", "o")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.calls(), [])

    def test_agent_run_and_login_are_still_refused_before_any_check(self):
        for args in (("run", "o", "--prompt", "hi"), ("login", "o")):
            r = self.umwayi(*args)
            self.assertEqual(r.returncode, 64)
        self.assertEqual(self.calls(), [])

    def test_the_other_platforms_are_checked_as_before(self):
        self.fake("claude")
        self.write_agents("agents:\n  - name: c\n    platform: claude-code\n    command: claude\n    workdir: {work}\n")
        r = self.umwayi("check", "c")
        self.assertIn("ok: command: claude found at", r.stdout)
        self.assertNotIn("managed config", r.stdout)


class SourceTests(unittest.TestCase):
    """The checks only read: agents.py still starts one short program (the version flag) through _run_child."""

    def test_the_check_code_makes_no_new_program_start_and_writes_no_file(self):
        import ast
        src = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertIn("_opencode_checks", names)
        for fn in tree.body:
            if isinstance(fn, ast.FunctionDef) and fn.name.startswith("_opencode"):
                for n in ast.walk(fn):
                    if isinstance(n, ast.Attribute):
                        self.assertNotIn(n.attr, {"Popen", "system", "popen", "write_text", "write_bytes", "mkdir",
                                                  "unlink", "rmdir", "rename", "replace", "touch", "chmod", "symlink_to",
                                                  "makedirs", "remove", "rmtree", "mkdtemp"}, fn.name)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
                        self.assertEqual(n.args[1].value, "rb", fn.name)
        self.assertEqual(src.count('b"", OPENCODE_VERSION_TIMEOUT'), 1)  # one more call of the one function that starts a short program

    def test_the_limits_are_those_of_the_spec(self):
        self.assertEqual(agents.OPENCODE_VERSION_TIMEOUT, 15.0)
        self.assertEqual(agents.OPENCODE_MAX_GLOBAL_CONFIG, 1024 * 1024)
        self.assertEqual(agents.OPENCODE_GLOBAL_KEYS, tuple(GLOBAL_KEYS))
        self.assertEqual(agents.OPENCODE_GLOBAL_ENTRIES, ("plugins", "plugin", "agents", "agent"))
        self.assertEqual(agents.OPENCODE_PROJECT_NAMES, ("opencode.json", "opencode.jsonc", ".opencode"))


if __name__ == "__main__":
    unittest.main()
