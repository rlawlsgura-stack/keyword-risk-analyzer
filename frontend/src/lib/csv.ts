/**
 * CSV output that matches pandas `DataFrame.to_csv(index=False, encoding="utf-8-sig")`
 * as used by the Streamlit app: UTF-8 BOM, comma separator, minimal quoting and
 * "\n" line endings. Values are written unchanged (no spreadsheet-formula prefixing),
 * so downloaded files contain the same cell values as the Streamlit downloads.
 */
export function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv(columns: readonly string[], rows: readonly Record<string, unknown>[]): string {
  const lines = [columns.map(csvCell).join(',')]
  for (const row of rows) lines.push(columns.map(column => csvCell(row[column])).join(','))
  return '﻿' + lines.join('\n') + '\n'
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadCsv(filename: string, columns: readonly string[], rows: readonly Record<string, unknown>[]) {
  downloadBlob(new Blob([toCsv(columns, rows)], { type: 'text/csv;charset=utf-8' }), filename)
}
