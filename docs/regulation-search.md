# 심의챗봇 검색 운영 안내

운영 React 화면과 Streamlit 보조 화면은 같은 FastAPI 심의챗봇을 사용합니다. 검색 범위는 국가법령정보센터, 사내 규정 문서, 키워드 DB, 통합 검색입니다. 질문 방향은 별도로 선택합니다. 검색 결과는 심의자의 근거 검토를 돕고, 기존 키워드 위험 판정을 변경하지 않습니다.

## 사내 문서 등록과 버전

관리자가 심의챗봇의 **사내 규정 문서 관리**에서 TXT, MD, DOCX, PDF 파일을 초안으로 등록합니다. 최대 2MB, 검색 가능한 본문 20~250,000자, 최대 300개 문단입니다. 이미지 전용 PDF는 OCR로 텍스트를 만든 뒤 등록해야 합니다. 원본 파일은 서버 전용 Supabase 테이블에 보관하고 SHA-256을 기록합니다. 브라우저는 원본 바이트에 직접 접근하지 않습니다.

문서 식별자, 버전, 상품 카테고리, 시행일과 종료일을 입력합니다. 본문 미리보기와 시행일을 검토한 다음 승인합니다. 잘못 등록한 초안은 삭제할 수 있습니다. **초안은 검색되지 않습니다.** 같은 식별자의 새 버전을 승인하면 이전 승인본의 종료일을 새 시행일 전날로 정하고 이전 버전으로 보관합니다. 새 버전 시행일은 현재 승인본보다 뒤여야 합니다. 검색 기준일에 맞는 승인 이력이 검색됩니다. 문서 원본은 승인 후 수정하지 않고 새 버전으로 교체합니다.

신규 Supabase 설치에는 `supabase/regulation_corpus_setup.sql`을 적용합니다. 이 프로젝트에는 `regulation_corpus_setup`, `regulation_corpus_versions_fix`, `regulation_embedding_backfill`, `regulation_draft_cleanup`, `regulation_raw_search_baseline` 마이그레이션이 적용되었습니다. 테이블은 RLS와 권한 회수로 브라우저 직접 접근을 막고 FastAPI의 서버 비밀 키만 사용합니다. 관리 API는 Supabase Auth `app_metadata.role=admin`을 다시 확인합니다.

## 검색

- 사내 문서는 Kiwi 내용어와 원문 단어로 검색 토큰을 만들고 PostgreSQL 전문 검색을 수행합니다. `pg_trgm` 유사 문자열 검색을 보조로 사용합니다.
- `REGULATION_EMBEDDINGS_ENABLED=true`와 `OPENAI_API_KEY`를 서버에 설정하면 `text-embedding-3-small` 임베딩을 함께 생성합니다. 어휘, 유사 문자열, 의미 검색 순위는 RRF로 합칩니다. 설정이 꺼져 있으면 어휘·유사 문자열 검색만 사용합니다. 기존 문서는 관리자의 **의미 검색 색인 생성** 버튼으로 색인을 채웁니다.
- 사내 문서의 승인 상태, 상품 카테고리, 기준일을 먼저 적용합니다. 기준일은 사내 문서 버전에 적용되며 국가법령정보센터의 과거 법령 버전을 조회하는 옵션은 아닙니다. 답변 출처에는 문서 ID, 버전, 내용 해시와 문단 ID를 연결합니다.
- 국가법령정보센터 범위는 기존 `legislation_source.py`를 사용합니다. 키워드 DB 범위는 현재 등록 키워드의 관련 후보를 제시합니다. 의미 검색 결과를 기존 위험 등급이나 자동 매칭에 합치지 않습니다.

운영 문서와 검토된 질문·정답 문단이 준비되면 `scripts/compare_regulation_search.py`로 원문 PostgreSQL 전문 검색, Kiwi 토큰 전문 검색, 유사 문자열, 의미, 통합 검색을 동일한 사례에서 비교합니다. `scripts/evaluate_regulation_retrieval.py`는 Recall@5/10, MRR, 근거 없음 응답, 금지 출처 혼입과 지연시간을 채점합니다. 평가 사례에는 `case_id`, `judgment_status=approved`, `evaluation_type=relevance`, `question`, `category`, `category_filter`, `as_of`, `relevant_ids`, `forbidden_ids`를 기록합니다. `category`는 평가 분류(`cosmetics`, `food`, `health_functional_food`)이고 `category_filter`는 실제 문서 카테고리 값입니다. 정답 ID는 관리자 본문 미리보기의 문단 ID를 사용합니다. **현재 승인된 사내 문서와 검토된 평가 사례가 없으므로 품질 수치를 주장할 수 없습니다.**

## 답변과 대화

심의챗봇은 **AI 근거 검토 및 부족한 공식 출처 추가 검색**을 기본으로 선택합니다. 서버에서 `REGULATION_LLM_ENABLED=true`, `REGULATION_LLM_MODEL`, `OPENAI_API_KEY`를 설정하면 먼저 검색된 근거의 충분성과 충돌을 검토합니다. 중요한 사실이나 값이 빠졌거나 근거가 충돌할 때 OpenAI Responses API의 웹 검색을 사용해 법령, 정부·규제기관 등 공식 도메인에서 추가 근거를 찾습니다. 공식 출처에서 확인할 수 없는 사내 고유 정책이나 값은 추정하지 않고 미확인으로 표시합니다.

AI 답변은 항상 심의 권고이며 위반·적합의 최종 판정이 아닙니다. 내부·검색 근거는 기존 출처 ID로, 웹 검색 근거는 `[WEB1]` 형식으로 답변과 출처 카드에 연결합니다. 웹 검색 인용은 허용된 공식 도메인의 URL만 표시하며, 유효한 출처 연결을 만들지 못하면 답변을 보류하고 추가 확인을 권고합니다. 사내 문서의 검색 문단과 질문은 기존과 같이 외부 AI API에 전송됩니다. AI 요약을 끄면 검색 결과만 표시합니다.

로그인한 사용자의 대화는 사용자 ID별로 저장합니다. 저장된 답변에는 사용된 문서 ID, 버전, 해시와 인용 원문을 붙여 이후 문서가 바뀌어도 당시 근거를 확인할 수 있습니다. 새 대화는 새 스레드를 만듭니다. 관리자도 자신의 대화만 조회하며 다른 사용자의 대화에는 접근할 수 없습니다. 저장된 대화를 선택해 **선택 대화 삭제**를 실행하면 확인 후 그 대화와 메시지·저장 근거가 영구 삭제됩니다. 자동 삭제는 적용하지 않았으며, 드롭다운에는 최근 대화 50개까지 표시합니다.

## 서버 설정

`LEGISLATION_API_KEY`는 국가법령정보센터 조회에 필요합니다. `REGULATION_API_URL`은 Streamlit에서 FastAPI 주소를 가리킵니다. `REGULATION_EMBEDDINGS_ENABLED`와 `REGULATION_LLM_ENABLED`의 기본값은 모두 `false`이므로 AI 근거 검토·추가 검색을 운영에서 사용하려면 API 서비스에 `REGULATION_LLM_ENABLED=true`, `REGULATION_LLM_MODEL`, `OPENAI_API_KEY`를 설정해야 합니다. 비밀 키는 API 서비스에만 둡니다. `REGULATION_MCP_URL`은 사용하지 않습니다.
