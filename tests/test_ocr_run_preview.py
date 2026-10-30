import ast
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


class OCRRunPreviewTests(unittest.TestCase):
    def test_scan_is_ready_immediately_after_ocr_click(self):
        source = (Path(__file__).resolve().parents[1] / 'keyword_app2_fixed318.py').read_text(
            encoding='utf-8')
        names = {
            '_ocr_normalize', '_ocr_select_options', '_ocr_options_for_column',
            '_update_ocr_editor_approvals', '_clear_ocr_results_on_upload',
            '_persist_ocr_candidate_edits', '_reset_ocr_analysis',
            '_prepare_ocr_candidate_analysis', 'render_image_ocr_tab',
        }
        functions = '\n\n'.join(
            ast.get_source_segment(source, node)
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name in names
        )
        script = '''
import logging
import sys
import unicodedata
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
import streamlit as st
from matching_engine import DB_COLS
from unmatched_collection import ocr_collection_text
from uuid import uuid4

DEFAULT_CATEGORIES = RISK_OPTIONS = DEFAULT_DETAIL_CRITERIA = []
DEFAULT_EVIDENCE_TYPES = DEFAULT_ALT_KEYWORDS = []
tab_specs = [('analysis', '스크립트 분석'), ('ocr_import', '이미지 OCR분석')]
st.session_state.setdefault('main_app_tabs', '이미지 OCR분석')
st.session_state.setdefault('kw_df', pd.DataFrame(columns=DB_COLS))
st.session_state.setdefault('ocr_call_count', 0)
st.session_state.setdefault('ocr_keyword_uploaded_files', [
    SimpleNamespace(name='sample.png', size=3, getvalue=lambda: b'img')
])

def _load_korean_ocr():
    return object()

def _collect_unmatched_text(*args, **kwargs):
    return True

def extract_text_lines(image_bytes, engine):
    st.session_state.ocr_call_count += 1
    return [{'text': '안티에이징', 'confidence': 0.98, 'bbox': [10, 20, 110, 45]}]

def make_image_preview_data(image_bytes):
    return 'data:image/jpeg;base64,', 200, 100

def render_text_selectable_image(*args, **kwargs):
    st.caption('selectable-overlay-ready')
    return True

'''
        # Exercise the real tab function without loading a model or uploading a file.
        render = '\nwith patch.object(st, "image"):\n    render_image_ocr_tab()'
        app = AppTest.from_string(script + functions + render, default_timeout=10).run()
        self.assertFalse(app.exception)
        self.assertNotIn('selectable-overlay-ready', [item.value for item in app.caption])

        app.button(key='ocr_keyword_run').click().run()

        self.assertFalse(app.exception)
        self.assertIn('selectable-overlay-ready', [item.value for item in app.caption])
        self.assertEqual(app.session_state['ocr_call_count'], 1)
        self.assertEqual(app.session_state['main_app_tabs'], '이미지 OCR분석')
        self.assertEqual(len(app.session_state['ocr_keyword_candidates']), 1)
        self.assertEqual(len(app.session_state['ocr_keyword_uploaded_files']), 1)

        version = app.session_state['ocr_keyword_editor_version']
        app.checkbox(key=f'ocr_keyword_select_all_{version}').uncheck().run()
        self.assertFalse(app.session_state['ocr_keyword_candidates'][0]['approved'])
        version = app.session_state['ocr_keyword_editor_version']
        app.checkbox(key=f'ocr_keyword_select_all_{version}').check().run()
        self.assertTrue(app.session_state['ocr_keyword_candidates'][0]['approved'])


if __name__ == '__main__':
    unittest.main()
