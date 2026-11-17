# 개발 작업 기록

이 파일은 Codex가 이 저장소에서 수행한 작업과 검증 내역을 날짜순으로 남깁니다. 실행하지 않은 명령은 기록하지 않으며, secret·비밀번호·토큰과 무시되는 환경 파일의 값은 기록하지 않습니다.

## 2026-11-17 — LLM 답변 URL 링크 표시

- 요청: LLM 답변의 인터넷 주소를 하이퍼링크로 표시하고 Ctrl+클릭으로 열 수 있게 함.
- 변경 파일: `frontend/src/tabs/ChatTab.tsx`, `frontend/src/styles.css`.
- 실행한 명령과 결과: `npm run build` 성공. `git diff --check` 성공.
- 검증: TypeScript 검사와 Vite 운영 빌드 통과. 공통 답변 렌더러에 적용되어 관리자·일반회원 화면에서 동일하게 표시됨.
- 커밋/푸시: `ff775bb`를 `main`에 push 완료.
- 미해결 항목: 없음.

## 2026-11-17 — 개발 Runbook과 작업 기록 흐름 정리

- 요청: 앞으로의 작업 절차를 저장소에 남기고, 실제 안내 명령을 실행·검증·기록하는 흐름을 마련함.
- 변경 파일: `AGENTS.md`, `README.md`, `.env.example`, `frontend/.env.example`, `frontend/README.md`, `docs/development/README.md`, `docs/development/WORK_LOG.md`.
- 실행한 명령과 결과: Python 3.14.7, Node.js v24.20.0, npm 11.19.0, Git 2.55.0 버전 확인. 문서 상대 링크 검사와 `git diff --check` 통과.
- 검증: GitBook `prerequisite-gap-checker`로 새 Runbook을 다시 읽고 준비사항을 점검함. 도구 설치 링크, Supabase 키·역할·스키마, 일반/격리 포트 쌍, Docker·방화벽 요구사항, 두 역할의 테스트 계정을 안내함. 기존 README의 없는 설계 ZIP 링크도 제거함. 코드 테스트는 수행하지 않음.
- 커밋/푸시: 변경 검토 후 `main`에 커밋·푸시 완료.
- 미해결 항목: GitBook MCP 계정 연결은 하지 않음. 저장소의 문서 diff 검토를 반영 경로로 사용.

## 2026-11-17 — NoteCam 원격 변경 모니터링 대상 확인

- 요청: NoteCam origin/upstream의 커밋·브랜치·PR 변화를 정기 확인하고 PC 간 작업 영향, 동기화·충돌 위험, 읽기 전용 명령을 요약. 자동 병합·원격 변경 금지.
- 변경 파일: `docs/development/WORK_LOG.md`(이 기록만 추가).
- 실행한 명령과 결과: `Get-Content`로 AGENTS·Runbook·최신 작업 기록 확인, `git status --short`, 인접 저장소 `.git/config` 조회, `git -C D:/back-up/encore/aio-03-p2-team3 remote -v`, README 조회, `rg`로 NoteCam 명칭 검색. GitHub 연결 도구로 저장소 검색, 앱 도구로 프로젝트·채팅 목록과 자동화 기능 확인.
- 검증: 현재 프로젝트는 keyword-risk-analyzer. 인접 aio-03-p2-team3의 origin/upstream은 확인했으나 NoteCam이라는 근거는 찾지 못함. 기존 로컬 변경은 보존. 대상 확인 질문을 전달했으며 정기 점검은 아직 생성하지 않음.
- 커밋/푸시: 없음. 사용자의 원격 변경 금지 요청에 따라 push하지 않음.
- 미해결 항목: NoteCam의 정확한 origin/upstream 주소 확인 후 1시간 주기 읽기 전용 점검 설정 필요.

## 2026-11-17 — AI 가독성·SEO/AEO 관점의 규정 검색·요약·매칭 검토

- 요청: AI Readability Check와 SEO & AEO Documentation을 적용해 사내규정 분석·LLM 요약·키워드 매칭 옵션·하이라이트의 개선점을 면밀히 검토. 구현 변경은 요청되지 않음.
- 적용 기준: 로컬에는 요청 스킬이 없어 GitbookIO/docs-skills의 `skills/ai-readiness/SKILL.md`(blob 5e3ecb5d06244380c913849b097bd4d487001e0e), `skills/seo-aeo-documentation/SKILL.md`(blob 0ddf7b04eefc4a340d9329b02e928ee7dd15c315)를 GitHub 읽기 도구로 확인·적용. 설치하지 않음. 문서 독립성·조건/예외 보존·인용 추적성을 내부 검색에 적용하며 검색 순위 향상은 주장하지 않음.
- 변경 파일: `docs/development/WORK_LOG.md`(기록만). 프로그램·환경·운영 데이터 변경 없음.
- 실행한 명령과 결과: `Get-Content`와 `rg`로 AGENTS·Runbook·README·규정 추출/분할/검색/LLM·매칭·React 강조·평가 코드 검토. `git status --short`, `py -0p`, `node --version`, `Test-Path SUMMARY.md` 확인. `.venv/Scripts/python.exe -m unittest discover -s tests -p ...` 3종은 가상환경이 가리키는 Python 3.13 실행 파일 부재로 실패. `py -3.14 -m unittest discover -s tests -p test_regulation_evaluation.py` 2개 통과. 같은 방식의 test_approved_matching.py와 test_regulation_corpus_api.py는 pandas/FastAPI 미설치로 실행 불가. frontend의 `npm test` 15개 통과.
- 재현 검증: `py -3.14 -`로 기존 함수 AST만 격리 실행한 합성 사례에서 1,500자 분할 시 예외 문장과 조항 제목 분리 확인. 최초 표준입력 한글 인코딩 문제와 작업 폴더 경로 오류를 수정해 유니코드 이스케이프로 재검증. 모의 응답으로 LLM에 INT1~INT8만 전달했음에도 INT9 인용이 검증 통과함을 확인. save_turn에서 뒤쪽 인용 WEB5가 첫 10개 제한으로 저장되지 않음을 확인. `node --input-type=module -`로 antiaging/ANTIAGING 일치에서 상세 공통 강조 문자열이 비는 사례 확인. 외부 AI·DB 호출 없음.
- 주요 결과: (1) 실제 전달 출처와 허용 인용 ID 집합 불일치 (2) 인용 출처와 대화 저장 10건 제한 불일치 (3) 문서의 조항·조건·예외 및 표 머리글·페이지 구조 보존 부족 (4) 질문+맥락 2,000자 제한·검색 5건·LLM 앞 8건 선택으로 검토 범위 제한 (5) 출처 표식 존재 검증은 주장 의미의 뒷받침을 보장하지 않음 (6) 매칭 이유를 서버가 반환하지 않아 화면이 추정함 (7) 챗봇 완화 일치는 표시 방식이며 서버 검색 조건을 바꾸지 않음 (8) 근거·조건·예외를 보존하는 요약과 실제 평가 자료 보강 권고.
- AI 가독성 대표 문서 점검(`docs/regulation-search.md`): A-1 실패(1행, description 없음; 현재 색인에 사용하는지는 별도 확인 필요), A-2 통과(3행), A-3 실패(15·50행의 포괄적 제목), A-4 실패(34행 다음 본문 없이 36행 하위 제목), A-5 보류(한국어·코드 식별자에 영어 단어 수 기준을 기계 적용하지 않음), A-6 해당 없음(표 없음), A-7 통과(7·17·52행에 제한/옵션을 텍스트로 명시), A-8 통과(문단 도입부 검토), A-9 해당 없음(일반 문서 링크 없음), A-10 해당 없음(SUMMARY.md 없음). 등록된 실제 사내규정 원본은 읽지 않았으므로 문서별 합격/불합격 또는 운영 검색 품질은 판단하지 않음.
- 검증 범위: React 운영 진입점 README와 관리자 전용 문서관리/공통 ChatTab 분기 정적 확인. UI·실행 안내 변경이 없어 서비스 시작·포트 변경·운영 접속·추가 설치는 하지 않음. 기존 검색 평가 사례 초안만으로 품질 수치 주장하지 않음.
- 커밋/푸시: 없음. 검토 결과와 기록만 로컬에 남김. 기존 미추적 파일과 앞선 기록은 보존.
- 미해결 항목: 실제 승인 사내문서와 심의자 정답으로 조건·예외 동반 검색, 인용 충실도, 의미 후보 오인율 평가 필요. 백엔드 실행환경 복구는 이번 검토 범위에서 제외.

## 2026-11-17 — 1단계 인용 검증·대화 근거 보존

- 요청: 검토 기록 커밋·푸시 후 권장 순서로 개선, Ponytail 적용.
- 변경 파일: `regulation_assistant.py`, `regulation_corpus.py`, `tests/test_evidence_integrity.py`, 이 기록.
- 변경: 실제 LLM 전달 출처로만 인용 검증. 현재/이전 웹 인용 응답 형식 지원. 미완성 응답 보류. 검증 후 답변·출처를 잘라내지 않으며 대화에 전체 근거·버전·해시를 보존.
- 실행/검증: 앞선 검토 기록을 `eaf9c00`으로 main에 push. Python 3.14와 requirements.txt로 무시되는 `.venv/review314` 검증 환경 준비(httpx·python-multipart·python-dotenv·tzdata 포함). 해당 Python으로 unittest discover의 test_evidence_integrity.py 4개, test_regulation_corpus_api.py 16개 통과. 외부 AI·운영 DB 호출 없음. diff 검토·공백 검사 후 커밋.
- 커밋/푸시: 1단계 변경을 검증 후 main에 커밋·푸시.
- 참고: 앞선 NoteCam 요청은 사용자가 취소했으며 자동화 생성·후속 작업 대상에서 제외.
- 후속: 조항·조건·예외 보존 → 매칭 이유 표시 → 요약 개선.

## 2026-11-17 — 2단계 규정 구조·조건·예외 보존

- 요청: 권장 순서 두 번째인 조항·조건·예외 보존 개선.
- 변경 파일: `regulation_corpus.py`, `regulation_assistant.py`, `tests/test_regulation_structure.py`, 이 기록.
- 변경: 새 문서는 1,500자 경계를 넘더라도 보통 문단은 6,000자까지 유지하고 초장문은 문장 경계 우선 분할. 바로 뒤 단서 문단을 함께 유지. DOCX 제목과 표의 항목명·값·빈 셀, PDF 원문 쪽수 보존. 기존 등록 문서는 재작성하지 않으며 검색 시 같은 버전의 인접 문단을 함께 읽고 근거 스냅샷으로 저장. 인접 문단 조회 실패 시 원문 확인 안내.
- 실행/검증: `.venv/review314/Scripts/python.exe -m unittest discover -s tests -p test_regulation_structure.py` 5개, test_regulation_corpus_api.py 16개, test_keyword_suggestion.py 11개 통과. 초장문 텍스트 무손실·단서 동반·버전 범위·이미지 PDF 거절 검증. 운영 데이터/SQL 변경 없음. diff·공백 검사 후 커밋.
- 커밋/푸시: 2단계 변경을 검증 후 main에 커밋·푸시.
- 한계: 한 문장이 6,000자를 초과하면 분할되므로 검색 문단만으로 전체 문서 검토를 주장하지 않음. 복잡한 병합 표의 시각 배치는 원본 파일에서 확인 필요.

## 2026-11-17 — 3단계 실제 매칭 이유·원문 강조 표시

- 요청: 매칭 이유를 서버에서 명시하고 화면의 추정 설명을 줄임.
- 변경 파일: `approved_matching.py`, `api.py`, `frontend/src/lib/types.ts`, `frontend/src/lib/highlight.ts`, `frontend/src/tabs/ChatTab.tsx`, `tests/test_approved_matching.py`, `tests/test_current_analysis.py`, `frontend/tests/parity.test.ts`, 이 기록.
- 변경: 현재 분석 결과에 실제 경로(완전/내용어/승인/등록표현/부분문자열), 입력·등록 원문 표현, 사용 옵션을 기록·반환. 상세 팝업에 해당 근거와 주변 문맥 표시. 이전 결과의 미저장 경로는 추정하지 않음. 대소문자 무시 결과도 원문 강조. 챗봇의 완화 일치를 검색 변경과 구분해 '강조 범위 확대'로 표시.
- 실행/검증: Python unittest의 test_approved_matching 6개, test_matching_regression 7개, test_current_analysis 5개 통과. 관리자·일반회원 API 실제 응답 검사에서 Pydantic 응답 필드 누락을 발견·수정한 뒤 재검증. npm test 16개, npm run build 통과. 기존 매칭 범위·중복·코드 회귀검사는 유지. README의 React 운영 진입점과 App.tsx/ChatTab의 역할별 분기를 확인했으며 공통 화면에 동일 적용. 서비스 시작·포트 변경 없음.
- 커밋/푸시: diff·공백 검사 후 3단계 변경 main 커밋·푸시.
- 후속: 근거·적용 범위·조건·예외를 보존하는 요약 및 검토 범위 표시.
