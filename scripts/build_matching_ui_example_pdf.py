"""Render two illustrative Keyword Risk Analyzer UI pages as a PDF."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'pdf' / 'keyword-risk-analyzer-matching-ui-example.pdf'
W, H = 1152, 648

pdfmetrics.registerFont(TTFont('Malgun', 'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('Malgun-Bold', 'C:/Windows/Fonts/malgunbd.ttf'))

BG = '#F7F3ED'
SIDEBAR = '#F3EEE7'
PANEL = '#FFFDFA'
INPUT = '#FCFAF7'
TEXT = '#2E2C2A'
MUTED = '#77716B'
BORDER = '#E8DFD5'
CORAL = '#D96F5D'
CORAL_LIGHT = '#FBECE7'


def color(value):
    return colors.HexColor(value)


def box(c, x, y, w, h, fill, stroke=None, radius=0, line_width=1):
    c.setLineWidth(line_width)
    c.setFillColor(color(fill))
    c.setStrokeColor(color(stroke or fill))
    c.roundRect(x, H-y-h, w, h, radius, stroke=int(stroke is not None), fill=1)


def rule(c, x1, y1, x2, y2, stroke=BORDER, width=1):
    c.setStrokeColor(color(stroke))
    c.setLineWidth(width)
    c.line(x1, H-y1, x2, H-y2)


def txt(c, x, y, value, size=10, bold=False, fill=TEXT):
    c.setFont('Malgun-Bold' if bold else 'Malgun', size)
    c.setFillColor(color(fill))
    c.drawString(x, H-y-size, value)


def right(c, x, y, value, size=10, bold=False, fill=TEXT):
    c.setFont('Malgun-Bold' if bold else 'Malgun', size)
    c.setFillColor(color(fill))
    c.drawRightString(x, H-y-size, value)


def pill(c, x, y, label, fill, text_color, width=None, size=8):
    width = width or pdfmetrics.stringWidth(label, 'Malgun-Bold', size) + 18
    box(c, x, y, width, 22, fill, radius=10)
    txt(c, x+9, y+5, label, size, True, text_color)
    return width


def app_shell(c, page_number, section_title, note):
    box(c, 0, 0, W, H, BG)
    txt(c, 38, 21, f'{page_number:02d}  /  KEYWORD RISK ANALYZER', 9, True, '#A66A5D')
    txt(c, 38, 42, section_title, 21, True)
    right(c, 1114, 45, note, 8, fill=MUTED)

    # Workspace frame mirrors the current React shell, at presentation scale.
    box(c, 38, 100, 1076, 500, PANEL, BORDER, 13)
    box(c, 38, 100, 180, 500, SIDEBAR, radius=13)
    box(c, 205, 100, 13, 500, SIDEBAR)
    rule(c, 218, 100, 218, 600)
    box(c, 61, 125, 32, 32, CORAL, radius=8)
    txt(c, 71, 131, 'K', 18, True, '#FFFFFF')
    txt(c, 103, 128, '키워드 리스크', 10, True)
    txt(c, 103, 143, 'ANALYZER', 6.8, True, '#9A756A')
    txt(c, 60, 204, '계정', 8, True, '#A66A5D')
    txt(c, 60, 222, 'reviewer@example.com', 8, fill='#3C3733')
    box(c, 60, 246, 136, 27, PANEL, BORDER, 7)
    txt(c, 102, 252, '로그아웃', 8)
    rule(c, 60, 291, 195, 291)
    txt(c, 60, 307, '데이터 저장소', 8, True, '#A66A5D')
    txt(c, 60, 326, 'Supabase 공유 저장소', 8, fill=MUTED)
    box(c, 60, 350, 136, 29, PANEL, BORDER, 7)
    txt(c, 82, 357, '최신 데이터 불러오기', 8)

    txt(c, 245, 124, 'KEYWORD RISK WORKSPACE', 7, True, '#A66A5D')
    txt(c, 245, 143, '광고심의 자동화 솔루션', 17, True)
    pill(c, 991, 134, 'UI EXAMPLE', '#F2E8DF', '#776C63', 95, 8)
    tabs = [('스크립트 분석', 245), ('이미지 OCR분석', 346), ('미매칭 후보군', 460),
            ('키워드 문의', 567), ('심의 Chat-bot', 657), ('분석리포트', 773)]
    rule(c, 245, 213, 1086, 213)
    for label, x in tabs:
        txt(c, x, 187, label, 8.4, label == '스크립트 분석', CORAL if label == '스크립트 분석' else '#746D66')
    rule(c, 245, 212, 331, 212, CORAL, 2.2)
    box(c, 244, 229, 842, 349, PANEL, '#EBE2D9', 12)


def current_page(c):
    app_shell(c, 1, '현재 UI 구성으로 보는 탐색용 매칭', '가상 데이터 · 실제 실행 화면 캡처 아님')
    txt(c, 266, 245, '스크립트 입력', 11, True)
    box(c, 266, 267, 798, 47, INPUT, '#E5DBD1', 7)
    txt(c, 281, 280, '피부과 방문 안내', 12)
    txt(c, 266, 326, '분석 실행', 11, True)
    box(c, 266, 351, 191, 42, INPUT, BORDER, 7)
    txt(c, 278, 356, '상품카테고리', 7, fill=MUTED)
    txt(c, 278, 369, '화장품', 9)
    box(c, 470, 351, 191, 42, INPUT, BORDER, 7)
    txt(c, 482, 356, '리스크 등급', 7, fill=MUTED)
    txt(c, 482, 369, '전체', 9)
    box(c, 674, 351, 390, 42, INPUT, BORDER, 7)
    txt(c, 686, 356, '키워드 매칭 방식', 7, fill=MUTED)
    txt(c, 686, 369, '글자 수 매칭 - 탐색용  ·  최소 2글자', 9)
    box(c, 266, 404, 124, 31, CORAL, radius=7)
    txt(c, 283, 412, '텍스트 분석하기', 8.5, True, '#FFFFFF')
    txt(c, 406, 412, '등록 키워드의 일부 글자가 일치한 예시입니다.', 8, fill=MUTED)
    txt(c, 266, 446, '분석 결과', 10, True)
    pill(c, 337, 444, '가상 키워드 DB', '#F2E8DF', '#776C63', 103, 7.6)
    box(c, 266, 471, 798, 29, '#F5EEE7', BORDER, 4)
    txt(c, 279, 479, '키워드명', 8, True)
    txt(c, 487, 479, '상품카테고리', 8, True)
    txt(c, 672, 479, '리스크 등급', 8, True)
    txt(c, 856, 479, '세부 심의기준', 8, True)
    box(c, 266, 500, 798, 31, PANEL, BORDER, 4)
    txt(c, 279, 509, '피부 보습', 9)
    txt(c, 487, 509, '화장품', 9)
    txt(c, 672, 509, '예시 등급', 9, fill=MUTED)
    txt(c, 856, 509, '담당자 확인', 9, fill=MUTED)
    txt(c, 266, 540, '하이라이트 미리보기', 9, True)
    pill(c, 412, 538, '피부', CORAL_LIGHT, '#A94D40', 48, 8)
    txt(c, 466, 542, '과 방문 안내', 9)
    right(c, 1057, 542, '일치 구간: 피부 · 2글자', 8, fill=MUTED)
    txt(c, 38, 613, '현재 예시: 짧은 공통 글자 조각도 탐색 결과에 나타날 수 있습니다.', 9, fill=MUTED)
    right(c, 1114, 613, '01 / 02', 9, True, '#A66A5D')
    c.showPage()


def proposed_page(c):
    app_shell(c, 2, '현행 디자인을 유지한 결과 구분 시안', '제안 기능 · 아직 구현되지 않은 화면')
    txt(c, 266, 247, '탐지 경로별 결과', 12, True)
    pill(c, 906, 243, '개선 제안 시안', CORAL_LIGHT, '#A94D40', 141, 8)
    txt(c, 266, 274, '같은 결과 영역에서 매칭 근거를 구분해 검토합니다.', 8.5, fill=MUTED)

    box(c, 266, 300, 798, 103, '#FFF8F5', '#E9D2C9', 9)
    box(c, 266, 300, 5, 103, CORAL, radius=2)
    pill(c, 284, 312, 'A  검수 별칭', CORAL_LIGHT, '#A94D40', 107, 8)
    pill(c, 401, 312, '건강기능식품', '#F2E8DF', '#776C63', 98, 8)
    txt(c, 284, 343, '광고 문구', 8, fill=MUTED)
    txt(c, 360, 340, '몸무게 줄이기', 12, True)
    txt(c, 284, 372, '관리자가 검수한 별칭 → 등록어 ‘체중 감량’의 기준 확인', 9)
    right(c, 1044, 371, '원문 위치 연결', 8, True, '#A94D40')

    box(c, 266, 416, 798, 103, '#FAF8F5', BORDER, 9)
    box(c, 266, 416, 5, 103, '#C6A287', radius=2)
    pill(c, 284, 428, 'B  탐색 후보', '#F1EBE5', '#65584E', 107, 8)
    pill(c, 401, 428, '화장품', '#F2E8DF', '#776C63', 76, 8)
    txt(c, 284, 459, '광고 문구', 8, fill=MUTED)
    txt(c, 360, 456, '피부과 방문 안내', 12, True)
    txt(c, 284, 488, '‘피부 보습’과 ‘피부’ 2글자 일치 → 문맥 확인 필요', 9)
    right(c, 1044, 487, '탐색 경로 표시', 8, True, '#776C63')

    box(c, 266, 532, 798, 31, '#F3EEE7', radius=6)
    txt(c, 282, 541, '검토 우선순위는 매칭 근거의 강도입니다. 위험 등급이나 법적 판단을 자동 변경하지 않습니다.', 8.5, fill='#65584E')
    txt(c, 38, 613, '제안 예시: 검수 별칭과 짧은 문자열 후보를 별도 경로로 표시하며, 의미 유사 후보는 확정 탐지와 분리합니다.', 8.4, fill=MUTED)
    right(c, 1114, 613, '02 / 02', 9, True, '#A66A5D')
    c.showPage()


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=(W, H), pageCompression=1)
    c.setTitle('Keyword Risk Analyzer — 매칭 UI 예시')
    c.setAuthor('Keyword Risk Analyzer')
    current_page(c)
    proposed_page(c)
    c.save()
    print(OUT)


if __name__ == '__main__':
    main()
