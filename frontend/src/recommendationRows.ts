import type { NormalizationRecommendation } from './api'

export function insertRecommendation(
  rows: NormalizationRecommendation[], row: NormalizationRecommendation,
  selectedIds: string[], position: 'end' | 'before' | 'after',
): NormalizationRecommendation[] {
  if (position === 'end') return [...rows, row]
  const anchor = selectedIds.length === 1
    ? rows.findIndex(item => item.recommendation_id === selectedIds[0]) : -1
  if (anchor < 0) throw new Error('삽입 위치로 사용할 행을 하나만 선택하세요.')
  const index = anchor + (position === 'after' ? 1 : 0)
  return [...rows.slice(0, index), row, ...rows.slice(index)]
}
