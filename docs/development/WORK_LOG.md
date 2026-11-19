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

## 2026-11-17 — 4단계 근거 요약·검토 범위 및 최종 검증

- 요청: 권장 마지막 단계인 조건·예외 보존 요약을 적용하고 전체 변경을 검증·커밋·푸시.
- 변경 파일: `regulation_assistant.py`, `regulation_corpus.py`, `keyword_suggestion.py`, `frontend/src/tabs/ChatTab.tsx`, `frontend/src/styles.css`, `docs/regulation-search.md`, `tests/test_evidence_integrity.py`, `tests/test_regulation_structure.py`, `tests/test_regulation_corpus_api.py`, 이 기록.
- 변경: 요약에 적용 대상·시행일·조건·예외·부정을 함께 유지하도록 요청. 내부 출처 인용 문단마다 실제 원문 구절을 대조하며 미검증/미완성 응답은 보류. 이전 LLM 경로도 검증된 주장·원문으로만 답변 구성. GPT 직접 요약도 미완성 출력을 보류. 근거 유형을 번갈아 선택하고 최대 8건/본문 48,000자 내에서 문단을 자르지 않고 전달. 제외 여부·인접 문단·전체 문서 검토가 아니라는 범위를 관리자·회원 공통 화면과 저장 근거에 표시. 검색어 강조와 인용 구절 밑줄을 구별.
- 검색/색인: 연결 자료 전체를 검색 단위로 나누고 질문을 반복해 뒤쪽도 처리. 단위별 결과의 순위를 합쳐 최대 5개 선택. 어휘 색인의 앞 160단어 제한을 제거해 긴 문단의 뒤쪽 단서도 색인. 긴 문단 임베딩은 2,000자 단위/배치 32개로 요청하고 길이 가중 평균 후 정규화해 원문을 잘라 버리지 않음. OpenAI 공식 입력 한도는 https://developers.openai.com/api/reference/python/resources/embeddings/methods/create 에서 확인. 긴 연결 자료의 검색·임베딩 사용량 증가를 문서에 명시. 기존 검색 요약 경로에서 사용량 이벤트가 최종 API 기록까지 전달되지 않던 부분도 수정·검증.
- 실행/검증: `.venv/review314/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"` 총 138개 중 137개 통과, 운영 초기화 opt-in 검사 1개 제외. 처음 전체 검사에서 검증 환경의 Pillow 누락을 확인해 lockfile과 같은 12.3.0 설치 후 통과. `pip check` 통과. `npm test` 16개, `npm run build` 통과. 기존 번들 크기 경고는 남아 있으나 빌드 성공. 실제 관리자·회원 API 경로에서 매칭 메타데이터와 인접 예외를 포함한 AI 근거·저장 스냅샷·사용량 전달 검증. 외부 AI/운영 DB 호출·서비스 시작·포트 변경 없음.
- 문서 검토: GitBook prerequisite-gap-checker 지침에 따라 별도 검토 에이전트가 운영 안내만 읽음. 등록보다 뒤에 있던 SQL 준비 안내 1건(Late/Blocks)을 등록 앞에 이동하고 원본 Storage 준비 문서도 사전에 연결. AI 가독성의 설명·첫 두 문장·구체적 제목·빈 제목·원문 값·링크 확인. description 길이, 로컬 링크 파일, 빈 제목 자동 검사와 docs diff·git diff --check 통과. 영어 단어 수 목표는 한국어에 기계 적용하지 않음. SUMMARY.md 검사는 해당 없음.
- 완료 확인: 1단계 cf9204e, 2단계 504e5d7, 3단계 1995505를 main에 push 완료. 4단계도 아래 검증한 변경만 커밋·푸시하며 기존 미추적 스킬 파일은 제외.
- 한계: 실제 사내 문서의 의미적 정확도는 심의자 정답 자료로 별도 측정해야 함. 원문 인용 존재 검사는 해석의 정확성을 자동 보증하지 않음. 이미 저장된 대화의 누락 자료·이전 매칭 경로는 재생성하지 않음. 복잡한 병합 표·전체 문서 검토는 원본 확인 필요. 운영 배포 완료 여부는 이번 로컬 구현·푸시의 검증 범위에 포함하지 않음.
- 커밋/푸시: 최종 diff·체크 검토 후 4단계 변경을 main에 커밋·푸시하고 원격 HEAD 일치 확인.

## 2026-11-19 — Toolkit 스킬과 대기 중인 변경 푸시

- 요청: 커밋 후 푸시.
- 변경 파일: Toolkit의 `prerequisite-gap-checker`를 Codex와 Claude 프로젝트 스킬로 추가하고 `skills-lock.json`으로 원본 버전을 고정. 기존 `main`의 대기 중인 7개 커밋도 함께 푸시.
- 실행/검증: 원격보다 `main`이 7개 커밋 앞선 것을 확인하고 각 커밋 요약과 기존 검증 기록을 검토. `git diff --check origin/main..main`에서 발견한 Runbook EOF 공백을 제거함.
- 검증: Toolkit 스킬 사본 내용 일치 확인. 프로젝트 테스트는 실행하지 않음.
- 커밋/푸시: 이 기록 및 스킬 설치 파일을 커밋하고 D-drive PC의 지정 명령으로 `main`에 푸시 완료.
- 미해결 항목: 없음.

## 2026-11-19 — Keyword Risk Analyzer 포트폴리오 자료 작성

- 요청: 저장소의 AGENTS.md와 프로그램 자료를 읽고 설계 로직·기능 구현·목표·기대효과 등을 분석한 HTML 및 PDF 설명자료 작성.
- 변경 파일: `docs/portfolio/keyword-risk-analyzer.html`, `output/pdf/keyword-risk-analyzer-portfolio.pdf`, 이 기록.
- 실행한 명령과 결과: 저장소 설계서·README·운영 안내·현행 React/API/매칭/OCR/문서 검색 구현·작업 기록을 검토. Edge headless 인쇄로 PDF 생성. `git diff --check` 실행.
- 검증: PDF 9페이지 생성 확인. 전체 페이지 축소본과 1·6·9페이지를 시각 점검해 한글, 표, 페이지 나눔, 링크 목록과 레이아웃 확인. 매칭 정확도·시간 절감·운영 품질은 측정값이 없어 기대효과와 추후 지표로 분리 표기. 코드 테스트 및 서비스 시작은 하지 않음.
- 커밋/푸시: 변경 diff 검토 후 D-drive PC 지정 명령으로 main에 커밋·푸시.
- 미해결 항목: 없음.

## 2026-11-19 — Keyword Risk Analyzer 기능별 UI 안내 PPT 초안

- 요청: 실제 구현 화면을 기능별로 설명하는 포트폴리오용 PPT 작성. GetDesign의 무료 DESIGN.md를 참고하고 차분한 파스텔 배경 적용.
- 변경 파일: `docs/development/WORK_LOG.md`. 비공개 Spaces에 13장 PPT 초안 작성.
- 실행: AGENTS.md·개발 Runbook·최신 WORK_LOG 확인. React 운영 UI 구조와 `frontend/README.md`, 관련 탭 구현을 확인. 현재 화면에서 관리자 역할 UI와 스크립트 분석 화면을 확인. Spaces Artifact Session으로 기능별 슬라이드 작성 및 전체 미리보기 렌더.
- 결과: 8개 기능 화면의 입력·처리·결과, 역할 분리, 시스템 흐름, 목표·기대효과, 향후 측정 지표를 작성. Oura 무료 DESIGN.md의 크림·세이지 팔레트 방향을 적용하고 출처를 수록. 전체 몽타주와 스크립트 분석·목표·출처 슬라이드를 시각 검토.
- 미완료: 실제 화면 캡처 파일을 PPT에 삽입하지 못해 각 기능 장표에 캡처 영역이 남아 있음. 사용자에게 PNG/JPG 캡처 파일 첨부 또는 `docs/portfolio/screenshots/`에 저장을 요청함. 파일 수령 후 같은 PPT에 삽입 예정.
- 서비스·검증: 포트 변경이나 서비스 시작 없음. 프로그램 테스트 미실행. PPT는 비공개 Spaces 초안이며 민감한 화면 이미지를 공개 저장소에 추가하지 않음.
- 커밋/푸시: 이 기록만 검토·반영하며 사용자 요청대로 D-drive PC의 지정 push 명령 사용.

