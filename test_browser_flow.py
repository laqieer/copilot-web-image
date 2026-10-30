import base64
from io import BytesIO
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from playwright.sync_api import sync_playwright

from generate_image import generate, parse_arguments


class BrowserFlowTests(unittest.TestCase):
    @staticmethod
    def image_fixture():
        image = BytesIO()
        Image.new("RGB", (37, 29), "green").save(image, format="PNG")
        original = image.getvalue()
        data_url = "data:image/png;base64," + base64.b64encode(original).decode()
        html = """
            <label><input type="radio" name="mode" aria-label="Cowork" checked>
              <span>Cowork</span><span aria-hidden="true">Cowork</span>
            </label>
            <textarea aria-label="Message Copilot"></textarea>
            <button id="send" aria-label="Send" disabled>Send</button>
            <p id="submitted"></p>
            <div id="output"></div>
            <script>
              const output = document.getElementById("output");
              let ready = false;
              setTimeout(() => { ready = true; }, 1100);
              document.querySelector("textarea").oninput = event => {
                if (ready) {
                  document.getElementById("send").disabled = false;
                } else {
                  event.target.value = "";
                }
              };
              document.getElementById("send").onclick = () => {
                document.getElementById("submitted").textContent =
                  document.querySelector("textarea").value;
                output.innerHTML = '<img alt="Generating preview" src="DATA_URL">';
                setTimeout(() => {
                  const artifact = document.createElement("button");
                  artifact.setAttribute("aria-label", "Open fixture.png, Image");
                  artifact.onclick = () => {
                    output.innerHTML = '<img alt="Image: fixture.png" src="DATA_URL">'
                      + '<button aria-label="More actions" id="more">More actions</button>';
                    document.getElementById("more").onclick = () => {
                      const link = document.createElement("a");
                      link.role = "menuitem";
                      link.textContent = "Download";
                      link.download = "fixture.png";
                      link.href = "DATA_URL";
                      output.appendChild(link);
                    };
                  };
                  output.appendChild(artifact);
                }, 300);
              };
            </script>
        """.replace("DATA_URL", data_url)
        return html, original

    def test_waits_for_artifact_and_downloads_original(self):
        html, original = self.image_fixture()
        with tempfile.TemporaryDirectory() as temp, sync_playwright() as playwright:
            output = Path(temp) / "download.png"
            args = parse_arguments(["--prompt", "test illustration", "--output", str(output)])
            browser = playwright.chromium.launch(
                channel="msedge", headless=True, chromium_sandbox=True
            )
            try:
                page = browser.new_page(accept_downloads=True)
                page.route("https://copilot-test.invalid/**", lambda route: route.fulfill(
                    content_type="text/html", body=html
                ))
                with patch("generate_image.SITE", "https://copilot-test.invalid/"):
                    self.assertEqual(generate(page, args), (37, 29))
                self.assertEqual(output.read_bytes(), original)
                self.assertEqual(page.locator("#submitted").inner_text(), "test illustration")
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
