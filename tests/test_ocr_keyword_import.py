import io
import unittest

import numpy as np
from PIL import Image

from ocr_keyword_import import extract_text_lines, make_image_preview_data


class FakePage:
    json = {
        "res": {
            "rec_texts": ["  안티 에이징  ", "복사할 문장"],
            "rec_scores": [0.98, 0.91],
            "rec_polys": np.asarray([
                [[10, 20], [110, 20], [110, 45], [10, 45]],
                [[25, 60], [125, 60], [125, 85], [25, 85]],
            ]),
        }
    }


class FakeOCREngine:
    def predict(self, image):
        assert image.shape == (100, 200, 3)
        return [FakePage()]


class OCRTextGeometryTests(unittest.TestCase):
    def setUp(self):
        buffer = io.BytesIO()
        Image.new("RGB", (200, 100), "white").save(buffer, format="PNG")
        self.image_bytes = buffer.getvalue()

    def test_extracts_copyable_text_and_corresponding_boxes(self):
        rows = extract_text_lines(self.image_bytes, FakeOCREngine())

        self.assertEqual([row["text"] for row in rows], ["안티 에이징", "복사할 문장"])
        self.assertEqual(rows[0]["bbox"], [10.0, 20.0, 110.0, 45.0])
        self.assertEqual(rows[1]["bbox"], [25.0, 60.0, 125.0, 85.0])

    def test_preview_keeps_original_coordinate_dimensions(self):
        data_url, width, height = make_image_preview_data(self.image_bytes, max_side=50)

        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        self.assertEqual((width, height), (200, 100))
        encoded = data_url.split(",", 1)[1]
        import base64

        with Image.open(io.BytesIO(base64.b64decode(encoded))) as preview:
            self.assertEqual(preview.size, (50, 25))


if __name__ == "__main__":
    unittest.main()
