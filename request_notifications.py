"""Best-effort administrator email notifications for keyword requests."""
import html
import os

import requests


class NotificationConfigurationError(RuntimeError):
    pass


class NotificationDeliveryError(RuntimeError):
    pass


def is_notification_configured(env=None):
    env = os.environ if env is None else env
    return all(env.get(name, '').strip() for name in (
        'RESEND_API_KEY',
        'KEYWORD_REQUEST_ADMIN_EMAIL',
        'KEYWORD_REQUEST_FROM_EMAIL',
    ))


def send_keyword_request_email(request_row, *, env=None, post=requests.post):
    """Send one request notification through Resend; never expose provider details."""
    env = os.environ if env is None else env
    api_key = env.get('RESEND_API_KEY', '').strip()
    recipient = env.get('KEYWORD_REQUEST_ADMIN_EMAIL', '').strip()
    sender = env.get('KEYWORD_REQUEST_FROM_EMAIL', '').strip()
    if not (api_key and recipient and sender):
        raise NotificationConfigurationError(
            'RESEND_API_KEY, KEYWORD_REQUEST_ADMIN_EMAIL, and '
            'KEYWORD_REQUEST_FROM_EMAIL must be configured.'
        )

    request_id = str(request_row.get('id') or '').strip()
    if not request_id:
        raise ValueError('A saved request ID is required for notification delivery.')

    request_type = request_row.get('request_type', '')
    type_labels = {
        'risk_grade_adjustment': '리스크 등급 조정요청',
        'review_criteria_change': '심의기준 변경요청',
    }
    fields = {
        '키워드 번호': request_row.get('kwd_no', ''),
        '키워드명': request_row.get('keyword_name', ''),
        '문의 유형': type_labels.get(request_type, request_type),
        '요청자': request_row.get('requester_email', ''),
        '요청 내용': request_row.get('request_detail', '') or '(내용 없음)',
        '접수 시각': request_row.get('created_at', ''),
    }
    html_rows = ''.join(
        '<tr><th align="left" style="padding:6px 12px 6px 0">'
        f'{html.escape(label)}</th><td style="padding:6px 0">'
        f'{html.escape(str(value))}</td></tr>'
        for label, value in fields.items()
    )
    text_body = '\n'.join(f'{label}: {value}' for label, value in fields.items())
    payload = {
        'from': sender,
        'to': [recipient],
        'subject': f"[키워드 문의] {fields['키워드 번호']} · {fields['문의 유형']}",
        'text': text_body,
        'html': f'<h2>새 키워드 문의</h2><table>{html_rows}</table>',
    }
    try:
        response = post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'Idempotency-Key': f'keyword-request/{request_id}',
            },
            json=payload,
            timeout=(5, 15),
        )
    except requests.RequestException as exc:
        raise NotificationDeliveryError('이메일 발송 서비스에 연결할 수 없습니다.') from exc
    if response.status_code >= 400:
        raise NotificationDeliveryError(
            f'이메일 발송 서비스가 HTTP {response.status_code}을 반환했습니다.'
        )
    return True
