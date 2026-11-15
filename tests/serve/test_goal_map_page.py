"""W38b: `umwayi serve --page ui/dist/goal-map.html` serves the goal map page under the same check as the live view
(W6.R2.3 as the owner changed it on Nov 15): a regular file of at most 2.5 MB, nothing on the way a link, and its SHA-256
equal to its own entry of build.json beside it, goalMapPage for a file named goal-map.html and page for every other name.

Through the backend without a socket, and once with the real server and the page of the repository. Standard library only.
"""
import hashlib
import json
import re

from tests.serve.support import REPO, InProc, RootCase, Server, make_root, rules_text

GM = b"<!doctype html><title>goal map</title>"
INDEX = b"<!doctype html><title>live view</title>"


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Case(RootCase):
    def setUp(self):
        super().setUp()
        self.root = make_root(self.tmp / "root", rules=rules_text())
        self.dist = self.tmp / "dist"
        self.dist.mkdir()

    def write(self, build, gm=GM, index=INDEX):
        (self.dist / "goal-map.html").write_bytes(gm)
        (self.dist / "index.html").write_bytes(index)
        (self.dist / "build.json").write_text(json.dumps(build))
        return self.dist / "goal-map.html"


class GoalMapPageTests(Case):
    def test_the_goal_map_page_is_served_when_it_matches_goal_map_page(self):
        path = self.write({"page": sha(INDEX), "goalMapPage": sha(GM)})
        r = InProc(self.root, page=path).get("/")
        self.assertEqual((r.status, r.raw), (200, GM))
        self.assertTrue(r.headers["content-type"].startswith("text/html"))
        self.assertIn("frame-ancestors 'none'", r.headers["content-security-policy"])

    def test_it_is_checked_against_goal_map_page_and_never_against_page(self):
        path = self.write({"page": sha(GM), "goalMapPage": sha(b"other")})  # the hash of page would match
        r = InProc(self.root, page=path).get("/")
        self.assertEqual((r.status, r.word), (503, "page"))
        path = self.write({"page": sha(GM)})  # no goalMapPage at all
        self.assertEqual(InProc(self.root, page=path).get("/").status, 503)

    def test_a_changed_byte_after_the_start_gives_503_page(self):
        path = self.write({"page": sha(INDEX), "goalMapPage": sha(GM)})
        web = InProc(self.root, page=path)
        self.assertEqual(web.get("/").status, 200)
        path.write_bytes(GM + b" ")
        self.assertEqual((web.get("/").status, web.get("/").word), (503, "page"))

    def test_the_live_view_is_still_checked_against_page_only(self):
        self.write({"page": sha(INDEX), "goalMapPage": sha(INDEX)})
        self.assertEqual(InProc(self.root, page=self.dist / "index.html").get("/").status, 200)
        (self.dist / "build.json").write_text(json.dumps({"page": sha(b"x"), "goalMapPage": sha(INDEX)}))
        self.assertEqual(InProc(self.root, page=self.dist / "index.html").get("/").status, 503)

    def test_another_name_is_checked_against_page_as_before(self):
        other = self.dist / "copy.html"
        other.write_bytes(GM)
        (self.dist / "build.json").write_text(json.dumps({"goalMapPage": sha(GM)}))
        self.assertEqual(InProc(self.root, page=other).get("/").status, 503)
        (self.dist / "build.json").write_text(json.dumps({"page": sha(GM)}))
        self.assertEqual(InProc(self.root, page=other).get("/").status, 200)

    def test_a_link_named_goal_map_html_is_not_served(self):
        real = self.dist / "real.html"
        real.write_bytes(GM)
        (self.dist / "goal-map.html").symlink_to(real)
        (self.dist / "build.json").write_text(json.dumps({"goalMapPage": sha(GM), "page": sha(GM)}))
        self.assertEqual(InProc(self.root, page=self.dist / "goal-map.html").get("/").status, 503)

    def test_serving_the_goal_map_page_adds_no_route(self):
        path = self.write({"page": sha(INDEX), "goalMapPage": sha(GM)})
        web = InProc(self.root, page=path)
        for p in ("/goal-map", "/goal-map.html", "/index.html", "/ui/dist/goal-map.html"):
            self.assertEqual(web.get(p).status, 404, p)
        self.assertEqual(web.get("/v1/goal-map").code, 0)


class RepoPageTests(RootCase):
    def test_the_built_goal_map_page_of_the_repo_is_served_by_the_real_server(self):
        self.root = make_root(self.tmp / "root", rules=rules_text())
        page = REPO / "ui" / "dist" / "goal-map.html"
        with Server(self.root, ["--page", str(page)]) as s:
            self.assertNotIn("page not served", s.first_lines[0])
            st, h, body = s.request("GET", "/", token=None)
            self.assertEqual(st, 200)
            self.assertEqual(sha(body), json.loads((REPO / "ui" / "dist" / "build.json").read_text())["goalMapPage"])
            csp = re.search(rb'http-equiv="Content-Security-Policy" content="([^"]*)"', body).group(1).decode()
            self.assertTrue(csp.endswith("; connect-src 'self'"), csp)
            st, h, body = s.request("GET", "/v1/goal-map")
            self.assertEqual(st, 200)
            self.assertEqual(json.loads(body)["data"]["version"], 1)
