"""Small adapter between PaddleOCR results and editable keyword candidates."""
from __future__ import annotations

import io
import os
from threading import Lock


_ocr_engine = None
_ocr_engine_lock = Lock()


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

    image = np.asarray(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    rows = []
    for page in ocr_engine.predict(image):
        payload = getattr(page, "json", {})
        if callable(payload):
            payload = payload()
        payload = payload.get("res", payload) if isinstance(payload, dict) else {}
        texts = payload.get("rec_texts", [])
        scores = payload.get("rec_scores", [])
        for index, text in enumerate(texts):
            text = " ".join(str(text).split())
            if text:
                score = float(scores[index]) if index < len(scores) else 0.0
                rows.append({"text": text, "confidence": score})
    return rows
