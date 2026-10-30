"""Generate and download a PNG using the normal Microsoft 365 Copilot website.

Run on Windows with Microsoft Edge installed:
    python generate_image.py --prompt "A blue robot tending a garden" --output robot.png

The default browser profile is dedicated to this script. On first use, select
your account in the browser and complete any required authentication yourself.
--account-index optionally selects a numbered account already offered by Windows.
--profile-dir and --profile-name can select another Edge profile, but that
profile must not be open elsewhere. No credentials or tokens are read or exported.
"""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

from PIL import Image, UnidentifiedImageError
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


SITE = "https://m365.cloud.microsoft/chat"
ACCOUNT_NAME = re.compile(r"Sign in with .* work or school account\.")
POLICY_ERRORS = re.compile(
    r"security policy is preventing access|requiring token protection|"
    r"requires the device requesting access to be managed",
    re.I,
)


def data_directory():
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "copilot-web-image"
    return Path.home() / ".local" / "share" / "copilot-web-image"


def positive_seconds(value):
    seconds = float(value)
    if not 0 < seconds <= 1800:
        raise argparse.ArgumentTypeError("must be greater than zero and at most 1800")
    return seconds


def positive_index(value):
    index = int(value)
    if index < 1:
        raise argparse.ArgumentTypeError("must be a one-based account number")
    return index


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="Image description sent to Copilot")
    parser.add_argument("--output", required=True, type=Path, help="New .png file; never overwritten")
    parser.add_argument("--profile-dir", type=Path, default=data_directory() / "browser-profile")
    parser.add_argument("--profile-name", help="Edge profile directory name, such as Default")
    parser.add_argument("--account-index", type=positive_index, help="Select an offered account (1-based)")
    parser.add_argument("--timeout", type=positive_seconds, default=240, help="Generation timeout in seconds")
    parser.add_argument("--signin-timeout", type=positive_seconds, default=180, help="Interactive sign-in timeout")
    parser.add_argument("--diagnostics-dir", type=Path, default=data_directory() / "diagnostics")
    args = parser.parse_args(argv)
    if not args.prompt.strip():
        parser.error("--prompt must not be blank")
    args.output = args.output.expanduser().absolute()
    if args.output.suffix.lower() != ".png":
        parser.error("--output must end in .png")
    if args.output.exists():
        parser.error("--output already exists; choose a new filename")
    args.profile_dir = args.profile_dir.expanduser().absolute()
    if args.profile_name and (
        args.profile_name in (".", "..") or re.search(r"[/\\]", args.profile_name)
    ):
        parser.error("--profile-name must be a directory name, not a path")
    return args


def validate_png(path):
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ValueError("The website download is not a PNG image")
            dimensions = image.size
            image.verify()
        with Image.open(path) as image:
            image.load()
    except SyntaxError:
        raise ValueError("The website download is a damaged PNG image") from None
    return dimensions


def save_download(download, output):
    failure = download.failure()
    if failure:
        raise RuntimeError("The browser reported a failed image download")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".copilot-download-", dir=output.parent) as temp:
        pending = Path(temp) / "image.png"
        download.save_as(str(pending))
        dimensions = validate_png(pending)
        with output.open("xb") as target:
            try:
                with pending.open("rb") as source:
                    shutil.copyfileobj(source, target)
            except OSError:
                target.close()
                output.unlink()
                raise
    return dimensions


@contextmanager
def locked_profile(profile):
    profile.mkdir(parents=True, exist_ok=True)
    lock = profile / ".copilot-web-image.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise RuntimeError(
            "This browser profile is already in use by the script. "
            "After a crash, confirm its browser has stopped before removing "
            ".copilot-web-image.lock from the profile directory."
        ) from None
    try:
        handle.write(str(os.getpid()))
        handle.close()
        yield
    finally:
        handle.close()
        lock.unlink()


def sign_in(page, args):
    deadline = time.monotonic() + args.signin_timeout
    selection_done = False
    announced = False
    editor = page.get_by_role("textbox", name=re.compile(r"^Message (Copilot|Cowork)$"))
    while time.monotonic() < deadline:
        if page.get_by_text(POLICY_ERRORS).count():
            raise RuntimeError("Microsoft blocked access with an organizational security policy")
        if editor.count() == 1 and editor.is_visible():
            return editor
        accounts = page.get_by_role("button", name=ACCOUNT_NAME)
        if not selection_done and accounts.count():
            if args.account_index:
                if args.account_index > accounts.count():
                    raise ValueError("--account-index exceeds the number of offered accounts")
                accounts.nth(args.account_index - 1).click()
                selection_done = True
            elif accounts.count() == 1:
                accounts.click()
                selection_done = True
        if not announced:
            print("Complete any account selection, sign-in or MFA in Edge.", flush=True)
            announced = True
        page.wait_for_timeout(500)
    raise RuntimeError("Sign-in did not finish before --signin-timeout")


def generate(page, args):
    page.goto(SITE, wait_until="domcontentloaded", timeout=60000)
    sign_in(page, args)
    print("Signed in. Selecting image-generation mode.", flush=True)
    # Wait for the mode switch, not just the transient editor during app startup.
    cowork = page.get_by_role("radio", name="Cowork", exact=True)
    cowork.wait_for(state="visible", timeout=60000)
    cowork.check()
    editor = page.get_by_role("textbox", name=re.compile(r"^Message (Copilot|Cowork)$"))
    print("Writing prompt.", flush=True)
    send = page.get_by_role("button", name="Send", exact=True)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        # Startup can replace the editor before its input handler is attached.
        editor.fill(args.prompt.strip(), timeout=5000)
        page.wait_for_timeout(500)
        if send.is_visible() and send.is_enabled():
            send.click()
            break
    else:
        raise RuntimeError("The website never enabled its Send button")
    print("Prompt submitted. Waiting for the generated image.", flush=True)
    artifact = page.get_by_role("button", name=re.compile(r"^Open .+, Image$"))
    artifact.wait_for(state="visible", timeout=args.timeout * 1000)
    artifact.click()
    images = page.get_by_role("img", name=re.compile(r"^Image: .+"))
    images.wait_for(state="visible", timeout=30000)
    # The artifact viewer is after the conversation's unrelated More actions menu.
    page.get_by_role("button", name="More actions", exact=True).last.click()
    download = page.get_by_role("menuitem", name="Download", exact=True)
    with page.expect_download(timeout=60000) as event:
        download.click()
    return save_download(event.value, args.output)


def main(argv=None):
    args = parse_arguments(argv)
    if sys.platform != "win32":
        print("Run this script with native Windows Python and Microsoft Edge.", file=sys.stderr)
        return 2
    page = None
    try:
        with locked_profile(args.profile_dir), sync_playwright() as playwright:
            browser_args = []
            if args.profile_name:
                browser_args.append("--profile-directory=" + args.profile_name)
            context = playwright.chromium.launch_persistent_context(
                str(args.profile_dir),
                channel="msedge",
                chromium_sandbox=True,
                headless=False,
                accept_downloads=True,
                viewport={"width": 1280, "height": 850},
                args=browser_args,
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                width, height = generate(page, args)
            except (PlaywrightError, OSError, ValueError, RuntimeError, UnidentifiedImageError):
                args.diagnostics_dir.mkdir(parents=True, exist_ok=True)
                screenshot = args.diagnostics_dir / ("failure-" + time.strftime("%Y%m%d-%H%M%S") + ".png")
                if not page.is_closed():
                    try:
                        page.screenshot(path=str(screenshot), timeout=5000)
                    except PlaywrightError:
                        print("Could not capture a diagnostic screenshot.", file=sys.stderr)
                    else:
                        print("Failure screenshot (may contain account/UI details): " + str(screenshot), file=sys.stderr)
                raise
            finally:
                context.close()
    except PlaywrightTimeout as error:
        print("Timed out waiting for a website control, generation or download. See diagnostics.", file=sys.stderr)
        print(str(error).splitlines()[0], file=sys.stderr)
        return 1
    except PlaywrightError as error:
        print(
            "Browser automation failed. Ensure Edge is installed and this profile "
            "is not open elsewhere; inspect the browser or diagnostic screenshot.",
            file=sys.stderr,
        )
        print(str(error).splitlines()[0], file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, UnidentifiedImageError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Saved verified PNG ({width}x{height}): {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
