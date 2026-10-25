"""Small adapter between PaddleOCR results and editable keyword candidates."""
from __future__ import annotations

import io


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
