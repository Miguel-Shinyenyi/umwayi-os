"""W27: the shape of .github/workflows/progress-page.yml. A workflow cannot be run here, so this test reads the file as text
and pins what the owner decided: it runs on a push to main, it builds the page with the W22 build command, it keeps the page
as a workflow artifact, and it publishes nothing (no Pages, no deploy step, no secret, no write permission).
Standard library only. The real run on GitHub is the record.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATH = REPO / ".github" / "workflows" / "progress-page.yml"
TEXT = PATH.read_text(encoding="utf-8")
CODE = "\n".join(line for line in TEXT.split("\n") if not line.lstrip().startswith("#"))


def block(name):
    """The lines of the top level key `name` (its indented body), comments left out."""
    lines = CODE.split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"{name}:"))
    out = []
    for ln in lines[start + 1:]:
        if ln and not ln.startswith(" "):
            break
        out.append(ln)
    return "\n".join(out)


class TriggerTests(unittest.TestCase):
    def test_it_runs_on_a_push_to_main_and_on_nothing_else(self):
        on = block("on")
        self.assertEqual(re.findall(r"^  (\w[\w-]*):", on, re.M), ["push"])
        self.assertRegex(on, r"branches: \[main\]")

    def test_it_never_runs_for_a_pull_request(self):
        self.assertNotIn("pull_request", CODE)
        self.assertNotIn("workflow_dispatch", CODE)
        self.assertNotIn("schedule:", CODE)


class BuildTests(unittest.TestCase):
    def test_it_uses_the_w22_build_command_in_ui(self):
        self.assertIn("working-directory: ui", CODE)
        steps = re.findall(r"^\s+(npm ci --ignore-scripts|node build\.mjs)\s*$", CODE, re.M)
        self.assertEqual(steps, ["npm ci --ignore-scripts", "node build.mjs"])

    def test_the_command_is_the_one_the_ui_readme_and_ci_use(self):
        self.assertIn("npm ci --ignore-scripts", (REPO / "ui" / "README.md").read_text(encoding="utf-8"))
        self.assertIn("node build.mjs", (REPO / "ui" / "README.md").read_text(encoding="utf-8"))
        self.assertIn("(cd ui && npm ci --ignore-scripts && node --test)", (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
        self.assertTrue((REPO / "ui" / "build.mjs").is_file())

    def test_the_page_it_keeps_is_the_one_the_build_writes(self):
        self.assertIn("writeFileSync(join(dist, 'progress.html')", (REPO / "ui" / "build.mjs").read_text(encoding="utf-8"))
        self.assertIn("path: ui/dist/progress.html", CODE)


class ArtifactOnlyTests(unittest.TestCase):
    def test_it_uploads_one_artifact_and_fails_when_the_page_is_missing(self):
        self.assertEqual(re.findall(r"uses: (actions/upload-artifact@v\d+)", CODE), ["actions/upload-artifact@v4"])
        self.assertIn("name: progress-page", CODE)
        self.assertIn("if-no-files-found: error", CODE)

    def test_every_action_it_uses_is_checkout_or_upload_artifact(self):
        used = set(re.findall(r"uses: ([\w./-]+)@", CODE))
        self.assertEqual(used, {"actions/checkout", "actions/upload-artifact"})

    def test_it_has_no_deploy_or_pages_step(self):
        for word in ("pages", "deploy", "publish", "gh-pages", "upload-pages-artifact", "configure-pages", "netlify", "vercel",
                     "cloudflare", "rsync", "scp ", "aws ", "s3 ", "git push", "gh release"):
            self.assertNotIn(word, CODE.lower(), word)

    def test_it_has_no_secret_and_no_token(self):
        self.assertNotRegex(CODE, r"secrets\.")
        self.assertNotRegex(CODE, r"GITHUB_TOKEN|github\.token|token:")
        self.assertNotIn("environment:", CODE)

    def test_it_can_only_read_the_repository(self):
        perms = block("permissions")
        self.assertEqual(re.findall(r"^  ([\w-]+): (\w+)$", perms, re.M), [("contents", "read")])
        self.assertNotIn("write", CODE.split("jobs:")[1])
        self.assertNotIn("id-token", CODE)

    def test_it_has_one_job_and_no_text_with_an_em_dash(self):
        self.assertEqual(re.findall(r"^  (\w[\w-]*):\n    name:", block("jobs"), re.M), ["build"])
        self.assertNotIn("\u2014", TEXT)


def publish_problems(code):
    """Every way a workflow text could publish, use a secret or write: empty means it is artifact only."""
    found = []
    for word in ("pages", "deploy", "publish", "gh-pages", "netlify", "vercel", "cloudflare", "rsync", "scp ", "aws ", "s3 ",
                 "git push", "gh release"):
        if word in code.lower():
            found.append(f"has '{word.strip()}'")
    if re.search(r"secrets\.|GITHUB_TOKEN|github\.token|token:|environment:", code):
        found.append("uses a secret, a token or an environment")
    if re.search(r"^\s+[\w-]+: write\s*$|id-token", code, re.M):
        found.append("asks for a write permission")
    if "pull_request" in code or "workflow_dispatch" in code:
        found.append("has a trigger other than push to main")
    return found


class PlantedFaultTests(unittest.TestCase):
    """The checks must fail on a workflow that publishes. They are run on changed copies of the text."""

    def test_the_real_workflow_has_no_problem(self):
        self.assertEqual(publish_problems(CODE), [])

    def test_a_pages_step_a_pull_request_trigger_a_secret_and_a_write_permission_are_found(self):
        for bad, word in ((CODE + "\n      - uses: actions/deploy-pages@v4\n", "pages"),
                          (CODE.replace("push:", "pull_request:\n  push:", 1), "trigger"),
                          (CODE + "\n        env:\n          T: ${{ secrets.PAGES_TOKEN }}\n", "secret"),
                          (CODE.replace("contents: read", "contents: write"), "write"),
                          (CODE + "\n      - run: git push origin HEAD:gh-pages\n", "git push")):
            self.assertTrue(any(word in p for p in publish_problems(bad)), (word, publish_problems(bad)))


if __name__ == "__main__":
    unittest.main()
