# 키워드 문의 기능 설계 및 적용

FIXED274에는 Supabase 계정 사용자를 위한 키워드 문의 등록과 조회 기능이 추가되었습니다.

## 화면 동작

- 사이드바의 `최신 데이터 불러오기` 아래에서 키워드 번호나 이름을 검색해 선택하고, 문의 유형과 상세 내용을 입력해 등록합니다.
- 문의 유형은 `리스크 등급 조정요청`, `심의기준 변경요청`, `신규키워드 등록요청`입니다. 신규키워드 등록요청은 기존 키워드 선택 없이 등록할 수 있습니다.
- 등록 전에 최신 공유 키워드 목록에서 `kwd_no`를 확인합니다. 키워드명은 DB의 현재 값을 복사해 문의 행에 기록합니다.
- `키워드 문의 내역` 탭에서 일반 사용자는 본인 요청만, 관리자는 전체 요청을 확인합니다.
- 요청 내역에는 `대기`, `검토중`, `처리완료` 상태와 관리자 답변이 표시됩니다. 접수 시각은 한국 시간의 `YYYY-MM-DD HH:MM` 형식으로 마지막 열에 표시합니다.
- 관리자는 각 문의의 상태와 답변을 수정해 저장할 수 있습니다. 일반 사용자는 본인 문의의 상태와 답변을 조회만 할 수 있습니다.
- 관리자는 해당 탭에서 이메일 알림을 켜거나 끌 수 있습니다. 기본값은 꺼짐입니다.
- 키워드 문의는 Supabase 로그인 사용자의 access token으로 저장·조회됩니다. SQL 정책이 사용자 ID와 관리자 `app_metadata.role`을 확인합니다.

## 본인 요청 수정 및 삭제 (FIXED300)

문의 내역의 행을 선택한 뒤 `내 요청 수정`에서 문의 유형과 상세 내용을 수정하고
`수정 저장`을 누릅니다. 본인 계정이 작성한 기존 요청에만 표시됩니다. 등록된 키워드,
작성자, 접수 시각, 처리상태와 관리자 답변은 수정하지 않습니다. 키워드가 지정되지 않은
신규키워드 등록요청은 다른 문의 유형으로 변경할 수 없습니다.

수정은 로그인 토큰의 사용자 ID로 소유권을 확인하는 전용 DB 함수에서 수행합니다.
최초 문의 메시지 내용도 같은 트랜잭션에서 갱신하며, 아직 최초 메시지가 없는 기존 요청은
접수 당시의 작성자·시각·현재 처리상태로 최초 메시지를 생성합니다. 관리자 답변과 후속 대화는 보존합니다.
일반 사용자에게 처리상태·관리자 답변이나 대화 메시지를 직접 수정하는 권한은 부여하지 않습니다.

본인 요청에는 `문의 삭제`도 표시됩니다. `영구 삭제 확인`을 누르면 해당 요청과 연결된
모든 문의·답변이 함께 삭제됩니다. 관리자의 전체 요청 삭제 권한도 유지됩니다.
다른 사용자의 요청은 DB 소유권 정책으로 삭제할 수 없습니다.

기존 프로젝트에는 [keyword_request_owner_edit_setup.sql](../../supabase/keyword_request_owner_edit_setup.sql)을
기존 피드백·처리상태 설정 이후 적용합니다. 전체 신규 설치용 `schema.sql`에도 포함됩니다.
DB 권한·수정·연결 대화 삭제는 `tests/keyword_request_owner_edit.sql`로 검증하며 테스트 데이터는 롤백합니다.
연결된 운영 프로젝트에는 `keyword_request_owner_edit_delete` 마이그레이션을 적용했고,
본인 수정·삭제, 타인 접근 차단, 관리자 처리 권한 보존과 원자적 갱신 검증을 통과했습니다.

## 기존 Supabase 프로젝트에 적용

이 기능에 필요한 SQL은 연결된 Supabase 운영 프로젝트에 마이그레이션으로 적용했습니다. 기존 프로젝트에서는 수동으로 다시 실행할 필요가 없습니다. 새 프로젝트를 설정할 때는 Supabase Dashboard SQL Editor에서 [keyword_requests_setup.sql](../../supabase/keyword_requests_setup.sql)을 실행하면 됩니다.

Supabase 운영 프로젝트에 문의 테이블과 RLS 마이그레이션을 적용했습니다. 상태·답변 저장은 관리자 전용 RLS 정책으로 제한합니다. 처리 완료는 문의 상태를 기록하는 기능이며, 관리자 승인 후 키워드 DB를 자동 변경하는 기능은 별도 구현 대상입니다.

## 이메일 알림 설정

메일 발송은 Resend API를 사용합니다. `.env.example`의 세 변수를 로컬 `.env` 또는 배포 환경의 Secrets에 설정합니다.

```dotenv
RESEND_API_KEY=
KEYWORD_REQUEST_ADMIN_EMAIL=관리자_수신주소
KEYWORD_REQUEST_FROM_EMAIL=Keyword Desk <검증된_발신주소>
```

Resend에서 발신 도메인을 인증하고 API 키를 발급해야 합니다. 값이 없으면 관리 화면에서 알림을 켤 수 없고, 요청 저장과 내역 조회는 계속 사용할 수 있습니다. 알림 발송이 실패해도 이미 저장된 요청은 취소되지 않으며 화면에 별도 경고가 표시됩니다.

Streamlit Community Cloud에서는 위 변수들을 앱의 Secrets에 TOML 형식으로 입력합니다.

## 주요 제한 및 검증 경계

- 요청은 최근 1,000건까지 표시합니다.
- 이메일은 저장 성공 후 best-effort 방식으로 한 번 요청합니다. 재시도 큐나 발송 이력 화면은 포함하지 않습니다.
- 사용자/관리자 분리는 DB RLS가 최종 적용합니다. 관리자 역할은 사용자가 수정할 수 없는 `app_metadata.role` 기준입니다.
- SQL Editor 실행과 실제 메일 발송은 아직 검증되지 않았습니다. 로컬 단위 테스트는 권한 토큰 전달과 메일 요청 조립을 확인합니다.
## 문의별 대화 히스토리 (FIXED276)

문의 상세 팝업에서 최초 문의와 기존 관리자 답변을 확인하고, 이후 대화를 시간순으로 이어갈 수 있습니다.

- 일반 사용자는 본인 문의에 재문의 또는 댓글을 추가할 수 있습니다.
- 관리자는 전체 문의를 열어 피드백/댓글을 추가할 수 있으며, 기존 처리 상태와 현재 답변 편집·삭제 기능도 유지됩니다.
- 새 메시지는 `kra_keyword_request_messages`에 별도 행으로 누적됩니다. 이전 문의 레코드는 수정하지 않습니다.
- 대화 메시지는 추가 방식으로 관리합니다. FIXED300부터 본인 요청 수정 시 최초 문의 내용만 함께 갱신하며, 답변과 후속 대화는 보존합니다. 로그인한 사용자는 본인이 작성한 메시지만 추가할 수 있습니다. 문의 소유자는 본인 문의의 메시지만 읽고, 관리자는 전체 메시지를 읽고 추가할 수 있습니다.
- 기존 프로젝트의 DB 설정에는 [keyword_request_messages_setup.sql](../../supabase/keyword_request_messages_setup.sql)을 추가 적용해야 합니다. 이후 새 프로젝트 설정은 `keyword_requests_setup.sql` 또는 전체 `schema.sql`에 포함된 설정을 사용합니다.\n
Administrator reply inserts use supabase/keyword_request_reply_policy_fix.sql; its private helper validates unanswered inquiry targets without recursive RLS evaluation.\n\n## 문의와 답변 1:1 연결 (FIXED277)

대화 목록은 메시지의 단순 시간순 나열에서 문의별 묶음으로 바뀝니다. 관리자가 답변을 등록할 때 대상 사용자 문의를 선택하고, 해당 답변은 그 문의 바로 아래에 표시됩니다. 사용자 재문의는 새 문의 항목으로 저장되어 각각 별도 답변을 받을 수 있습니다.

- 메시지 행의 `reply_to_id`가 답변 대상 문의를 가리킵니다.
- 부분 고유 인덱스로 문의 하나에 관리자 답변을 하나만 연결합니다.
- 사용자는 본인 문의에만 답변 없는 새 문의/댓글을 추가합니다. 관리자는 선택한 사용자 문의에 답변합니다.
- 기존 메시지와 관리자 답변 필드는 보존합니다. 기존 메시지는 소유자와 작성 시각을 기준으로 가능한 범위에서 자동 연결합니다.
- 기존 Supabase 프로젝트에는 [keyword_request_reply_pairing_setup.sql](../../supabase/keyword_request_reply_pairing_setup.sql)을 적용해야 합니다.

## User follow-up replies (FIXED280)

Users can select **Reply to this answer** under an administrator response and continue the same numbered inquiry thread. Administrators can respond to each user follow-up; the reply target is validated with a private SECURITY DEFINER helper and a unique index allows at most one direct response per message. Existing answers stored only on the request row are backfilled as legacy admin messages; their historical author and exact timestamp were not available, so the UI does not present invented metadata.

Apply [keyword_request_user_followup_setup.sql](../../supabase/keyword_request_user_followup_setup.sql) after the existing message history and reply-pairing setup.

## Inquiry cards (FIXED281)

Each initial inquiry is rendered in its own bordered card. Responses and re-inquiries appear in chronological order in that same card, separated by dividers and labeled Q01, Q01_A1, Q01-R1, Q01_A2. A new initial inquiry creates the next separate card.

## Per-inquiry feedback and status (FIXED282)

Administrators select **Feedback** on an unanswered user message inside its conversation card. Only that target opens an editor, where the administrator enters a reply and selects one status. Saving appends the linked reply, updates that inquiry message's status, and refreshes the request-level status/reply summary in one database transaction. keyword_request_feedback_status_setup.sql is applied after the user-follow-up migration.

## Optional keyword selection for new keyword requests (FIXED284)

For `신규키워드 등록요청`, users may leave the keyword search empty. The request is stored with a blank `kwd_no` and the display name `신규 키워드`. Other request types still require selecting an existing keyword. The connected Supabase project has the matching conditional constraint migration.
