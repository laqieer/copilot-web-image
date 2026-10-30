from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcp import Client, StdioServerParameters
from mcp.types import TextContent
from PIL import Image
from playwright.sync_api import sync_playwright

import generate_image as generator
from mcp_server import mcp
import test_browser_flow


class MCPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / "result.png"

    async def test_structured_result_forwards_options_and_keeps_stdout_clean(self):
        stdout, stderr = StringIO(), StringIO()

        def generate(args, *, progress):
            print("Fixture progress", file=progress, flush=True)
            Image.new("RGB", (23, 17), "blue").save(args.output)
            return generator.validate_png(args.output)

        options = {
            "prompt": "--a blue robot",
            "output": str(self.output),
            "profile_dir": str(self.root / "profile"),
            "profile_name": "Default",
            "account_index": 1,
            "timeout": 30,
            "signin_timeout": 40,
            "diagnostics_dir": str(self.root / "diagnostics"),
        }
        with redirect_stdout(stdout), redirect_stderr(stderr), patch(
            "mcp_server.generator.run_generation", side_effect=generate
        ) as run:
            async with Client(mcp, raise_exceptions=True) as client:
                result = await client.call_tool("generate_image", options)
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content, {
            "path": str(self.output), "width": 23, "height": 17,
        })
        self.assertEqual(generator.validate_png(self.output), (23, 17))
        args = run.call_args.args[0]
        for name, value in options.items():
            with self.subTest(option=name):
                actual = getattr(args, name)
                self.assertEqual(str(actual) if isinstance(actual, Path) else actual, value)
        self.assertIs(run.call_args.kwargs["progress"], stderr)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Fixture progress", stderr.getvalue())

    async def test_invalid_arguments_are_tool_errors_and_leave_server_usable(self):
        existing = self.root / "existing.png"
        existing.write_bytes(b"existing")
        cases = (
            ({"prompt": " "}, "--prompt must not be blank"),
            ({"output": "relative.png"}, "output must be an absolute path"),
            ({"output": str(self.root / "image.jpg")}, "--output must end in .png"),
            ({"output": str(existing)}, "--output already exists"),
            ({"profile_name": "../profile"}, "--profile-name must be a directory name"),
            ({"profile_dir": "relative-profile"}, "profile_dir must be an absolute path"),
            ({"diagnostics_dir": "relative-diagnostics"}, "diagnostics_dir must be an absolute path"),
            ({"diagnostics_dir": "~/private-diagnostics"}, "diagnostics_dir must be an absolute path"),
            ({"timeout": 1801}, "1800"),
        )
        with patch("mcp_server.generator.run_generation") as run:
            async with Client(mcp, raise_exceptions=True) as client:
                for overrides, message in cases:
                    with self.subTest(overrides=overrides):
                        result = await client.call_tool("generate_image", {
                            "prompt": "test", "output": str(self.output), **overrides,
                        })
                        self.assertTrue(result.is_error)
                        self.assertIsNone(result.structured_content)
                        self.assertTrue(any(
                            message in block.text for block in result.content
                            if isinstance(block, TextContent)
                        ), result.content)
                self.assertEqual([tool.name for tool in (await client.list_tools()).tools], ["generate_image"])
        run.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"existing")
        self.assertFalse(self.output.exists())

    async def test_generation_failures_are_explicit_tool_errors(self):
        async with Client(mcp, raise_exceptions=True) as client:
            for error in (
                RuntimeError("Organizational security policy blocked access"),
                generator.PlaywrightTimeout("Fixture generation timed out"),
                OSError("Fixture output permission denied"),
            ):
                with self.subTest(error=error), patch(
                    "mcp_server.generator.run_generation", side_effect=error
                ):
                    result = await client.call_tool("generate_image", {
                        "prompt": "test", "output": str(self.output),
                    })
                    self.assertTrue(result.is_error)
                    self.assertIsNone(result.structured_content)
                    self.assertTrue(any(
                        str(error) in block.text for block in result.content
                        if isinstance(block, TextContent)
                    ), result.content)
        self.assertFalse(self.output.exists())

    async def test_requires_native_windows_before_opening_browser(self):
        with patch("generate_image.sys.platform", "linux"), patch("generate_image.sync_playwright") as start:
            async with Client(mcp, raise_exceptions=True) as client:
                result = await client.call_tool("generate_image", {
                    "prompt": "test", "output": str(self.output),
                })
        self.assertTrue(result.is_error)
        self.assertTrue(any(
            "native Windows Python and Microsoft Edge" in block.text
            for block in result.content if isinstance(block, TextContent)
        ), result.content)
        start.assert_not_called()

    async def test_legacy_stdio_round_trip_from_another_directory(self):
        server = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py").resolve())],
            cwd=str(self.root),
            env={"LOCALAPPDATA": os.environ["LOCALAPPDATA"]} if sys.platform == "win32" else None,
        )
        async with Client(server, mode="legacy") as client:
            listed = await client.list_tools()
            self.assertEqual([tool.name for tool in listed.tools], ["generate_image"])
            result = await client.call_tool("generate_image", {
                "prompt": " ", "output": str(self.output),
            })
            self.assertTrue(result.is_error)
            self.assertTrue(any(
                "--prompt must not be blank" in block.text
                for block in result.content if isinstance(block, TextContent)
            ), result.content)
            self.assertEqual([tool.name for tool in (await client.list_tools()).tools], ["generate_image"])
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(sys.platform == "win32", "Native Edge fixture requires Windows")
    async def test_native_edge_download_through_mcp(self):
        html, original = test_browser_flow.BrowserFlowTests.image_fixture()

        @contextmanager
        def fixture_playwright():
            with sync_playwright() as playwright:
                launch = playwright.chromium.launch_persistent_context

                def launch_fixture(*args, **kwargs):
                    kwargs["headless"] = True
                    context = launch(*args, **kwargs)
                    context.route("https://copilot-test.invalid/**", lambda route: route.fulfill(
                        content_type="text/html", body=html
                    ))
                    return context

                with patch.object(playwright.chromium, "launch_persistent_context", side_effect=launch_fixture):
                    yield playwright

        profile = self.root / "profile"
        with patch("generate_image.sync_playwright", fixture_playwright), patch(
            "generate_image.SITE", "https://copilot-test.invalid/"
        ):
            async with Client(mcp, raise_exceptions=True) as client:
                result = await client.call_tool("generate_image", {
                    "prompt": "test illustration",
                    "output": str(self.output),
                    "profile_dir": str(profile),
                    "diagnostics_dir": str(self.root / "diagnostics"),
                })
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.structured_content, {
            "path": str(self.output), "width": 37, "height": 29,
        })
        self.assertEqual(self.output.read_bytes(), original)
        self.assertFalse((profile / ".copilot-web-image.lock").exists())


if __name__ == "__main__":
    unittest.main()
