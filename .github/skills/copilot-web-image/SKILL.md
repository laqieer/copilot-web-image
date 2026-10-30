---
name: copilot-web-image
description: Generate and download a verified PNG through the Microsoft 365 Copilot website using this project's Windows Python and Edge CLI. Use when asked to create an image, illustration, or visual asset with Copilot, not to search for existing images.
---

# Copilot Web Image

Use the existing browser generator, not an API, a placeholder, or a hand-drawn
replacement. This workflow requires native Windows, Microsoft Edge, Python 3.13
or newer, an eligible Microsoft 365 account, and organizational permission for
browser automation. If those requirements are unavailable, explain the blocker.
Do not try to bypass an access policy or automate credentials or MFA.

## Locate and prepare the tool

The source checkout is three directories above this skill's directory:
`.github/skills/copilot-web-image/../../..`. Resolve that location from the
skill's base directory, not from the agent's current working directory.
It must contain `generate-image.cmd`, `generate_image.py`, and `requirements.txt`.
Keep the skill with its checkout; copying `SKILL.md` alone is not an installation.

Read the checkout's `README.md` for prerequisites and privacy guidance. If its
`venv\Scripts\python.exe` is missing, create the environment from that checkout
in PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use the installed Edge browser. Do not download a Playwright browser or request
an API token.

## Generate the requested image

1. Turn the user's request into a descriptive image prompt without adding private
   information. Choose an absolute, new `.png` output path, preferably outside
   the source checkout. If no destination was given, use a unique filename in
   the user's Downloads directory.
2. Invoke the checkout's `generate-image.cmd` in native Windows PowerShell,
   passing the prompt and output as separate arguments. For example, with
   `$toolHome` set to the resolved checkout:

   ```powershell
   & "$toolHome\generate-image.cmd" --prompt 'A friendly blue robot watering a seedling' --output "$HOME\Downloads\robot.png"
   ```

3. Allow the user to complete account selection, sign-in, and MFA in the visible
   Edge window. Only pass `--account-index` if the user explicitly selected an
   offered account position. Do not guess an identity.
4. Wait for the process to finish. Generation defaults to 240 seconds and
   sign-in to 180 seconds; `--timeout` and `--signin-timeout` accept positive
   values up to 1800 seconds. A slow generation is not proof of failure.
5. Report success only when the command exits with zero and reports a saved,
   verified PNG. Return its absolute path and reported dimensions. When the
   agent can display local images, show the saved file, not a website preview.

If the command fails, report its actual error. Never fabricate an image, silently
switch providers, overwrite an existing output, or claim generation succeeded.
Do not repeatedly retry an organizational policy denial.

## Protect browser state

Use the default dedicated browser profile unless the user requests another.
Never read or export tokens, cookies, or stored credentials. Concurrent runs
must use separate profiles; never remove a profile lock until the old process
and browser are confirmed stopped.

Keep profiles, generated images, diagnostics, and environments out of Git.
Diagnostic screenshots can contain account or application details: review them
and obtain permission before sharing. Do not upload them as routine proof.
