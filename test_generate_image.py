import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image

from generate_image import PlaywrightError, locked_profile, parse_arguments, run_generation, save_download


class Download:
    def __init__(self, path, error=None):
        self.path = path
        self.error = error

    def failure(self):
        return self.error

    def save_as(self, path):
        Path(path).write_bytes(self.path.read_bytes())


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        Image.new("RGB", (23, 17), "blue").save(self.source)
        self.output = self.root / "result.png"

    def test_saves_validated_original_bytes(self):
        self.assertEqual(save_download(Download(self.source), self.output), (23, 17))
        self.assertEqual(self.source.read_bytes(), self.output.read_bytes())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["result.png", "source.png"])

    def test_refuses_to_replace_existing_output(self):
        self.output.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            save_download(Download(self.source), self.output)
        self.assertEqual(self.output.read_bytes(), b"existing")

    def test_rejects_failed_download(self):
        with self.assertRaises(RuntimeError):
            save_download(Download(self.source, "network failure"), self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_non_image_download(self):
        self.source.write_bytes(b"<html>sign in</html>")
        with self.assertRaises(OSError):
            save_download(Download(self.source), self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_wrong_image_format(self):
        Image.new("RGB", (23, 17)).save(self.source, format="JPEG")
        with self.assertRaises(ValueError):
            save_download(Download(self.source), self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_truncated_image(self):
        self.source.write_bytes(self.source.read_bytes()[:45])
        with self.assertRaises((OSError, SyntaxError)):
            save_download(Download(self.source), self.output)
        self.assertFalse(self.output.exists())

    def test_profile_lock_is_exclusive_and_released_after_failure(self):
        profile = self.root / "profile"
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with locked_profile(profile):
                with self.assertRaisesRegex(RuntimeError, "already in use"):
                    with locked_profile(profile):
                        self.fail("Concurrent profile use was admitted")
                raise RuntimeError("test failure")
        with locked_profile(profile):
            self.assertTrue((profile / ".copilot-web-image.lock").exists())
        self.assertFalse((profile / ".copilot-web-image.lock").exists())

    def test_invalid_cli_inputs(self):
        for extra in (
            ["--prompt", " "],
            ["--output", str(self.root / "image.jpg")],
            ["--account-index", "0"],
            ["--timeout", "nan"],
            ["--timeout", "inf"],
            ["--profile-name", "../profile"],
        ):
            with self.subTest(extra=extra), self.assertRaises(SystemExit):
                parse_arguments(["--prompt", "test", "--output", str(self.output), *extra])

    def test_page_creation_failure_closes_browser_and_releases_profile(self):
        profile = self.root / "profile"
        args = parse_arguments([
            "--prompt", "test",
            "--output", str(self.output),
            "--profile-dir", str(profile),
            "--diagnostics-dir", str(self.root / "diagnostics"),
        ])
        with patch("generate_image.sys.platform", "win32"), patch("generate_image.sync_playwright") as start:
            context = start.return_value.__enter__.return_value.chromium.launch_persistent_context.return_value
            context.pages = []
            context.new_page.side_effect = PlaywrightError("Could not create a page")
            with self.assertRaisesRegex(PlaywrightError, "Could not create a page"):
                run_generation(args)
        context.close.assert_called_once()
        self.assertFalse((profile / ".copilot-web-image.lock").exists())


if __name__ == "__main__":
    unittest.main()
