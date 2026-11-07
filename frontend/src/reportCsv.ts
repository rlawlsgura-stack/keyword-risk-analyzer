type ReportItem = {
  search_rank: number
  hit_count: number
  keyword_data?: Record<string, string>
}

const reportKeywordColumns = [
  'kwd_no',
  '\uD0A4\uC6CC\uB4DC\uBA85',
  '\uC0C1\uD488\uCE74\uD14C\uACE0\uB9AC',
  '\uB9AC\uC2A4\uD06C \uB4F1\uAE09',
  '\uB300\uCCB4\uD0A4\uC6CC\uB4DC',
  '\uB9AC\uC2A4\uD06C \uB4F1\uAE09\uBCC4 \uC138\uBD80 \uC2EC\uC758\uAE30\uC900',
  '\uC99D\uBE59\uC790\uB8CC\uC720\uD615',
  '\uD0A4\uC6CC\uB4DC \uC870\uD68C \uC218(\uB204\uC801\uCE74\uC6B4\uD2B8)',
  '\uB9C8\uC9C0\uB9C9 \uCD9C\uB825\uC77C\uC790',
  '\uD0A4\uC6CC\uB4DC\uB4F1\uB85D\uC778',
  '\uBE44\uACE0',
  '\uD0A4\uC6CC\uB4DC \uB4F1\uB85D\uC77C\uC790',
]

function csvCell(value: string) {
  const safeValue = /^[\u0000-\u0020]*[=+\-@]/.test(value) ? `'${value}` : value
  return `"${safeValue.replaceAll('"', '""')}"`
}

export function buildTopKeywordCsv(
  reportItems: ReportItem[],
  formatDate: (value: string) => string,
) {
  const keywordColumns = reportKeywordColumns
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
