"""Build an offline design book and API contracts without touching the database."""
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'design'
sys.path.insert(0, str(ROOT))


def svg_text(x, y, value, size=16, fill='#243047', weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}">{html.escape(value)}</text>'


def svg_box(x, y, width, height, title, lines):
    result = f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="10" fill="white" stroke="#bac5d4"/>'
    result += f'<path d="M{x+10} {y}H{x+width-10}Q{x+width} {y} {x+width} {y+10}V{y+42}H{x}V{y+10}Q{x} {y} {x+10} {y}" fill="#eaf0f8"/>'
    result += svg_text(x+16, y+28, title, 17, weight=700)
    for index, line in enumerate(lines):
        result += svg_text(x+16, y+69+index*26, line, 14)
    return result


def write_svg(name, width, height, title, body):
    source = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">
<title id="title">{html.escape(title)}</title>
<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9" fill="#60718c"/></marker></defs>
<rect width="100%" height="100%" fill="#f8fafc"/>
<g font-family="Malgun Gothic, Apple SD Gothic Neo, sans-serif">{body}</g></svg>'''
    (OUT / 'assets' / name).write_text(source, encoding='utf-8')


def diagrams():
    (OUT / 'assets').mkdir(parents=True, exist_ok=True)
    body = svg_text(30, 36, 'KRA 서비스 구성', 23, weight=700)
    body += svg_box(30, 80, 220, 138, '사내 사용자', ['브라우저 화면', 'member 또는 admin'])
    body += svg_box(30, 270, 220, 138, '외부 연동 시스템', ['사용자 access token', '또는 연동 전용 토큰'])
    body += svg_box(315, 80, 265, 138, 'Streamlit 서버', ['로그인과 화면 이벤트', '공통 매칭 함수를 직접 호출'])
    body += svg_box(315, 270, 265, 138, 'FastAPI 서버', ['인증과 입력 검증', '분석 조회 및 통계 API'])
    body += svg_box(650, 80, 300, 138, '공통 Python 모듈', ['service.py와 매칭 엔진', '원문 위치와 결과 필터'])
    body += svg_box(650, 270, 300, 138, 'Supabase', ['Auth 계정과 역할', 'PostgreSQL 및 REST RPC'])
    for path in ('M250 150H310', 'M250 340H310', 'M580 150H645',
                 'M580 340H645', 'M580 310L645 195', 'M580 183L645 302'):
        body += f'<path d="{path}" fill="none" stroke="#60718c" stroke-width="2" marker-end="url(#arrow)"/>'
    body += svg_text(32, 455, 'Streamlit은 FastAPI의 가용성과 독립적으로 동작하며 두 서버가 같은 DB를 사용합니다.', 15)
    write_svg('architecture.svg', 990, 485, '시스템 아키텍처', body)

    body = svg_text(28, 36, 'Supabase 테이블과 관계', 23, weight=700)
    body += svg_box(30, 75, 280, 200, 'kra_runs', ['PK id uuid', 'actor text', 'fingerprint text', 'result jsonb', 'created_at timestamptz'])
    body += svg_box(410, 75, 285, 252, 'kra_hits', ['PK id bigint identity', 'FK analysis_id uuid NULL', 'kwd_no text', 'ts timestamptz', 'visible boolean', 'UK import_key text NULL', 'UK analysis_id + kwd_no'])
    body += svg_box(795, 75, 280, 200, 'kra_keywords', ['PK kwd_no text', 'data jsonb', 'hit_count bigint', 'last_hit text'])
    body += svg_box(180, 385, 280, 160, 'kra_state', ['PK id boolean = true', 'revision bigint', 'columns jsonb'])
    body += svg_box(650, 385, 280, 160, 'kra_settings', ['PK name text', 'value jsonb'])
    body += '<path d="M310 166H405" stroke="#60718c" stroke-width="2" marker-end="url(#arrow)"/>'
    body += svg_text(320, 145, '1 : N', 14)
    body += '<path d="M795 166H700" stroke="#60718c" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#arrow)"/>'
    body += svg_text(700, 145, '논리 관계', 14)
    body += svg_text(32, 590, '실선은 FK 관계입니다. kwd_no와 Auth actor는 물리 외래키가 아닙니다.', 15)
    write_svg('erd.svg', 1105, 620, '물리 ERD와 논리 코드 관계', body)

    body = svg_text(28, 38, '현재 화면의 정보 구조', 23, weight=700)
    panels = [
        (25, 75, 'UI 00 로그인', ['사내 계정 로그인', '이메일 입력', '비밀번호 마스킹 입력', '로그인 버튼', '실패 시 안내, role 확인 후 진입']),
        (595, 75, 'UI 10과 UI 11 분석', ['일반 사용자: 분석하기 | 리포트', '원문 입력  최대 20,000자', '키워드 매칭 방식·옵션과 규칙 요약', '분석 실행  고유 코드 수와 결과 표', '원문 하이라이트와 CSV 다운로드']),
        (25, 395, 'UI 20과 UI 21 리포트', ['최근 7일 Top N  기본 10', '시작과 종료 기간', '키워드별 주간 조회수 표', '리포트 CSV 다운로드', '관리자용 누적 초기화와 주간 제외']),
        (595, 395, 'UI 30~32와 UI 40 관리', ['admin 전용: 키워드 관리 | 사용자 관리', '공통 분석 규칙 편집과 저장', '키워드 추가·편집·업로드·삭제', '드롭다운과 템플릿 다운로드', '계정 목록 조회와 member/admin 역할 지정'])
    ]
    for x, y, title, lines in panels:
        body += svg_box(x, y, 535, 270, title, lines)
    body += svg_text(28, 715, '위 배치는 화면 설계용 도식입니다. 실제 캡처나 픽셀 단위 시안이 아닙니다.', 15)
    write_svg('screens.svg', 1155, 750, '로그인 분석 리포트 관리자 화면 배치도', body)

    body = svg_text(30, 36, '규정 근거 검색 도입안 — 운영 기능 미연결', 23, weight=700)
    body += svg_box(30, 75, 280, 165, '기존 Streamlit 화면 확장', ['국내 화장품·식품·건강기능식품', '제품군 하나와 검사 기준일 선택', '키워드 검사와 규정 검색 분리'])
    body += svg_box(390, 75, 280, 165, '별도 FastAPI — 추가 계획', ['사용자 인증과 호출 제한', '검색 결과·원문 위치 반환', '키워드 API와 장애 분리'])
    body += svg_box(750, 75, 280, 165, '외부 모델 API — 계획', ['관리형 임베딩 API 우선 평가', 'BGE-M3는 검색 품질 비교 후보', '생성 API는 검색 검증 후 연결'])
    body += svg_box(390, 325, 280, 190, 'Supabase — 추가 계획', ['승인된 문서·조항·임베딩', '국가·제품군·조항 적용일 필터', '어휘 + 벡터 검색 순위 결합', '최종 판정 대신 관련 근거 반환'])
    body += svg_box(30, 325, 280, 190, '관리자 자료 준비', ['공식 원문과 버전 확보', '페이지·표·단서·예외 검수', '적용 기간과 출처 승인', '배치 임베딩 후 근거 묶음 전환'])
    body += svg_box(750, 325, 280, 190, '후속 근거 기반 검토', ['외부 API 전송 허용 확인 완료', '원문과 근거만으로 설명 생성', '인용·출력 형식 서버 검증', '추가 정보 확인과 담당자 검토'])
    for path in ('M310 150H385', 'M670 150H745', 'M530 240V320', 'M310 420H385'):
        body += f'<path d="{path}" fill="none" stroke="#60718c" stroke-width="2" marker-end="url(#arrow)"/>'
    body += '<path d="M670 420H745" fill="none" stroke="#60718c" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#arrow)"/>'
    body += svg_text(30, 565, '검색 유사도는 위반 확률이 아닙니다. 자료의 효력·적용 조건·시행일과 제품 정보를 함께 확인합니다.', 15)
    write_svg('regulation_rag.svg', 1060, 600, '규정 검색 추가 계획과 후속 AI 검토 구성', body)


def inline(value):
    value = html.escape(value)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    value = re.sub(r'!\[([^]]*)\]\(([^)]+)\)', r'<figure><img alt="\1" src="\2"><figcaption>\1</figcaption></figure>', value)

    def link(match):
        label, target = match.groups()
        if target.endswith('.md'):
            target = '#' + Path(target).stem
        return f'<a href="{target}">{label}</a>'

    value = re.sub(r'\[([^]]+)\]\(([^)]+)\)', link, value)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)


def markdown(source):
    lines = source.splitlines()
    output = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith('```'):
            language = line[3:].strip()
            code = []
            index += 1
            while index < len(lines) and not lines[index].startswith('```'):
                code.append(lines[index])
                index += 1
            rendered = '<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>'
            if language == 'mermaid':
                rendered = '<details><summary>Mermaid 원본</summary>' + rendered + '</details>'
            output.append(rendered)
            index += 1
            continue
        if line.startswith('#'):
            count = len(line) - len(line.lstrip('#'))
            level = min(count + 1, 6)
            output.append(f'<h{level}>{inline(line[count:].strip())}</h{level}>')
            index += 1
            continue
        if line.startswith('!['):
            output.append(inline(line))
            index += 1
            continue
        if line.startswith('|'):
            rows = []
            while index < len(lines) and lines[index].startswith('|'):
                cells = [x.strip() for x in lines[index].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', x.replace(' ', '')) for x in cells):
                    rows.append(cells)
                index += 1
            if not rows:
                continue
            output.append('<div class="table-scroll"><table><thead><tr>' + ''.join('<th>'+inline(c)+'</th>' for c in rows[0]) + '</tr></thead><tbody>')
            for row in rows[1:]:
                output.append('<tr>' + ''.join('<td>'+inline(c)+'</td>' for c in row) + '</tr>')
            output.append('</tbody></table></div>')
            continue
        if re.match(r'^(- |\d+\. )', line):
            tag = 'ul' if line.startswith('- ') else 'ol'
            output.append('<'+tag+'>')
            pattern = r'^- ' if tag == 'ul' else r'^\d+\. '
            while index < len(lines) and re.match(pattern, lines[index]):
                output.append('<li>'+inline(re.sub(pattern, '', lines[index]))+'</li>')
                index += 1
            output.append('</'+tag+'>')
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r'^(#|\||```|- |\d+\. )', lines[index]):
            paragraph.append(lines[index])
            index += 1
        output.append('<p>'+inline(' '.join(paragraph))+'</p>')
    return '\n'.join(output)


def contracts():
    from api import app
    runtime = app.openapi()
    (OUT / 'openapi.runtime.json').write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding='utf-8')
    design = deepcopy(runtime)
    design['info']['description'] = '현재 구현 기준 문서용 명세. 응답 스키마는 반환 코드에 근거해 보충했으며 서버 response_model 검증은 구현하지 않았습니다.'
    design['x-response-model-validation'] = False
    schemas = design['components']['schemas']
    ref = lambda name: {'$ref': '#/components/schemas/' + name}
    schemas.update({
        'Match': {'type':'object','required':['term','start','end','category','risk','detail','kwd_no'],
                  'properties':{**{k:{'type':'string'} for k in ('term','category','risk','detail')},
                    'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':0},
                    'kwd_no':{'anyOf':[{'type':'string'},{'type':'null'}]}}},
        'AnalysisResponse': {'type':'object','required':['analysis_id','matches','unique_keywords','keyword_revision','offset_unit','end_exclusive','recorded'],
          'properties':{'analysis_id':{'type':'string','format':'uuid'},'matches':{'type':'array','items':ref('Match')},
            'unique_keywords':{'type':'array','items':{'type':'string'}},'keyword_revision':{'type':'integer'},
            'offset_unit':{'type':'string','const':'unicode_codepoint'},'end_exclusive':{'type':'boolean','const':True},'recorded':{'type':'boolean'}}},
        'KeywordRecord': {'type':'object','additionalProperties':{'type':'string'},'description':'원장의 동적 컬럼. 조회수도 문자열로 반환합니다.'},
        'KeywordPage': {'type':'object','required':['total','revision','items'],
          'properties':{'total':{'type':'integer'},'revision':{'type':'integer'},'items':{'type':'array','items':ref('KeywordRecord')}}},
        'TopKeyword': {'type':'object','required':['kwd_no','hit_count','term'],
          'properties':{'kwd_no':{'type':'string'},'hit_count':{'type':'integer'},'term':{'anyOf':[{'type':'string'},{'type':'null'}]}}},
        'TopKeywordsResponse': {'type':'object','required':['items'],'properties':{'items':{'type':'array','items':ref('TopKeyword')}}},
        'StatusResponse': {'type':'object','required':['status'],'properties':{'status':{'type':'string','enum':['ok','ready']}}},
        'ErrorResponse': {'type':'object','required':['detail'],'properties':{'detail':{'type':'string'}}}
    })
    names = {('/healthz','get'):'StatusResponse',('/readyz','get'):'StatusResponse',
             ('/api/v1/analyses','post'):'AnalysisResponse',('/api/v1/analyses/{analysis_id}','get'):'AnalysisResponse',
             ('/api/v1/keywords','get'):'KeywordPage',('/api/v1/reports/top-keywords','get'):'TopKeywordsResponse',
             ('/api/v1/auxiliary-analyses','post'):'AuxiliaryResponse'}
    for (path, method), name in names.items():
        operation = design['paths'][path][method]
        operation['responses']['200']['content'] = {'application/json':{'schema':ref(name)}}
        if path != '/healthz':
            for status, description in {'401':'인증 실패 또는 앱 역할 없음','503':'백엔드 연결 또는 설정 오류'}.items():
                operation['responses'][status] = {'description':description,'content':{'application/json':{'schema':ref('ErrorResponse')}}}
        if path.startswith('/api/v1/analyses'):
            operation['responses']['409'] = {'description':'ID 입력 소유자 또는 revision 충돌','content':{'application/json':{'schema':ref('ErrorResponse')}}}
        if '{analysis_id}' in path:
            operation['responses']['404'] = {'description':'저장된 분석 없음','content':{'application/json':{'schema':ref('ErrorResponse')}}}
    (OUT / 'openapi.json').write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding='utf-8')
    return runtime


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    diagrams()
    runtime = contracts()
    files = [OUT/'README.md'] + sorted(OUT.glob('[0-9][0-9]_*.md'))
    nav = []
    chapters = []
    for path in files:
        source = path.read_text(encoding='utf-8')
        title = source.splitlines()[0].lstrip('# ')
        nav.append(f'<a href="#{path.stem}">{html.escape(title.replace("Keyword Risk Analyzer ",""))}</a>')
        chapters.append(f'<section class="chapter" id="{path.stem}">{markdown(source)}</section>')
    css = '''
    :root{--ink:#182438;--muted:#57667b;--line:#d9e1eb;--accent:#214d85}
    *{box-sizing:border-box}body{margin:0;color:var(--ink);background:#f2f5f9;font:15px/1.8 "Malgun Gothic","Apple SD Gothic Neo",sans-serif}
    aside{position:fixed;inset:0 auto 0 0;width:258px;padding:30px 22px;background:#172b49;color:white;overflow:auto}
    aside strong{display:block;font-size:18px;margin-bottom:18px}aside a{display:block;color:#d8e6f8;text-decoration:none;padding:9px 0;line-height:1.6;font-size:13px}
    aside .meta{font-size:12px;color:#c5d4e8;margin-top:25px}main{max-width:1150px;margin:0 auto 0 258px;padding:42px 42px 70px}
    .cover,.chapter{background:white;padding:38px 44px;margin-bottom:25px;border:1px solid var(--line);border-radius:10px}
    .cover h1{font-size:31px;margin:8px 0 14px;letter-spacing:-1px}.eyebrow{font-size:13px;letter-spacing:1px;color:var(--accent);font-weight:bold}
    .cover p{color:var(--muted)}h2{font-size:26px;line-height:1.45;margin:0 0 12px;letter-spacing:-.6px}h3{font-size:20px;margin:34px 0 10px}h4{font-size:17px;margin:25px 0 8px}
    p{margin:11px 0}a{color:var(--accent);overflow-wrap:anywhere}li{margin:6px 0}code{font:13px/1.7 Consolas,"Malgun Gothic",monospace;background:#edf2f7;padding:2px 4px;overflow-wrap:anywhere}
    pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7fa;border:1px solid var(--line);padding:17px 18px;border-radius:5px;font-size:12px;line-height:1.7}pre code{background:none;padding:0}
    .table-scroll{overflow-x:auto;margin:18px 0 24px}table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.75}th,td{border:1px solid #d9d9d9;padding:9px 11px;text-align:left;vertical-align:middle;overflow-wrap:anywhere}
    th{background:#e7eef8;color:#172b49;font-weight:700}tbody tr:nth-child(even){background:#f8fafc}figure{margin:24px 0}img{max-width:100%;height:auto;display:block}figcaption{font-size:12px;color:var(--muted);margin-top:8px}
    details{margin:18px 0}summary{cursor:pointer;font-size:13px;color:var(--muted)}button{border:1px solid var(--line);background:white;color:var(--accent);padding:10px 18px;border-radius:5px;font:inherit;cursor:pointer}
    .links{display:flex;gap:17px;flex-wrap:wrap;font-size:13px}.chapter{scroll-margin-top:20px}
    @media(max-width:950px){aside{position:relative;width:auto}aside a{display:inline-block;margin-right:18px}main{margin:0;padding:18px}.cover,.chapter{padding:25px 22px}h2{font-size:23px}}
    @media print{@page{size:A4;margin:17mm 15mm}body{background:white;font-size:10pt;line-height:1.65}aside,.no-print{display:none}main{margin:0;padding:0;max-width:none}.cover,.chapter{border:0;border-radius:0;padding:0;margin:0}.cover{margin-bottom:25px}.chapter{break-before:page}h2{font-size:20pt}h3{font-size:14pt}h4{font-size:12pt}h2,h3,h4{break-after:avoid}table{font-size:8.3pt}th,td{padding:5px 7px}thead{display:table-header-group}tr{break-inside:avoid}pre{font-size:8pt}img{max-height:220mm}a{color:inherit;text-decoration:none}.table-scroll{overflow:visible}figure{break-inside:avoid}details{display:none}}
    '''
    html_doc = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Keyword Risk Analyzer 통합 설계서</title><style>{css}</style></head><body>
    <aside><strong>Keyword Risk Analyzer<br>설계 문서</strong>{''.join(nav)}<div class="meta">버전 1.0<br>구현 기준: 2026년 10월 21일<br>매칭 안내 갱신: 10월 22일<br>규정 검색 제안 갱신: 10월 22일</div></aside>
    <main><header class="cover"><div class="eyebrow">SYSTEM DESIGN DOCUMENTATION</div><h1>Keyword Risk Analyzer 통합 설계서</h1><p>시스템 구조부터 API 화면 Supabase 분석 규칙과 운영 검수까지 연결한 개발 인수인계 문서입니다.</p><p>버전 1.0 · 구현 기준 2026년 10월 21일 · Streamlit + FastAPI + Supabase</p><p>매칭 옵션 안내와 설계 검토는 2026년 10월 22일 재현 결과를 반영했습니다.</p><p>규정 검색 도입 제안은 2026년 10월 22일 사용자 확정 범위를 반영했습니다.</p><div class="links no-print"><a href="openapi.json">문서용 OpenAPI</a><a href="openapi.runtime.json">런타임 원본 OpenAPI</a><a href="README.md">개별 문서 안내</a><button onclick="window.print()">인쇄</button></div></header>{''.join(chapters)}</main></body></html>'''
    (OUT / 'design_book.html').write_text(html_doc, encoding='utf-8')
    source_files = ['keyword_app2_fixed271.py','keyword_app2_fixed270.py','CHANGELOG.md','matching_engine.py','api.py','service.py','auxiliary_analysis.py',
                    'repository.py','app_config.py','supabase/schema.sql','supabase/fix_reset_counts.sql','render.yaml',
                    'scripts/evaluate_regulation_retrieval.py','data/regulations/source_manifest.json']
    proposed_files = ['07_regulation_rag_design.md', 'reference/regulation_sources.json',
                      'reference/regulation_openapi.proposed.json', 'reference/regulation_eval_cases.jsonl']
    manifest = {'document_version':'1.0','application_version':'FIXED271','previous_ui_version':'FIXED270',
                'basis_date_kst':'2026-10-21',
                'matching_design_updated_kst':'2026-10-22',
                'regulation_design_updated_kst':'2026-10-22',
                'source_hash_format':'SHA-256 of UTF-8 text without BOM, with CRLF/CR normalized to LF',
                'runtime_openapi':runtime['openapi'],'runtime_path_count':len(runtime['paths']),
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest() for p in source_files},
                'proposed_artifacts_sha256':{p:hashlib.sha256((OUT/p).read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest() for p in proposed_files}}
    (OUT / 'source_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    reference = OUT / 'reference'
    reference.mkdir(exist_ok=True)
    for name in ('schema.sql','fix_reset_counts.sql'):
        (reference/name).write_bytes((ROOT/'supabase'/name).read_bytes())
    archive = ROOT/'docs'/'keyword_risk_analyzer_design_v1.zip'
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
        for path in sorted(OUT.rglob('*')):
            if path.is_file():
                bundle.write(path, path.relative_to(OUT.parent))
    print(json.dumps({'chapters':len(files)-1,'html':str(OUT/'design_book.html'),
                      'api_paths':len(runtime['paths']),'archive':str(archive)},ensure_ascii=True))


if __name__ == '__main__':
    build()
