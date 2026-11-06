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
  const alternativeColumn = '\uB300\uCCB4\uD0A4\uC6CC\uB4DC'
  const evidenceColumn = '\uC99D\uBE59\uC790\uB8CC\uC720\uD615'
  const periodCountColumn = '\uAE30\uAC04\uB0B4_\uC870\uD68C\uC218'
  const lastSearchColumn = '\uB9C8\uC9C0\uB9C9 \uCD9C\uB825\uC77C\uC790'
  const countColumn = keywordColumns.includes(alternativeColumn)
    ? alternativeColumn : keywordColumns.includes(evidenceColumn) ? evidenceColumn : ''
  const insertAt = countColumn ? keywordColumns.indexOf(countColumn) + 1 : keywordColumns.length
  const columns = [...keywordColumns.slice(0, insertAt), periodCountColumn,
    ...keywordColumns.slice(insertAt)]
  const rows = [
    ['\uAC80\uC0C9\uC21C\uC704', ...columns.map(column => column === lastSearchColumn
      ? '\uB9C8\uC9C0\uB9C9 \uAC80\uC0C9\uC77C\uC790' : column)],
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
