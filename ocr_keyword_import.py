"""Small adapter between PaddleOCR results and editable keyword candidates."""
from __future__ import annotations

import io
import logging
import math
import os
from threading import Lock


_ocr_engine = None
_ocr_engine_lock = Lock()


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


def load_korean_ocr():
    """Create one PaddleOCR pipeline per app process and reuse it across reruns."""
    global _ocr_engine
    if _ocr_engine is None:
        with _ocr_engine_lock:
            if _ocr_engine is None:
                # Repeated OCR calls can revisit PaddleX in the same process.
                # Disable PaddleX's import-time repo initialization; the OCR
                # pipeline initializes only the components it actually needs.
                os.environ["PADDLE_PDX_EAGER_INIT"] = "False"
                os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
                from paddleocr import PaddleOCR

                _ocr_engine = PaddleOCR(
                    lang="korean",
                    ocr_version="PP-OCRv5",
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
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
