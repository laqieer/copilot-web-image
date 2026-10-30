# Copilot Web Image

A standalone Windows command-line tool that generates and downloads PNG images
through the normal Microsoft 365 Copilot website using Playwright and Edge.
It is independent of any game or application project and is not an MCP server.
It is a community tool, not affiliated with or supported by Microsoft.

## Requirements

- Windows, Microsoft Edge and Python 3.13 or newer.
- A Microsoft 365 account with access to Copilot Cowork and image generation.
- Permission from your organization to use browser automation.
- The website's English interface. Its controls can change without notice.

## Install

From the source directory in PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

The tool uses the installed Edge browser; no additional browser download,
Microsoft API token, MCP installation or administrator access is required.

## Generate an image

```powershell
.\generate-image.cmd --prompt "A friendly blue robot watering a seedling" --output "$HOME\Downloads\robot.png"
```

The script opens the website, selects Cowork, submits the prompt, waits for an
image artifact and downloads it through the artifact viewer's Download menu.
It verifies the PNG before saving and never overwrites an existing output.
The output can be used by any project; generated images are not part of this
source repository.

Complete account selection, sign-in or MFA in Edge when requested. If Windows
offers several accounts, you may explicitly select one by its current position:

```powershell
.\generate-image.cmd --account-index 1 --prompt "A watercolor landscape" --output landscape.png
```

The position is one-based and can change. Omit this option to select the
account manually. No account name or email is required in the source code.

Run `.\generate-image.cmd --help` for generation and sign-in timeouts and
diagnostic options. A website change or policy denial produces a nonzero exit
status rather than a success-shaped placeholder image.

## Browser profiles and privacy

By default, the tool uses its own persistent Edge profile under
`%LOCALAPPDATA%\copilot-web-image\browser-profile`. This keeps authentication
state outside the source checkout. It does not read or export credentials or
tokens, change device-management settings or bypass Conditional Access.
The browser profile itself contains private authentication and account data.

To select an existing Edge profile instead, close every browser instance using
that profile, then pass its user-data directory and profile directory name:

```powershell
.\generate-image.cmd --profile-dir "$env:LOCALAPPDATA\Microsoft\Edge\User Data" --profile-name Default --prompt "A mountain lake" --output lake.png
```

Existing/default browser profiles may be locked or unsuitable for Playwright.
Use the dedicated profile if Edge refuses to launch; do not copy credentials
or disable security controls to work around an organizational restriction.

Concurrent script runs must use different browser profiles. After an interrupted
run, a stale `.copilot-web-image.lock` can remain in the selected profile
directory. Remove it only after confirming that the old script and its browser
have stopped.

On failure, diagnostic screenshots are saved under
`%LOCALAPPDATA%\copilot-web-image\diagnostics`. Screenshots can contain private
account or application information; do not publish them without reviewing them.

Never commit browser profiles, environments, compiled Python caches, generated
images, diagnostics, credentials or personal account details. The included
ignore rules cover the default local directories, but custom output/profile
paths must also be kept outside Git. Only source, tests and documentation belong
in this repository. Do not copy runtime directories into a source checkout.
Commit authorship should use a generic identity when personal metadata must not
be recorded; GitHub repository ownership and push activity remain visible to
people who can access the repository.

## Tests

```powershell
.\venv\Scripts\python.exe -m unittest -v test_generate_image test_browser_flow
```

The browser test runs native Edge headlessly against an intercepted local
fixture, not against Microsoft services. It covers delayed editor readiness,
an image preview appearing before the downloadable artifact, and a byte-exact
PNG download. Unit tests cover invalid CLI arguments, profile locking, failed
and corrupt downloads, PNG validation, and refusal to overwrite files.
CI does not sign in to a Microsoft account or spend image-generation quota.
