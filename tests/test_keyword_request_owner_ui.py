import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from streamlit.testing.v1 import AppTest


class KeywordRequestOwnerUITests(unittest.TestCase):
    def test_cloud_entrypoint_reloads_a_repository_without_owner_edit(self):
        root = Path(__file__).resolve().parents[1]
        entrypoint = root / 'streamlit_cloud' / 'app.py'
        legacy_module = SimpleNamespace(
            __file__=str(root / 'repository.py'),
            SupabaseRepository=SimpleNamespace(load_unmatched_terms=lambda: None),
        )
        with patch.dict(sys.modules, {'repository': legacy_module}), \
                patch.object(sys, 'path', sys.path.copy()), patch('runpy.run_path') as run:
            exec(compile(entrypoint.read_bytes(), str(entrypoint), 'exec'),
                 {'__file__': str(entrypoint)})
            self.assertNotIn('repository', sys.modules)
            run.assert_called_once_with(str(root / 'keyword_app2_fixed300.py'), run_name='__main__')

    def app(self, user_id='owner', admin=False):
        source = (Path(__file__).resolve().parents[1] / 'keyword_app2_fixed300.py').read_text(
            encoding='utf-8')
        dialog = next(node for node in ast.parse(source).body
                      if isinstance(node, ast.FunctionDef)
                      and node.name == 'render_keyword_request_dialog')
        script = '''
import streamlit as st
from repository import StorageError
st.session_state.setdefault('calls', [])
st.session_state.setdefault('test_row', {
    'id': '00000000-0000-0000-0000-000000000001', 'requester_id': 'owner',
    'requester_email': 'owner@example.test', 'request_type': 'risk_grade_adjustment',
    'request_detail': 'original', 'kwd_no': 'B101', 'keyword_name': 'keyword',
})
KEYWORD_REQUEST_TYPE_LABELS = {
    'risk_grade_adjustment': 'risk', 'review_criteria_change': 'criteria',
    'new_keyword_registration': 'new',
}
KEYWORD_REQUEST_STATUSES = ('pending', 'reviewing', 'done')
def is_admin():
    return st.session_state.admin_mode
def format_keyword_request_time(value):
    return str(value)
class SupabaseRepository:
    def load_keyword_request_messages(self, request_id, token):
        return []
    def edit_own_keyword_request(self, request_id, request_type, detail, token):
        st.session_state.calls.append(('edit', request_id, request_type, detail, token))
        st.session_state.test_row.update(request_type=request_type, request_detail=detail)
    def delete_keyword_request(self, request_id, token):
        st.session_state.calls.append(('delete', request_id, token))
'''
        script += '\n' + ast.get_source_segment(source, dialog)
        script += '\nrender_keyword_request_dialog(st.session_state.test_row, "owner-token")'
        script_path = Path(__file__).with_name(f'_owner_ui_{uuid4().hex}.py')
        script_path.write_text(script, encoding='utf-8')
        self.addCleanup(script_path.unlink, missing_ok=True)
        app = AppTest.from_file(str(script_path), default_timeout=10)
        app.session_state['cloud_user'] = {'id': user_id, 'email': user_id + '@example.test'}
        app.session_state['admin_mode'] = admin
        return app.run()

    def test_owner_can_edit_existing_request_and_refresh_history(self):
        app = self.app()
        self.assertFalse(app.exception)
        app.selectbox(key='keyword_request_edit_type_00000000-0000-0000-0000-000000000001').select(
            'review_criteria_change')
        app.text_area(key='keyword_request_edit_detail_00000000-0000-0000-0000-000000000001').set_value(
            'edited')
        next(button for button in app.button if button.label == '수정 저장').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['calls'], [
            ('edit', '00000000-0000-0000-0000-000000000001',
             'review_criteria_change', 'edited', 'owner-token'),
        ])
        self.assertEqual(app.session_state['keyword_request_history_epoch'], 1)

    def test_owner_delete_needs_confirmation_and_cancel_keeps_request(self):
        app = self.app()
        next(button for button in app.button if button.label == '문의 삭제').click().run()
        self.assertEqual(app.session_state['calls'], [])
        next(button for button in app.button if button.label == '취소').click().run()
        self.assertEqual(app.session_state['calls'], [])
        next(button for button in app.button if button.label == '문의 삭제').click().run()
        next(button for button in app.button if button.label == '영구 삭제 확인').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['calls'], [
            ('delete', '00000000-0000-0000-0000-000000000001', 'owner-token'),
        ])
        self.assertEqual(app.session_state['keyword_request_history_epoch'], 1)

    def test_other_user_has_no_edit_or_delete_controls_and_admin_keeps_delete(self):
        for admin in (False, True):
            with self.subTest(admin=admin):
                app = self.app(user_id='other', admin=admin)
                self.assertFalse(app.exception)
                self.assertFalse(any(item.key.startswith('keyword_request_edit_')
                                     for item in app.text_area))
                self.assertEqual(any(button.label == '문의 삭제' for button in app.button), admin)
                self.assertEqual(app.session_state['calls'], [])


if __name__ == '__main__':
    unittest.main()
