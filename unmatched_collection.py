"""Small helpers for account-independent unmatched-term collection."""
import math


OCR_COLLECTION_MIN_CONFIDENCE = 0.60


def ocr_collection_text(file_results):
    """Keep original line multiplicity and exclude OCR confidence below 60%."""
    texts = []
    for result in file_results:
        if result.get('error'):
            continue
        for line in result.get('lines', []):
            try:
                score = float(line.get('confidence', 0))
            except (TypeError, ValueError):
                continue
            if math.isfinite(score) and score >= OCR_COLLECTION_MIN_CONFIDENCE:
                text = str(line.get('text', '')).strip()
                if text:
                    texts.append(text)
    return '\n'.join(texts)
