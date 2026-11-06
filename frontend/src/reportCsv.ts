type ReportItem = {
  search_rank: number
  hit_count: number
  keyword_data?: Record<string, string>
}

function csvCell(value: string) {
  const safeValue = /^[\u0000-\u0020]*[=+\-@]/.test(value) ? `'${value}` : value
  return `"${safeValue.replaceAll('"', '""')}"`
}

export function buildTopKeywordCsv(
  reportItems: ReportItem[],
  formatDate: (value: string) => string,
) {
  const keywordColumns = reportItems[0]?.keyword_data
    ? Object.keys(reportItems[0].keyword_data) : []
  const alternativeColumn = '대체키워드'
  const evidenceColumn = '증빙자료유형'
  const periodCountColumn = '기간내_조회수'
  const lastSearchColumn = '마지막 출력일자'
  const countColumn = keywordColumns.includes(alternativeColumn)
    ? alternativeColumn : keywordColumns.includes(evidenceColumn) ? evidenceColumn : ''
  const insertAt = countColumn ? keywordColumns.indexOf(countColumn) + 1 : keywordColumns.length
  const columns = [...keywordColumns.slice(0, insertAt), periodCountColumn,
    ...keywordColumns.slice(insertAt)]
  const rows = [
    ['검색순위', ...columns.map(column => column === lastSearchColumn
      ? '마지막 검색일자' : column)],
    ...reportItems.map(item => {
      const values = columns.map(column => column === periodCountColumn
        ? String(item.hit_count) : item.keyword_data?.[column] ?? '')
      const dateIndex = columns.indexOf(lastSearchColumn)
      if (dateIndex >= 0) values[dateIndex] = formatDate(values[dateIndex])
      return [String(item.search_rank), ...values]
    }),
  ]
  return '\uFEFF' + rows.map(row => row.map(csvCell).join(',')).join('\r\n')
}
