from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.pdfgen.canvas import Canvas
from xml.sax.saxutils import escape

OUT = 'output/pdf/repository-structure-and-environments.pdf'
pdfmetrics.registerFont(TTFont('Malgun', 'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold', 'C:/Windows/Fonts/malgunbd.ttf'))
NAVY = colors.HexColor('#17324D')
BLUE = colors.HexColor('#2563EB')
PALE = colors.HexColor('#EFF6FF')
INK = colors.HexColor('#1F2937')
MUTED = colors.HexColor('#64748B')
LINE = colors.HexColor('#D8E1EA')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleKo', fontName='MalgunBold', fontSize=23, leading=31, textColor=NAVY, spaceAfter=8))
styles.add(ParagraphStyle(name='SubKo', fontName='Malgun', fontSize=10, leading=16, textColor=MUTED, spaceAfter=14))
styles.add(ParagraphStyle(name='H1Ko', fontName='MalgunBold', fontSize=15, leading=21, textColor=NAVY, spaceBefore=6, spaceAfter=8))
styles.add(ParagraphStyle(name='H2Ko', fontName='MalgunBold', fontSize=11, leading=16, textColor=BLUE, spaceBefore=4, spaceAfter=4))
styles.add(ParagraphStyle(name='BodyKo', fontName='Malgun', fontSize=9.4, leading=15, textColor=INK, spaceAfter=5))
styles.add(ParagraphStyle(name='SmallKo', fontName='Malgun', fontSize=8, leading=12, textColor=MUTED))
styles.add(ParagraphStyle(name='CellKo', fontName='Malgun', fontSize=8.2, leading=12, textColor=INK))
styles.add(ParagraphStyle(name='CellHeadKo', fontName='MalgunBold', fontSize=8.3, leading=12, textColor=colors.white))
styles.add(ParagraphStyle(name='CodeKo', fontName='Malgun', fontSize=8.2, leading=13, textColor=INK, backColor=PALE, borderPadding=8, leftIndent=5, rightIndent=5, spaceBefore=4, spaceAfter=8))

class NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.setFont('Malgun', 8)
            self.setFillColor(MUTED)
            self.drawString(18*mm, 12*mm, 'Keyword Risk Analyzer | 레포 구조 안내')
            self.drawRightString(A4[0]-18*mm, 12*mm, f'{self._pageNumber} / {total}')
            Canvas.showPage(self)
        Canvas.save(self)

def p(txt, style='BodyKo'):
    return Paragraph(txt, styles[style])

def bullet(txt):
    return p('•&nbsp;&nbsp;' + txt)

def make_table(rows, widths, header=True):
    data=[]
    for ri,row in enumerate(rows):
        data.append([p(escape(str(cell)), 'CellHeadKo' if header and ri==0 else 'CellKo') for cell in row])
    t=Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign='LEFT')
    cmds=[('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),0.45,LINE),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]
    if header: cmds.append(('BACKGROUND',(0,0),(-1,0),NAVY))
    for r in range(1 if header else 0,len(rows)):
        if (r-(1 if header else 0))%2==1: cmds.append(('BACKGROUND',(0,r),(-1,r),colors.HexColor('#F8FAFC')))
    t.setStyle(TableStyle(cmds))
    return t

story=[]
story += [p('레포 구조와<br/>테스트·운영 환경', 'TitleKo'), p('Keyword Risk Analyzer | 현재 작업 폴더의 파일 구성과 실행 방식 요약', 'SubKo')]
story += [p('핵심 요약','H1Ko'), p('이 저장소는 테스트용 코드와 운영용 코드를 폴더별로 복제해 둔 구조가 아닙니다. 애플리케이션 코드는 대부분 공유하고, 실행 설정과 데이터 연결 대상(Supabase)으로 환경을 나눕니다. 화면은 Streamlit과 React 두 종류가 있지만 현재 운영 화면으로 설명된 것은 Streamlit입니다.')]
story += [make_table([
 ['구분','현재 레포에서의 의미'],
 ['Streamlit','현재 운영 UI. run_latest.ps1과 Streamlit Cloud 진입점이 가장 높은 번호의 앱 파일을 선택합니다. 현재는 keyword_app2_fixed329.py입니다.'],
 ['React','frontend/에 있는 별도 React·TypeScript UI. README 기준으로 운영 데이터 검증 전 미리보기·검증 단계입니다.'],
 ['테스트 환경','테스트 전용 시작 스크립트가 로컬 Supabase와 테스트 계정을 사용합니다. 운영 데이터와 분리된 로컬 스택입니다.'],
 ['운영 환경','공유 애플리케이션 코드가 운영 Supabase 설정을 읽어 연결합니다. 비밀 키는 저장소에 커밋하지 않는 구조입니다.'],
], [33*mm, 139*mm])]
story += [Spacer(1,7), p('화면과 데이터 연결 흐름','H1Ko')]
story += [p('<b>현재 운영 UI 흐름</b>','H2Ko'), p('브라우저 → Streamlit(최신 FIXED 앱) → service.py / matching_engine.py → repository.py → 운영 Supabase')]
story += [p('<b>React UI 흐름</b>','H2Ko'), p('브라우저 → frontend/ (Vite 개발 서버) → FastAPI(api.py) 및 Supabase Auth/Data API')]
story += [p('분석 로직과 저장소 코드는 여러 UI가 공유합니다. 따라서 테스트·운영을 가르는 핵심은 서로 다른 앱 코드라기보다 어떤 환경 설정과 데이터베이스에 연결했는가입니다.')]
story += [PageBreak()]
story += [p('폴더와 주요 파일','TitleKo'), p('레포 루트에서 확인한 주요 디렉터리와 역할', 'SubKo')]
story += [make_table([
 ['경로','역할'],
 ['keyword_app2_fixed288.py ~ fixed329.py','번호별 Streamlit 앱 버전 파일. run_latest.ps1 실행 시 번호가 가장 높은 파일을 고릅니다.'],
 ['streamlit_cloud/app.py','Streamlit Cloud와 로컬에서 공유하는 진입점. 최신 번호 앱을 찾아 실행합니다.'],
 ['frontend/','React·TypeScript UI. src/tabs/는 화면별 구성, src/lib/는 API·Supabase·분석 공통 로직입니다. tests/에 프론트엔드 테스트가 있습니다.'],
 ['api.py','FastAPI 백엔드 진입점. React에서 사용하는 HTTP API를 제공합니다.'],
 ['service.py, matching_engine.py','분석 서비스와 키워드 매칭 로직. UI에서 공통으로 사용합니다.'],
 ['repository.py, app_config.py','CSV/Supabase 저장소 연결 및 환경 설정 로직.'],
 ['scripts/','로컬 테스트 서버 시작, Supabase 연결 확인, 데이터 가져오기, 문서 생성 스크립트.'],
 ['supabase/','Supabase 로컬 설정, 스키마, 시드 데이터, 마이그레이션 및 SQL 업그레이드 파일.'],
 ['tests/','Python·SQL 테스트와 테스트 데이터. frontend/tests/는 프론트엔드 테스트.'],
 ['docs/','시스템·API·화면·DB 설계, QA 체크리스트 및 인수인계 문서.'],
 ['data/','법령 검색을 위한 출처 목록과 문서 스냅샷.'],
 ['requirements*.txt','Python 의존성 목록. requirements.lock.txt는 고정 버전 목록.'],
 ['render.yaml','Render 배포 서비스 설정.'],
], [56*mm, 116*mm])]
story += [Spacer(1,9), p('테스트 환경의 실행 스크립트','H1Ko')]
story += [bullet('<b>start_local_test_supabase.ps1</b>: Docker 기반 로컬 Supabase를 시작하고 테스트용 로컬 관리자 계정을 준비합니다.'), bullet('<b>start_local_test_api.ps1</b>: 테스트 환경 파일이 로컬 Supabase를 가리키는지 확인한 다음 API를 시작합니다.'), bullet('<b>start_local_test_frontend.ps1</b>: 프론트엔드가 로컬 Supabase와 로컬 API를 바라보는지 확인한 다음 Vite를 시작합니다.')]
story += [PageBreak()]
story += [p('실행 설정과 현재 확인 사항','TitleKo'), p('환경 파일, 로컬 실행 명령, 이번 폴더 점검 결과', 'SubKo')]
story += [p('설정 파일로 환경을 나누는 방식','H1Ko'), bullet('<b>.env.test.local</b>과 <b>frontend/.env.test.local</b>은 로컬 테스트 연결에 사용됩니다. .gitignore에서 제외되어 저장소에 커밋되지 않습니다.'), bullet('<b>.env</b>는 기본 백엔드 설정 파일로 사용됩니다. 앱 설정 코드는 STORAGE_BACKEND 값에 따라 CSV 또는 Supabase를 선택합니다.'), bullet('배포 환경에서는 서비스 환경 변수나 Streamlit secrets를 설정할 수 있습니다. Supabase 비밀 키는 프론트엔드 VITE_ 변수에 넣지 않아야 합니다.')]
story += [p('대표적인 로컬 실행 흐름','H1Ko')]
story += [p('운영 설정을 쓰는 Streamlit 로컬 실행','H2Ko'), p(r'.\run_latest.ps1', 'CodeKo'), p('문서상 이 스크립트는 Supabase 연결을 먼저 확인한 후 최신 Streamlit 앱을 실행합니다. 테스트용 Supabase를 시작하는 스크립트와는 별개입니다.')]
story += [p('React 테스트 실행','H2Ko'), p(r'1. scripts\start_local_test_supabase.ps1<br/>2. scripts\start_local_test_api.ps1<br/>3. scripts\start_local_test_frontend.ps1', 'CodeKo'), p('각 프로세스는 별도 터미널에서 실행하도록 안내되어 있습니다. React 테스트 절차는 로컬 Supabase 데이터베이스를 사용합니다.')]
story += [p('이번 작업 폴더에서 확인한 점','H1Ko'), bullet('테스트용 환경 파일은 존재하지만 운영용 .env와 프론트엔드 운영 환경 변수는 확인되지 않았습니다.'), bullet('따라서 이 폴더의 현재 설정만으로는 운영 Supabase를 사용하는 React 로컬 서버를 구성할 수 없습니다.'), bullet('README는 React 화면이 운영 데이터 기준으로 검증될 때까지 기존 Streamlit UI를 운영 화면으로 유지한다고 설명합니다.'), p('참고: 이 문서는 현재 작업 폴더의 파일과 README·실행 스크립트를 바탕으로 정리했습니다. 비밀 설정 값 자체는 출력하거나 문서에 포함하지 않았습니다.', 'SmallKo')]

doc=SimpleDocTemplate(OUT, pagesize=A4, rightMargin=19*mm, leftMargin=19*mm, topMargin=17*mm, bottomMargin=21*mm, title='레포 구조와 테스트·운영 환경', author='OpenAI')
doc.build(story, canvasmaker=NumberedCanvas)
print(OUT)
