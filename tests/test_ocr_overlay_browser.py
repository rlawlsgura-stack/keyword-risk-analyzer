"""Check the actual OCR overlay layout without extra browser dependencies."""
import html
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from PIL import Image

import ocr_keyword_import as ocr


class OCROverlayBrowserTests(unittest.TestCase):
    def test_text_selection_fits_ocr_boxes_after_preview_resize(self):
        self.check_overlay((2000, 1000), [
            {"text": "긴 한글 문장과 영문 Long OCR text " * 4,
             "bbox": [100, 100, 600, 150]},
            {"text": "짧음", "bbox": [1600, 700, 1950, 750]},
        ])

    def test_header_selection_stays_on_one_line_in_tall_advertisement(self):
        self.check_overlay((846, 3000), [
            {"text": "SEBUM AND PORE CARE", "bbox": [43, 36, 350, 64]},
            {"text": "IMPROVEMENT EFFECT", "bbox": [507, 36, 800, 64]},
        ])

    def check_overlay(self, image_size, lines):
        browser = shutil.which("google-chrome") or shutil.which("chromium")
        if not browser:
            for root, relative in [
                ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
                ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
            ]:
                candidate = Path(os.environ.get(root, "")) / relative
                if candidate.is_file():
                    browser = str(candidate)
                    break
        if not browser:
            self.skipTest("Chrome or Chromium is required for the overlay layout check")

        buffer = io.BytesIO()
        Image.new("RGB", image_size, "white").save(buffer, format="PNG")
        image, width, height = ocr.make_image_preview_data(buffer.getvalue())
        data = json.dumps({
            "image": image, "width": width, "height": height,
            "lines": lines,
        }, ensure_ascii=False)
        renderer = ocr._TEXT_SELECTABLE_IMAGE_JS.replace(
            "export default function", "function renderOverlay", 1)
        page = """<!doctype html><meta charset="utf-8">
<style>body { margin: 0; }</style>
<template id="component"><style>CSS</style><div class="ocr-image-root"><div class="ocr-image-stage"></div></div></template>
<div id="host"></div>
<pre id="result">pending</pre>
<script>window.onerror = message => document.querySelector('#result').textContent = JSON.stringify([message]);</script>
<script>
RENDERER
const host = document.querySelector('#host');
const root = host.attachShadow({mode: 'open'});
root.appendChild(document.querySelector('#component').content.cloneNode(true));
const data = DATA;
renderOverlay({ data, parentElement: root });
const errors = [];
const frame = () => new Promise(resolve => setTimeout(resolve, 50));
(async () => {
  const img = root.querySelector('img');
  await new Promise(resolve => img.complete ? resolve() : img.addEventListener('load', resolve));
  for (const width of [800, 240, 100, 1800]) {
    host.style.width = `${width}px`;
    await frame(); await frame();
    const image = img.getBoundingClientRect();
    if (Math.abs(image.width - Math.min(width, img.naturalWidth)) > 1 || image.height < 1)
      errors.push(`Invalid preview size at ${width}: ${image.width} x ${image.height}`);
    [...root.querySelectorAll('.ocr-text-line')].forEach((line, index) => {
      const box = data.lines[index].bbox;
      const rect = line.getBoundingClientRect();
      const expected = [image.x + box[0] / data.width * image.width,
                        image.y + box[1] / data.height * image.height,
                        (box[2] - box[0]) / data.width * image.width,
                        (box[3] - box[1]) / data.height * image.height];
      [rect.x, rect.y, rect.width, rect.height].forEach((value, axis) => {
        if (Math.abs(value - expected[axis]) > 1)
          errors.push(`Box ${index}, viewport ${width}, axis ${axis}: ${value} != ${expected[axis]}`);
      });
      const range = document.createRange();
      range.selectNodeContents(line);
      const text = range.getBoundingClientRect();
      if (text.left < rect.left - 1 || text.right > rect.right + 1)
        errors.push(`Text overflows box ${index} at ${width}: ${text.width} > ${rect.width}`);
      const selection = window.getSelection();
      selection.removeAllRanges(); selection.addRange(range);
      if (selection.toString() !== data.lines[index].text)
        errors.push(`Copy lost text in box ${index} at ${width}`);
    });
  }
  document.querySelector('#result').textContent = JSON.stringify(errors);
})().catch(error => document.querySelector('#result').textContent = JSON.stringify([String(error)]));
</script>""".replace("CSS", ocr._TEXT_SELECTABLE_IMAGE_CSS).replace(
            "RENDERER", renderer).replace("DATA", data)
        with tempfile.TemporaryDirectory(prefix="ocr-overlay-") as directory:
            document = Path(directory) / "overlay.html"
            document.write_text(page, encoding="utf-8")
            result = subprocess.run([
                browser, "--headless=new", "--disable-gpu", "--no-first-run",
                f"--user-data-dir={directory}/profile", "--dump-dom",
                "--virtual-time-budget=3000", document.as_uri(),
            ], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        match = re.search(r'<pre id="result">(.*?)</pre>', result.stdout, re.DOTALL)
        self.assertIsNotNone(match, result.stdout[-2000:])
        self.assertNotEqual(match[1], "pending", "Browser layout check did not finish")
        self.assertEqual(json.loads(html.unescape(match[1])), [])


if __name__ == "__main__":
    unittest.main()
