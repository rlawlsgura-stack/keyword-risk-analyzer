# React 화면

`frontend/`는 운영 React/TypeScript 화면입니다.
이전 QA 기록은 [docs/qa/legacy_react_QA_STATUS.md](../docs/qa/legacy_react_QA_STATUS.md)에 보관합니다.

## 구조

```text
React (frontend/) ── FastAPI (api.py) ── service / matching_engine / repository ── Supabase
       └─ Supabase Auth (로그인·회원가입·비밀번호 복구는 브라우저에서 직접)
```

| 경로 | 내용 |
| --- | --- |
| `src/App.tsx` | 로그인·복구 링크 처리, 역할 확인, 사이드바, 탭 표시 규칙 |
| `src/store.tsx` | 탭 사이 공유 상태 (키워드 원장, 분석 입력, OCR 후보, 미저장 미매칭 수집) |
| `src/tabs/*` | 8개 탭: 스크립트 분석 · 이미지 OCR분석 · 미매칭 후보군 · 키워드 문의내역 · 심의 Chat-bot · 분석리포트 · 키워드 관리 · 사용자 관리 |
| `src/lib/highlight.ts` | `highlight_text`·툴팁 포팅 (겹침 병합, 번호 괄호 건너뛰기, 매칭 근거) |
| `src/lib/catalog.ts` | 정렬·날짜 표시(KST)·`next_kwd_no`·드롭다운 정규화 포팅 |
| `src/lib/workspace.ts` | 정규화 작업본 (draft v1 형식과 행 ID) |
| `tests/parity.test.ts` | Python 결과와 맞춘 포팅 로직 단위 테스트 |

현재 화면 동작:
- 키워드 업로드는 파일 선택 후 **업로드** 버튼을 눌러야 실행됩니다.
- 키워드 삭제·드롭다운 값 삭제 전에 확인 단계를 둡니다.
- 정규화 작업본의 셀 편집은 1.5초 뒤 자동 저장됩니다.
- 원장 편집 표는 100행씩 페이지로 나눠 셀을 클릭해 수정합니다. 동작하지 않던 선택 열은 뺐습니다.
- 사용자 역할이 지정되지 않은 계정도 역할 변경 화면이 오류 없이 열립니다.

## 로컬 실행 (운영 DB와 분리된 테스트 환경)

Docker Desktop이 켜져 있어야 합니다. 프로젝트 루트에서 차례대로 실행합니다.

```powershell
cd frontend; npm ci; cd ..
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_test_supabase.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_test_api.ps1      # 다른 터미널
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_test_frontend.ps1 # 다른 터미널
```

`http://127.0.0.1:5173`에서 `.local-test-credentials.txt`의 로컬 전용 관리자 계정으로 로그인합니다.

## 검증

```powershell
npm test        # 포팅 로직 단위 테스트 (Node 22.13+)
npm run build   # 타입 검사 + 운영 빌드
```

## 배포

`render.yaml`의 `keyword-risk-ui` 정적 사이트가 이 폴더를 빌드합니다. 운영 주소는 [https://keyword-risk-ui.onrender.com](https://keyword-risk-ui.onrender.com)입니다.
빌드 시 `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`(공개용 키), `VITE_API_BASE_URL`이 필요합니다.
`SUPABASE_SECRET_KEY`는 절대 `VITE_` 변수에 넣지 않습니다.
이 화면이 쓰는 API 추가분(`/api/v2/matching-rules`, `/api/v1/keyword-requests/new-keywords`,
`/api/v1/admin/unmatched-terms/register`, `/api/v1/admin/unmatched-registration-requests/delete` 등)이 있으므로
API 서비스를 함께 배포해야 합니다.
