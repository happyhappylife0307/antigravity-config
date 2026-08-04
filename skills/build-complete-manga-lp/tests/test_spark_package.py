from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SparkPackageTest(unittest.TestCase):
    def test_root_skill_metadata(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: build-complete-manga-lp", text)
        self.assertIn("Gemini Spark", text)

    def test_no_old_environment_residue(self):
        blocked = (
            "Cod" + "ex",
            "Open" + "AI",
            "agents/" + "openai",
            "チャレンジ" + "型",
            '"chall' + 'enge"',
        )
        suffixes = {".md", ".py", ".json", ".yaml", ".yml", ".txt"}
        for path in ROOT.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                text = path.read_text(encoding="utf-8", errors="ignore")
                for needle in blocked:
                    self.assertNotIn(needle, text, str(path))

    def test_upload_contains_only_plain_text_types(self):
        allowed = {
            ".txt", ".md", ".rst", ".rtf", ".tex", ".log", ".py", ".sh",
            ".json", ".yaml", ".yml", ".csv", ".toml", ".xml", ".env",
            ".sql", ".html", ".css", ".svg",
        }
        for path in ROOT.rglob("*"):
            if path.is_file():
                self.assertIn(path.suffix.lower(), allowed, str(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
