from __future__ import annotations

import json
import math
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
SAMPLE = SKILL_ROOT / "sample" / "achievement-knowledge"
BUILDER = SCRIPTS / "builder.py"
sys.path.insert(0, str(SCRIPTS))

from engine.prompts import build_jobs  # noqa: E402
from engine.render import safe_path  # noqa: E402
from engine.strategy import AUTO_ROUTES, PRODUCT_TYPES, SALES_STYLES, build_strategy  # noqa: E402
from engine.validate import validate_script  # noqa: E402
from builder import _next_action, _template_script  # noqa: E402


class CompleteBuilderTest(unittest.TestCase):
    def test_all_fifteen_auto_routes(self):
        self.assertEqual(len(PRODUCT_TYPES) * 3, 15)
        for product, goals in AUTO_ROUTES.items():
            for goal, (expected_style, expected_overlays) in goals.items():
                strategy = build_strategy(product, goal)
                self.assertEqual(strategy["primary_style"], expected_style)
                self.assertEqual(strategy["overlays"], expected_overlays)
                beats = strategy["required_beats"]
                if strategy["product_reveal_by"] is not None:
                    reveal = beats.index("product_reveal")
                    latest = max(0, math.ceil(len(beats) * strategy["product_reveal_by"]) - 1)
                    self.assertLessEqual(reveal, latest, (product, goal, beats))
                if "recommendation" in expected_overlays:
                    self.assertIn("recommendation", beats)
                if "desire" in expected_overlays:
                    self.assertIn("bright_future", beats)
                if "testimonial" in expected_overlays:
                    self.assertIn("experience", beats)
                if "objection" in expected_overlays:
                    self.assertIn("objection", beats)
                if "proof_stack" in expected_overlays:
                    self.assertIn("proof_stack", beats)

    def test_template_respects_requested_page_count_and_product_cta(self):
        for product in PRODUCT_TYPES:
            for goal in ("awareness", "trial", "conversion"):
                strategy = build_strategy(product, goal)
                strategy.update({
                    "next_action": _next_action(product, goal),
                    "hook_question": "未解決疑問",
                    "payoff_mirror": "冒頭と結末の反転",
                    "achievement_ceiling": "確認可能な成功まで",
                    "cta_basis": "一次資料",
                })
                script = _template_script("試験", strategy)
                self.assertEqual(max(panel["page"] for panel in script["panels"]), strategy["pages"])
                self.assertEqual(
                    {panel["page"] for panel in script["panels"]},
                    set(range(1, strategy["pages"] + 1)),
                )
        self.assertEqual(_next_action("story_ip", "trial"), "試し読みする")
        self.assertEqual(_next_action("story_ip", "conversion"), "購入する")

    def test_all_nine_styles_are_selectable(self):
        self.assertEqual(len(SALES_STYLES), 9)
        for style in SALES_STYLES:
            strategy = build_strategy("knowledge", "conversion", style, decision_maker_separate=True)
            self.assertEqual(strategy["primary_style"], style)
            self.assertEqual(strategy["selection_mode"], "manual")

    def test_auto_achievement_journey_for_separate_decision_maker_across_products(self):
        for product in PRODUCT_TYPES:
            strategy = build_strategy(
                product, "conversion", decision_maker_separate=True,
            )
            self.assertEqual(strategy["primary_style"], "achievement_journey", product)
            self.assertEqual(strategy["product_reveal_by"], 0.5)
            self.assertGreaterEqual(len(strategy["route_candidates"]), 2)
            self.assertTrue(strategy["route_candidates"][0]["recommended"])

    def test_achievement_journey_template_has_three_roles_and_references(self):
        strategy = build_strategy(
            "service", "conversion", decision_maker_separate=True,
        )
        strategy.update({
            "next_action": "申し込む",
            "hook_question": "未解決疑問",
            "payoff_mirror": "冒頭と結末の反転",
            "achievement_ceiling": "確認可能な成功まで",
            "cta_basis": "一次資料",
            "user": "利用者", "peer": "仲間", "decision_maker": "決裁者",
            "bright_future": "具体的な未来",
        })
        script = _template_script("試験", strategy)
        self.assertEqual(set(script["characters"]), {"user", "peer", "decision_maker"})
        peer_panel = next(panel for panel in script["panels"] if panel["section"] == "peer_prompt")
        decision_panel = next(panel for panel in script["panels"] if panel["section"] == "decision_maker_pitch")
        self.assertIn("peer", peer_panel["characters"])
        self.assertIn("decision_maker", decision_panel["characters"])
        job_ids = {job["id"] for job in build_jobs(script)}
        self.assertTrue({"character-user", "character-peer", "character-decision_maker"} <= job_ids)

    def test_generic_achievement_journey_sample_passes_strict_gate(self):
        script = json.loads((SAMPLE / "script.json").read_text(encoding="utf-8"))
        issues = validate_script(script, strict=True)
        self.assertEqual([(issue.code, issue.message) for issue in issues], [])
        jobs = build_jobs(script)
        self.assertEqual(sum(job["kind"] == "character" for job in jobs), 3)
        self.assertEqual(sum(job["kind"] == "expression" for job in jobs), 3)
        self.assertGreaterEqual(sum(job["kind"] in {"character", "expression", "action"} for job in jobs), 3)
        self.assertEqual(sum(job["kind"] == "panel" for job in jobs), 10)

    def test_marketing_placeholders_are_rejected(self):
        strategy = build_strategy("story_ip", "conversion")
        strategy.update({
            "next_action": "購入する",
            "hook_question": "未解決疑問",
            "payoff_mirror": "冒頭と結末の反転",
            "achievement_ceiling": "確認可能な成功まで",
            "cta_basis": "一次資料",
        })
        script = _template_script("試験", strategy)
        issues = validate_script(script, strict=True)
        codes = {issue.code for issue in issues}
        self.assertIn("marketing.target.segment.placeholder", codes)
        self.assertIn("marketing.transformation.after_experience.placeholder", codes)
        self.assertIn("marketing.route.presented", codes)

    def test_marketing_route_must_match_story_strategy(self):
        script = json.loads((SAMPLE / "script.json").read_text(encoding="utf-8"))
        script["meta"]["marketing"]["route_decision"]["selected"] = "testimonial"
        issues = validate_script(script, strict=True)
        self.assertIn("marketing.route.mismatch", {issue.code for issue in issues})

    def test_separate_roles_require_separate_decision_flag(self):
        script = json.loads((SAMPLE / "script.json").read_text(encoding="utf-8"))
        script["meta"]["strategy"]["decision_maker_separate"] = False
        issues = validate_script(script, strict=True)
        self.assertIn("marketing.roles.separate", {issue.code for issue in issues})

    def test_third_party_marks_are_rejected(self):
        script = json.loads((SAMPLE / "script.json").read_text(encoding="utf-8"))
        script["meta"]["rights"]["third_party_names"] = ["第三者サービスA"]
        issues = validate_script(script, strict=True)
        self.assertIn("rights.third_party_names", {issue.code for issue in issues})

    def test_unreviewed_rights_are_rejected(self):
        script = json.loads((SAMPLE / "script.json").read_text(encoding="utf-8"))
        script["meta"]["rights"]["reviewed"] = False
        issues = validate_script(script, strict=True)
        self.assertIn("rights.reviewed", {issue.code for issue in issues})

    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                safe_path(pathlib.Path(tmp), "../outside.png")
            with self.assertRaises(ValueError):
                safe_path(pathlib.Path(tmp), "/tmp/outside.png")

    def test_missing_images_do_not_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "job"
            shutil.copytree(SAMPLE, root)
            result = subprocess.run(
                [sys.executable, str(BUILDER), "finalize", str(root)],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("作画素材", result.stderr)

    def test_demo_end_to_end_and_public_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "job"
            shutil.copytree(SAMPLE, root)
            subprocess.run(
                [sys.executable, str(BUILDER), "demo-assets", str(root)],
                text=True, capture_output=True, check=True,
            )
            public = subprocess.run(
                [sys.executable, str(BUILDER), "finalize", str(root)],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(public.returncode, 0)
            self.assertIn("デモ素材", public.stderr)
            subprocess.run(
                [sys.executable, str(BUILDER), "finalize", str(root), "--allow-demo"],
                text=True, capture_output=True, check=True,
            )
            html = (root / "output" / "lp.html").read_text(encoding="utf-8")
            self.assertIn("data:image/png;base64,", html)
            self.assertNotIn("/Users/", html)
            self.assertTrue((root / "output" / "note_vertical.png").is_file())
            self.assertEqual(len(list((root / "output" / "pages").glob("page_*.png"))), 10)
            self.assertEqual(len(list((root / "output" / "social").glob("card_*.png"))), 10)
            package = root / "output" / "manga-lp-delivery.zip"
            with zipfile.ZipFile(package) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("output/lp.html", archive.namelist())
            manifest = json.loads((root / "reports" / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["demo"])
            current = subprocess.run(
                [sys.executable, str(BUILDER), "status", str(root)],
                text=True, capture_output=True, check=True,
            )
            self.assertTrue(json.loads(current.stdout)["finalized"])
            script_path = root / "script.json"
            changed = json.loads(script_path.read_text(encoding="utf-8"))
            changed["meta"]["title"] += " 改稿"
            script_path.write_text(json.dumps(changed, ensure_ascii=False, indent=2), encoding="utf-8")
            stale = subprocess.run(
                [sys.executable, str(BUILDER), "status", str(root)],
                text=True, capture_output=True, check=True,
            )
            self.assertFalse(json.loads(stale.stdout)["finalized"])

    def test_distribution_has_no_personal_residue(self):
        blocked = (
            "星海" + "アリス",
            "/Users/" + "happyhappylife0307",
            "2nd" + "-Brain-i",
            "軍" + "配",
            "Gun" + "bai",
            "pro-marketing-" + "director",
            "明" + "鏡",
        )
        text_suffixes = {".md", ".py", ".json", ".yaml", ".yml", ".txt"}
        for path in SKILL_ROOT.rglob("*"):
            if path.is_file() and path.suffix.lower() in text_suffixes:
                text = path.read_text(encoding="utf-8", errors="ignore")
                for needle in blocked:
                    self.assertNotIn(needle, text, str(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
