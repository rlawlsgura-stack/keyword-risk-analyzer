"""Small adapter between PaddleOCR results and editable keyword candidates."""
from __future__ import annotations

import io
import logging
import math
import os
from threading import Lock


_ocr_engine = None
_ocr_engine_lock = Lock()


OCR_OVERLAY_REVISION = 2
_TEXT_SELECTABLE_IMAGE = None
_TEXT_SELECTABLE_IMAGE_ERROR = ""
_TEXT_SELECTABLE_IMAGE_CSS = """
.ocr-image-root { width: 100%; min-width: 0; }
.ocr-image-stage { position: relative; width: 100%; max-width: 100%; line-height: 0; container-type: inline-size; }
.ocr-image-stage img { display: block; width: 100%; height: auto; }
.ocr-text-layer { position: absolute; inset: 0; overflow: hidden; }
.ocr-text-line {
  position: absolute; display: flex; align-items: center;
  overflow: hidden; white-space: pre;
  color: transparent; cursor: text; user-select: text; -webkit-user-select: text;
  line-height: 1; font-family: Arial, sans-serif;
}
.ocr-text-content { display: block; flex: none; width: max-content; transform-origin: left center; }
.ocr-text-line:hover { background: rgba(55, 115, 255, 0.16); outline: 1px solid rgba(55, 115, 255, 0.38); }
.ocr-text-content::selection { color: #111; background: rgba(80, 145, 255, 0.72); }
"""
_TEXT_SELECTABLE_IMAGE_JS = """
export default function (component) {
  const { data, parentElement } = component;
  const stage = parentElement.querySelector('.ocr-image-stage');
  if (!stage || !data) return;

  stage._ocrResizeObserver?.disconnect();
  stage.replaceChildren();
  const imageWidth = Math.max(1, Number(data.width) || 1);
  const imageHeight = Math.max(1, Number(data.height) || 1);
  stage.style.width = `${imageWidth}px`;
  const image = document.createElement('img');
  image.onload = () => { stage.style.width = `${image.naturalWidth}px`; };
  image.src = data.image;
  image.alt = data.alt || 'OCR 분석 이미지';
  image.draggable = false;
  stage.appendChild(image);

  const layer = document.createElement('div');
  layer.className = 'ocr-text-layer';
  for (const line of data.lines || []) {
    const box = line.bbox;
    if (!box || box.length !== 4) continue;
    const left = Math.max(0, Math.min(imageWidth, Number(box[0])));
    const top = Math.max(0, Math.min(imageHeight, Number(box[1])));
    const right = Math.max(0, Math.min(imageWidth, Number(box[2])));
    const bottom = Math.max(0, Math.min(imageHeight, Number(box[3])));
    if (![left, top, right, bottom].every(Number.isFinite) || right <= left || bottom <= top) continue;
    const span = document.createElement('span');
    span.className = 'ocr-text-line';
    const content = document.createElement('span');
    content.className = 'ocr-text-content';
    content.textContent = line.text || '';
    span.appendChild(content);
    span.title = line.text || '';
    span.style.left = `${100 * left / imageWidth}%`;
    span.style.top = `${100 * top / imageHeight}%`;
    span.style.width = `${100 * (right - left) / imageWidth}%`;
    span.style.height = `${100 * (bottom - top) / imageHeight}%`;
    const fontScale = 100 * (bottom - top) * 0.78 / imageWidth;
    span.style.fontSize = `${fontScale}cqw`;
    layer.appendChild(span);
  }
  stage.appendChild(layer);
  const fitText = () => {
    for (const line of layer.children) {
      const content = line.firstElementChild;
      content.style.transform = '';
      const textWidth = content.getBoundingClientRect().width;
      if (textWidth > 0) {
        content.style.transform = `scaleX(${line.getBoundingClientRect().width / textWidth})`;
      }
    }
  };
  const observer = new ResizeObserver(fitText);
  stage._ocrResizeObserver = observer;
  observer.observe(stage);
  fitText();
  return () => { observer.disconnect(); image.onload = null; };
}
"""


def _get_text_selectable_image_component():
    """Register the optional UI component only when the OCR preview is opened."""
    global _TEXT_SELECTABLE_IMAGE, _TEXT_SELECTABLE_IMAGE_ERROR
    if _TEXT_SELECTABLE_IMAGE is not None:
        return _TEXT_SELECTABLE_IMAGE
    try:
        import streamlit as st

        _TEXT_SELECTABLE_IMAGE = st.components.v2.component(
            f"kra_ocr_text_selectable_image_v{OCR_OVERLAY_REVISION}",
            html="<div class='ocr-image-root'><div class='ocr-image-stage'></div></div>",
            css=_TEXT_SELECTABLE_IMAGE_CSS,
            js=_TEXT_SELECTABLE_IMAGE_JS,
        )
        _TEXT_SELECTABLE_IMAGE_ERROR = ""
        return _TEXT_SELECTABLE_IMAGE
    except Exception as exc:
        _TEXT_SELECTABLE_IMAGE_ERROR = f"{type(exc).__name__}: {exc}"
        logging.exception("Could not register the selectable OCR image component")
        return None


def make_image_preview_data(image_bytes: bytes, max_side: int = 1600) -> tuple[str, int, int]:
    """Make a compact display copy without changing the OCR source image."""
    import base64
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGB")
    width, height = image.size
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}", width, height


def render_text_selectable_image(image_data: str, width: int, height: int,
                                lines: list[dict[str, object]], *, alt: str, key: str):
    """Show an image with a transparent, browser-selectable OCR text layer."""
    image_width = max(1, int(width))
    image_height = max(1, int(height))
    safe_lines = []
    for line in lines:
        text = str(line.get("text", "")).strip()
        bbox = line.get("bbox")
        if not text or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            coords = [float(value) for value in bbox]
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(value) for value in coords):
            continue
        coords = [
            max(0.0, min(float(image_width), coords[0])),
            max(0.0, min(float(image_height), coords[1])),
            max(0.0, min(float(image_width), coords[2])),
            max(0.0, min(float(image_height), coords[3])),
        ]
        if coords[2] <= coords[0] or coords[3] <= coords[1]:
            continue
        safe_lines.append({"text": text, "bbox": coords})
    component = _get_text_selectable_image_component()
    if component is None:
        return False
    try:
        component(
            key=f"{key}_v{OCR_OVERLAY_REVISION}",
            data={"image": image_data, "width": image_width,
                  "height": image_height, "lines": safe_lines, "alt": alt},
            width="stretch",
            height="content",
        )
        return True
    except Exception:
        logging.exception("Could not render the selectable OCR image component")
        return False


def load_korean_ocr():
    """Create one PaddleOCR pipeline per app process and reuse it across reruns."""
    global _ocr_engine
    if _ocr_engine is None:
        with _ocr_engine_lock:
            if _ocr_engine is None:
                # Streamlit reruns can revisit PaddleX in the same process.
                # Disable PaddleX's import-time repo initialization; the OCR
                # pipeline initializes only the components it actually needs.
                os.environ["PADDLE_PDX_EAGER_INIT"] = "False"
                os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
                from paddleocr import PaddleOCR

                _ocr_engine = PaddleOCR(
                    lang="korean",
                    ocr_version="PP-OCRv5",
                    device="cpu",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
    return _ocr_engine


def extract_text_lines(image_bytes: bytes, ocr_engine) -> list[dict[str, object]]:
    """Run a PaddleOCR v3 engine on an uploaded image and return text/confidence pairs."""
    import numpy as np
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as source:
        rgb_image = source.convert("RGB")
        image_width, image_height = rgb_image.size
        image = np.asarray(rgb_image)
    rows = []
    for page in ocr_engine.predict(image):
        payload = getattr(page, "json", {})
        if callable(payload):
            payload = payload()
        payload = payload.get("res", payload) if isinstance(payload, dict) else {}
        texts = payload.get("rec_texts", [])
        scores = payload.get("rec_scores", [])
        polygons = payload.get("rec_polys")
        if polygons is None:
            polygons = payload.get("dt_polys")
        if polygons is None:
            polygons = []
        boxes = payload.get("rec_boxes")
        if boxes is None:
            boxes = []
        for index, text in enumerate(texts):
            text = " ".join(str(text).split())
            if text:
                score = float(scores[index]) if index < len(scores) else 0.0
                bbox = None
                if index < len(polygons):
                    points = np.asarray(polygons[index], dtype=float).reshape(-1, 2)
                    if points.size and np.isfinite(points).all():
                        bbox = [float(points[:, 0].min()), float(points[:, 1].min()),
                                float(points[:, 0].max()), float(points[:, 1].max())]
                if bbox is None and index < len(boxes):
                    box = np.asarray(boxes[index], dtype=float).reshape(-1)
                    if box.size >= 4 and np.isfinite(box[:4]).all():
                        bbox = [float(box[0]), float(box[1]), float(box[2]), float(box[3])]
                if bbox:
                    bbox = [max(0.0, min(float(image_width if i % 2 == 0 else image_height), value))
                            for i, value in enumerate(bbox)]
                rows.append({"text": text, "confidence": score, "bbox": bbox})
    return rows
