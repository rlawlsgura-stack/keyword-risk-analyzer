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
            SupabaseRepository=SimpleNamespace(load_unmatched_terms=lambda: None, edit_own_keyword_request=lambda: None),
        )
        with patch.dict(sys.modules, {'repository': legacy_module}), \
                patch.object(sys, 'path', sys.path.copy()), patch('runpy.run_path') as run:
            exec(compile(entrypoint.read_bytes(), str(entrypoint), 'exec'),
                 {'__file__': str(entrypoint)})
            self.assertNotIn('repository', sys.modules)
            run.assert_called_once_with(str(root / 'keyword_app2_fixed306.py'), run_name='__main__')

    def app(self, user_id='owner', admin=False):
        source = (Path(__file__).resolve().parents[1] / 'keyword_app2_fixed306.py').read_text(
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
st.session_state.setdefault('messages', [
    {'id': 'q1', 'author_id': 'owner', 'author_role': 'user', 'is_initial': True, 'body': 'original'},
    {'id': 'q2', 'author_id': 'owner', 'author_role': 'user', 'body': 'second'},
    {'id': 'q3', 'author_id': 'owner', 'author_role': 'user', 'body': 'third'},
    {'id': 'a2', 'author_id': 'admin', 'author_role': 'admin', 'reply_to_id': 'q2', 'body': 'answer'},
    {'id': 'r2', 'author_id': 'owner', 'author_role': 'user', 'reply_to_id': 'a2', 'body': 'followup'},
])
KEYWORD_REQUEST_TYPE_LABELS = {
    'risk_grade_adjustment': 'risk', 'review_criteria_change': 'criteria',
    'new_keyword_registration': 'new',
}
KEYWORD_REQUEST_STATUSES = ('대기', '검토중', '처리완료')
def is_admin():
    return st.session_state.admin_mode
def format_keyword_request_time(value):
    return str(value)
class SupabaseRepository:
    def load_keyword_request_messages(self, request_id, token):
        return st.session_state.messages
    def mutate_own_keyword_inquiry(self, request_id, inquiry_id, action, token, body=None, request_type=None):
        st.session_state.calls.append((action, inquiry_id, body, request_type, token))
        target = next(message for message in st.session_state.messages if message['id'] == inquiry_id)
        if action == 'edit':
            target['body'] = body
            if target.get('is_initial'):
                st.session_state.test_row.update(request_detail=body, request_type=request_type)
        else:
            deleted = {inquiry_id}
            while True:
                descendants = {m['id'] for m in st.session_state.messages if m.get('reply_to_id') in deleted}
                if descendants.issubset(deleted):
                    break
                deleted.update(descendants)
            st.session_state.messages = [m for m in st.session_state.messages if m['id'] not in deleted]
            if target.get('is_initial'):
                st.session_state.test_row['request_detail'] = ''
    def delete_keyword_request(self, request_id, token):
        st.session_state.calls.append(('delete_request', request_id, token))
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
        app.selectbox(key='keyword_inquiry_edit_type_q1').select(
            'review_criteria_change')
        app.text_area(key='keyword_inquiry_edit_body_q1').set_value(
            'edited')
        next(button for button in app.button if button.label == 'Q01 수정 저장').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['calls'], [
            ('edit', 'q1', 'edited', 'review_criteria_change', 'owner-token'),
        ])
        self.assertEqual(app.session_state['test_row']['request_detail'], 'edited')
        self.assertEqual(app.session_state['test_row']['request_type'], 'review_criteria_change')

    def test_each_later_inquiry_and_followup_can_be_edited_without_touching_siblings(self):
        for inquiry_id, label in [('q2', 'Q02'), ('q3', 'Q03'), ('r2', 'Q02-R1')]:
            with self.subTest(inquiry_id=inquiry_id):
                app = self.app()
                before = {m['id']: m['body'] for m in app.session_state['messages']}
                app.text_area(key=f'keyword_inquiry_edit_body_{inquiry_id}').set_value('edited')
                next(button for button in app.button if button.label == f'{label} 수정 저장').click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['calls'], [('edit', inquiry_id, 'edited', None, 'owner-token')])
                after = {m['id']: m['body'] for m in app.session_state['messages']}
                self.assertEqual(after, {**before, inquiry_id: 'edited'})
                self.assertEqual(app.session_state['test_row']['request_detail'], 'original')

    def test_receipt_and_keyword_fields_have_separate_titles(self):
        app = self.app()
        fields = [item.value for item in app.markdown]
        self.assertIn('**접수번호:** KR-00000000', fields)
        self.assertIn('**키워드no.:** B101', fields)
        self.assertIn('**키워드명:** keyword', fields)

    def test_empty_later_inquiry_is_rejected_without_saving(self):
        app = self.app()
        app.text_area(key='keyword_inquiry_edit_body_q2').set_value('  ')
        next(button for button in app.button if button.label == 'Q02 수정 저장').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['calls'], [])
        self.assertIn('문의 내용을 입력하세요.', [item.value for item in app.error])

    def test_owner_delete_needs_confirmation_and_cancel_keeps_request(self):
        app = self.app()
        app.button(key='keyword_inquiry_delete_q2').click().run()
        self.assertEqual(app.session_state['calls'], [])
        app.button(key='keyword_inquiry_delete_cancel_q2').click().run()
        self.assertEqual(app.session_state['calls'], [])
        app.button(key='keyword_inquiry_delete_q2').click().run()
        app.button(key='keyword_inquiry_delete_submit_q2').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['calls'], [
            ('delete', 'q2', None, None, 'owner-token'),
        ])
        self.assertEqual({m['id'] for m in app.session_state['messages']}, {'q1', 'q3'})
        self.assertEqual(app.session_state['test_row']['request_detail'], 'original')

    def test_deleting_initial_inquiry_preserves_the_receipt_and_later_inquiries(self):
        app = self.app()
        app.button(key='keyword_inquiry_delete_q1').click().run()
        app.button(key='keyword_inquiry_delete_submit_q1').click().run()
        self.assertFalse(app.exception)
        self.assertEqual({m['id'] for m in app.session_state['messages']}, {'q2', 'q3', 'a2', 'r2'})
        self.assertEqual(app.session_state['test_row']['request_detail'], '')
        self.assertEqual(app.session_state['test_row']['id'], '00000000-0000-0000-0000-000000000001')

    def test_other_user_has_no_edit_or_delete_controls_and_admin_keeps_delete(self):
        for admin in (False, True):
            with self.subTest(admin=admin):
                app = self.app(user_id='other', admin=admin)
                self.assertFalse(app.exception)
                self.assertFalse(any(item.key.startswith('keyword_inquiry_edit_')
                                     for item in app.text_area))
                self.assertFalse(any(button.key.startswith('keyword_inquiry_delete_') for button in app.button))
                self.assertEqual(any(button.label == '접수건 전체 삭제' for button in app.button), admin)
                self.assertEqual(app.session_state['calls'], [])


if __name__ == '__main__':
    unittest.main()
