import type { AnalysisMode } from './types.ts'

/** _numbered_help (L2631): one sentence per numbered line; backticks removed for tooltips. */
export function numberedHelp(text: string): string {
  const parts = text.replace(/`/g, '').trim().split(/(?<=[.!?])\s+|\n+/)
  return parts.map(p => p.trim().replace(/^[-\s]+/, '').trim()).filter(Boolean)
    .map((item, i) => `${i + 1}. ${item}`).join('\n')
}

export const MODE_LABELS: Record<AnalysisMode, string> = {
  exact: '키워드 완전 일치',
  similar: '키워드 일부 일치',
  partial: '글자 수 매칭 - 탐색용',
}

export const MODE_DETAILS: Record<AnalysisMode, string> = {
  exact: '등록된 키워드 표현 전체를 문장 안에서 찾습니다.\n\n'
    + '단어 경계를 강제하지 않아 다른 단어 안에 포함된 표현도 검출할 수 있습니다.\n\n'
    + '예시) 등록 키워드: `피부`\n\n'
    + '- O · `피부가 건조하다` → `피부` 검출\n'
    + '- O · `피부과` → 다른 단어 안의 `피부` 검출\n'
    + '- X · `피로` → `피부` 미검출\n\n'
    + '괄호 설명·공백·대소문자·기호 차이는 키워드 매칭 옵션의 선택을 따릅니다.',
  similar: '등록 키워드와 입력 문장을 Kiwi로 분석합니다.\n\n'
    + '양쪽의 내용어 토큰 전체가 같으면 검출합니다.\n\n'
    + '자동으로 나뉘지 않는 전문 용어는 관리자 승인 표현으로 보완합니다.\n\n'
    + '예시) 등록 `노화방지` → `노화` + `방지`\n\n'
    + '- O · `노화 피부` → `노화` 토큰으로 노화방지 검출\n'
    + '- X · 등록 `안티에이징` / 입력 `티에이` → 동일 토큰 없음\n'
    + '- O · 등록 `안티에이징` / 입력 `에이징 관리` → 에이징 승인 시 검출\n\n'
    + '괄호 설명 제외를 끄면 괄호 안 단어도 비교합니다.\n\n'
    + '내용어 한 개만 같아도 관련 후보가 됩니다.\n\n동의어·위반 여부는 판단하지 않습니다.',
  partial: '단어 의미와 경계에 관계없이 연속된 글자 조각을 찾습니다.\n\n'
    + '승인 표현과 Kiwi 경계 검사는 적용하지 않습니다.\n\n'
    + '글자수를 늘리면 짧은 조각으로 인한 결과를 줄일 수 있습니다.\n\n'
    + '예시) 등록 키워드: `안티에이징`\n\n'
    + '- O · 최소 2글자 / 입력 `안티` → 실제 일치 `안티`\n'
    + '- X · 최소 3글자 / 입력 `안티` → 미검출\n'
    + '- O · 최소 3글자 / 입력 `에이징` → 실제 일치 `에이징`\n'
    + '- X · 최소 4글자 / 입력 `에이징` → 미검출',
}

export type NormalizationKey = 'strip_bracket_notes' | 'normalize_whitespace' | 'ignore_case' | 'normalize_symbols'

export const NORMALIZATION_OPTIONS: [NormalizationKey, string, string][] = [
  ['strip_bracket_notes', '등록 키워드의 괄호 설명 제외',
    '등록 키워드에서 괄호 설명을 제외한 표현을 검색합니다.\n\n입력 원문의 괄호를 삭제하는 설정은 아닙니다.\n\n'
    + '예시) 키워드 완전 일치 / 등록: `안티에이징(anti-aging)` / 입력: `안티에이징으로`\n\n- O · 옵션 켬 → `안티에이징` 검출\n- X · 옵션 끔 → 미검출'],
  ['normalize_whitespace', '띄어쓰기·줄바꿈 차이 허용',
    '공백·탭·줄바꿈 차이를 무시하고 비교합니다.\n\n끄면 공백과 줄바꿈을 그대로 비교합니다.\n\n'
    + '예시) 키워드 완전 일치 / 등록: `피부보습` / 입력: `피부 보습`\n\n- O · 옵션 켬 → `피부 보습` 검출\n- X · 옵션 끔 → 미검출'],
  ['ignore_case', '영문 대소문자 무시',
    '영문 대소문자를 구분하지 않고 비교합니다.\n\n끄면 대소문자가 같아야 일치합니다.\n\n'
    + '예시) 키워드 완전 일치 / 등록: `Spot` / 입력: `spot`\n\n- O · 옵션 켬 → `spot` 검출\n- X · 옵션 끔 → 미검출'],
  ['normalize_symbols', '설정된 기호를 공백으로 처리',
    '관리자 공통 목록에 있는 기호만 공백으로 바꿉니다.\n\n붙여 쓴 표현까지 비교하려면 띄어쓰기·줄바꿈 차이 허용도 켜세요.\n\n'
    + '예시) 키워드 완전 일치 / 공통 기호: `&` / 등록: `피부 보습` / 입력: `피부&보습`\n\n- O · 옵션 켬 → `피부&보습` 검출\n- X · 옵션 끔 → 미검출'],
]

export const PARTIAL_LEN_HELP = '예시) 등록 `안티에이징` / 입력 `에이징 관리가 필요하다`\n\n- O · 최소 3글자 → `에이징` 검출\n- X · 최소 4글자 → 미검출\n\n'
  + '옵션에 따라 공백·기호를 처리한 뒤의 글자수를 기준으로 합니다.\n\n등록 키워드 자체가 최소 글자수보다 짧으면 검색하지 않습니다.'

export const HIGHLIGHT_HELP = '검출 문구를 클릭하면 같은 검출 대상의 번호 표시를 전환합니다.\n\n'
  + '번호 클릭은 상세 정보, Ctrl+클릭은 같은 검출 대상의 번호를 선택합니다. 선택 후 Ctrl+C로 복사할 수 있습니다.\n\n'
  + '색상은 연결된 키워드의 리스크 등급을 나타냅니다.\n'
  + '연분홍: 1등급(사용금지) · 하늘색: 2등급(대체키워드사용) · 연보라: 3등급(조건부사용)\n'
  + '연두빛 초록: 4등급(사용가능) · 연두색: 5등급(테스트 등급)\n\n'
  + '노란색은 같은 검출 문구에 서로 다른 등급의 키워드가 연결되었거나, 등급을 확인할 수 없을 때 표시됩니다.\n'
  + '하나의 유효 등급만 연결된 경우 해당 등급의 색으로 표시합니다. 자세한 기준은 결과 표의 리스크 등급을 확인하세요.'

export function rulesSummary(mode: AnalysisMode, partialMinLen: number, opts: Record<NormalizationKey, boolean>, symbols: string[]): string {
  const lines = [`키워드 매칭 방식: ${MODE_LABELS[mode]}`]
  if (mode === 'partial') lines.push(`최소 일치 글자수: ${partialMinLen}글자`)
  for (const [key, label] of NORMALIZATION_OPTIONS) lines.push(`${label}: ${opts[key] ? '켜짐' : '꺼짐'}`)
  if (mode === 'similar') {
    lines.push('양쪽 Kiwi 내용어 토큰 전체 비교 + 승인 표현 보완 + 원문 단어 경계 검사')
    lines.push('조사·어미 허용 목록과 임의 글자 조각 검색은 적용하지 않습니다.')
  } else {
    lines.push('뒤에 붙는 말 허용 목록: 이 검사 방식에는 적용하지 않음')
  }
  if (opts.normalize_symbols) lines.push(`비교 시 처리할 기호: ${symbols.join(' · ') || '없음'}`)
  else lines.push('기호 처리가 꺼져 있어 공통 기호 목록은 적용하지 않습니다.')
  lines.push('목록은 관리자 공통 설정입니다. 분석 실행 시 저장된 최신 규칙을 다시 불러옵니다.')
  return numberedHelp(lines.join('\n\n'))
}
