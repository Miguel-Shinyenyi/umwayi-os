"""L9, part 1: the `video` line of units.yaml and `video_gate`.

Videos are budget spend (the PR story and video rule, D1 and D2). Without a video line videos are off. The gate is a pure function and the
tests give it the numbers, so no clock or file decides a result. Planted faults: a video over the cap, mode off, a cap of 0, the owner's off
for one pull request, and an estimate that does not fit the day.
"""
import unittest

from umwayi import units

TODAY = "2026-11-24"


def load(body=""):
    u, p = units.check_text("version: 1\n" + body, TODAY)
    assert not p, [x.message for x in p]
    return u


ON = "video:\n  mode: on\n  per_video: 50\n  per_day: 100\n"


class ParseTests(unittest.TestCase):
    def test_no_video_line_means_none_and_validate_says_nothing_about_videos(self):
        self.assertIsNone(load().video)

    def test_a_video_line_loads_and_shows_in_the_change_state(self):
        u = load(ON)
        self.assertEqual((u.video.mode, u.video.per_video, u.video.per_day), ("on", 50, 100))
        self.assertEqual({k: v for k, v in u.state().items() if k.startswith("video")},
                         {"video.mode": "on", "video.per_video": "50", "video.per_day": "100"})

    def test_planted_faults_each_is_a_problem(self):
        for label, body in {
            "a missing key": "video:\n  mode: on\n  per_video: 50\n",
            "an unknown key": ON + "  note: x\n",
            "a bad mode": ON.replace("mode: on", "mode: maybe"),
            "a negative cap": ON.replace("per_video: 50", "per_video: -1"),
            "a text cap": ON.replace("per_day: 100", "per_day: lots"),
            "not a mapping": "video: 3\n",
        }.items():
            with self.subTest(label):
                u, p = units.check_text("version: 1\n" + body, TODAY)
                self.assertIsNone(u)
                self.assertTrue(p)


class GateTests(unittest.TestCase):
    def test_a_video_within_both_caps_is_yes_and_a_free_local_render_costs_zero(self):
        u = load(ON)
        self.assertEqual(units.video_gate(u, 30, 20), ("yes", "within_cap"))
        self.assertEqual(units.video_gate(u, 50, 50), ("yes", "within_cap"))  # exactly at both caps
        self.assertEqual(units.video_gate(u, 0, 0), ("yes", "within_cap"))

    def test_planted_fault_a_video_over_the_cap_is_refused(self):
        u = load(ON)
        self.assertEqual(units.video_gate(u, 51, 0), ("no", "over_per_video"))
        self.assertEqual(units.video_gate(u, 30, 71), ("no", "over_per_day"))
        self.assertEqual(units.video_gate(u, 50, 51), ("no", "over_per_day"))

    def test_without_a_video_line_or_with_mode_off_or_a_zero_cap_there_is_no_video_and_it_says_why(self):
        for u in (load(), load(ON.replace("mode: on", "mode: off")), load(ON.replace("per_video: 50", "per_video: 0")),
                  load(ON.replace("per_day: 100", "per_day: 0"))):
            self.assertEqual(units.video_gate(u, 0, 0), ("no", "video_off"))

    def test_the_owners_off_for_one_pull_request_wins_over_everything(self):
        self.assertEqual(units.video_gate(load(ON), 0, 0, pr_off=True), ("no", "owner_off"))
        self.assertEqual(units.video_gate(load(), 0, 0, pr_off=True), ("no", "owner_off"))

    def test_the_estimate_is_checked_before_anything_is_spent_and_the_gate_spends_nothing(self):
        u = load(ON)
        before = (u.video, u.state())
        units.video_gate(u, 30, 20)
        self.assertEqual((u.video, u.state()), before)


if __name__ == "__main__":
    unittest.main()
