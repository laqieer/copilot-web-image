# Copilot Web Image

A standalone Windows command-line tool that generates and downloads PNG images
through the normal Microsoft 365 Copilot website using Playwright and Edge.
It is independent of any game or application project. Use the CLI directly,
through the included Agent Skill, or through the optional local MCP server.
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

The CLI uses the installed Edge browser; no additional browser download,
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

## Agent Skill

The project includes an Agent Skill at
`.github/skills/copilot-web-image/SKILL.md`. Compatible agents discover it when
working in this checkout. In an existing Copilot CLI session, run `/skills reload`
and `/skills info copilot-web-image` to check discovery, then request, for example:

```text
Use /copilot-web-image to generate a watercolor mountain lake in my Downloads folder.
```

The skill invokes the same CLI and requires the same Windows environment,
account access, and interactive sign-in. Keep it with the source checkout;
copying only `SKILL.md` to another project does not install the generator.
It does not grant blanket shell permissions or bypass organizational policies.

## MCP server

The optional stdio MCP server exposes one tool, `generate_image`, backed by the
same browser flow, profile lock, PNG verification, and no-overwrite checks as the
CLI. It opens no network listener and does not require Microsoft API credentials.
Install its additional dependencies in the existing Windows environment:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
```

From the source checkout, register it with a native Windows Copilot CLI:

```powershell
$python = (Resolve-Path .\venv\Scripts\python.exe).Path
$server = (Resolve-Path .\mcp_server.py).Path
copilot mcp add copilot-web-image --tools generate_image --timeout 900000 --env "LOCALAPPDATA=$env:LOCALAPPDATA" -- "$python" "$server"
```

This saves machine-specific paths in the client's local configuration, not in
Git. Other stdio MCP clients can launch the same Python executable with the
absolute server path as its argument. Pass the Windows `LOCALAPPDATA` environment
variable if the client does not inherit it. Do not launch it with Linux/WSL Python.

Call `generate_image` with `prompt` and an absolute Windows `output` path ending
in `.png`. Optional arguments are `profile_dir`, `profile_name`, `account_index`,
`timeout`, `signin_timeout`, and `diagnostics_dir`, matching the CLI options.
Any supplied profile or diagnostics path must also be absolute. For example:

```json
{
  "prompt": "A friendly blue robot watering a seedling",
  "output": "C:\\path\\to\\outputs\\robot.png"
}
```

Successful calls return structured `path`, `width`, and `height` values. Failed
calls are MCP tool errors, not successful placeholder results. Progress and
diagnostics go to stderr, leaving stdout for the MCP protocol. No browser state
or images are automatically sent back to the client.

The Windows/Edge, account, permission, and manual sign-in requirements still
apply. The example client timeout is 15 minutes; increase it if you raise the
generation/sign-in timeouts. Cancelling a client call does not immediately
interrupt a synchronous browser operation: let it finish and release its profile
lock before retrying. Do not share private diagnostic screenshots without review.

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

With the optional MCP dependencies installed, include its protocol and browser
fixture tests:

```powershell
.\venv\Scripts\python.exe -m unittest -v test_generate_image test_browser_flow test_mcp_server
```

MCP tests cover stdio discovery from another working directory, argument errors,
structured results, progress routing, and the same intercepted native Edge
download through an MCP tool call. Platform-independent MCP tests also run on
Linux; native Edge fixture coverage requires Windows.
