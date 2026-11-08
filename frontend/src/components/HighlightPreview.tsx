import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { RISK_BG, type CodeEntry, type Segment, type TooltipRow } from '../lib/highlight.ts'

/**
 * Interactive preview matching the Streamlit component (L4024-4435):
 * click a highlight → toggle its keyword numbers; hover (500 ms) or click a number → detail popup;
 * Ctrl/⌘+click → select every number for the same detected text; Ctrl+C copies the selection; Esc clears.
 */
export function HighlightPreview({ segments }: { segments: Segment[] }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<{ group: string } | null>(null)
  const [popup, setPopup] = useState<{ entry: CodeEntry; anchor: HTMLElement } | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const hoverTimer = useRef(0)
  const hideTimer = useRef(0)

  useEffect(() => { setHidden(new Set()); setSelected(null); setPopup(null) }, [segments])

  const clearTimers = () => { window.clearTimeout(hoverTimer.current); window.clearTimeout(hideTimer.current) }

  const selectedCodes = useCallback(() => {
    if (!selected) return []
    const codes: string[] = []
    for (const s of segments) if (s.kind === 'mark') for (const e of s.entries) {
      if (e.groupKey === selected.group && !hidden.has(e.toggleKey) && !codes.includes(e.code)) codes.push(e.code)
    }
    return codes
  }, [segments, selected, hidden])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setSelected(null); setPopup(null) }
    }
    const onCopy = (e: ClipboardEvent) => {
      const codes = selectedCodes()
      if (!codes.length) return
      e.preventDefault()
      e.clipboardData?.setData('text/plain', codes.join(', '))
    }
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (!boxRef.current?.contains(target) && !document.getElementById('kwd-tt-float')?.contains(target)) setPopup(null)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('copy', onCopy)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('copy', onCopy)
      document.removeEventListener('mousedown', onDown)
    }
  }, [selectedCodes])

  const toggleMark = (entries: CodeEntry[]) => {
    const keys = entries.map(e => e.toggleKey)
    setHidden(prev => {
      const anyVisible = keys.some(k => !prev.has(k))
      const next = new Set(prev)
      keys.forEach(k => (anyVisible ? next.add(k) : next.delete(k)))
      return next
    })
  }

  const onCodeClick = (e: React.MouseEvent<HTMLElement>, entry: CodeEntry) => {
    e.stopPropagation()
    clearTimers()
    if (e.ctrlKey || e.metaKey) {
      setSelected({ group: entry.groupKey })
      setPopup(null)
      return
    }
    const anchor = e.currentTarget
    setPopup(p => (p && p.anchor === anchor ? null : { entry, anchor }))
  }

  return (
    <div ref={boxRef} className="hl-preview" onClick={() => setSelected(null)}
      style={{ border: '1px solid rgba(0,0,0,0.1)', borderRadius: 10, padding: 10, background: 'rgba(255,255,255,.55)' }}>
      <div style={{ maxHeight: 520, overflowY: 'auto', lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {segments.map((s, i) => {
          if (s.kind === 'text') return <span key={i}>{s.text}</span>
          const visible = s.entries.filter(e => !hidden.has(e.toggleKey))
          return (
            <span key={i}>
              {s.lead}
              <span className="hl-mark" tabIndex={0} aria-label="검출 키워드 표시 전환" role="button"
                style={{ background: RISK_BG[s.grade] ?? RISK_BG[0], color: '#000', borderRadius: 2, cursor: 'pointer' }}
                onClick={e => { e.stopPropagation(); toggleMark(s.entries) }}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleMark(s.entries) } }}>
                【<b>{s.core}</b>】
                {visible.length > 0 && (
                  <span className="kwdno-group" style={{ whiteSpace: 'nowrap' }}>(
                    {visible.map((entry, j) => {
                      const picked = selected?.group === entry.groupKey
                      return (
                        <span key={entry.toggleKey}>
                          {j > 0 && ', '}
                          <span role="button" tabIndex={0} aria-label={`${entry.code} 상세 정보`} className="kwdno-link"
                            style={{
                              color: entry.color, textDecoration: 'underline', cursor: 'pointer',
                              ...(picked ? { background: '#b3d4fc', outline: '1px solid #3977c3' } : {}),
                            }}
                            onClick={e => onCodeClick(e, entry)}
                            onKeyDown={e => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault(); e.stopPropagation()
                                const anchor = e.currentTarget
                                setPopup(p => (p && p.anchor === anchor ? null : { entry, anchor }))
                              }
                            }}
                            onMouseEnter={e => {
                              const anchor = e.currentTarget
                              window.clearTimeout(hideTimer.current)
                              hoverTimer.current = window.setTimeout(() => setPopup({ entry, anchor }), 500)
                            }}
                            onMouseLeave={() => {
                              window.clearTimeout(hoverTimer.current)
                              hideTimer.current = window.setTimeout(() => setPopup(null), 180)
                            }}>
                            <b>{entry.token}</b>
                          </span>
                        </span>
                      )
                    })})
                  </span>
                )}
              </span>
              {s.trail}
            </span>
          )
        })}
      </div>
      {popup && <TooltipPopup entry={popup.entry} anchor={popup.anchor}
        onEnter={() => window.clearTimeout(hideTimer.current)}
        onLeave={() => { hideTimer.current = window.setTimeout(() => setPopup(null), 180) }} />}
    </div>
  )
}

function bold(text: string, core: string): ReactNode {
  if (!core) return text
  const i = text.indexOf(core)
  if (i < 0) return text
  return <>{text.slice(0, i)}<strong>{core}</strong>{text.slice(i + core.length)}</>
}

function rowValue(row: TooltipRow): ReactNode {
  if (row.kind === 'plain') return row.value
  return <>입력 문구 ‘{bold(row.matched, row.matchedCore)}’ ↔ DB 등록 키워드 ‘{bold(row.registered, row.registeredCore)}’</>
}

function TooltipPopup({ entry, anchor, onEnter, onLeave }: { entry: CodeEntry; anchor: HTMLElement; onEnter: () => void; onLeave: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number; maxHeight?: number }>({ left: -9999, top: -9999 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const group = (anchor.closest('.kwdno-group') as HTMLElement | null) ?? anchor
    const a = group.getBoundingClientRect()
    const vw = window.innerWidth, vh = window.innerHeight, gap = 8, margin = 8
    const w = el.offsetWidth, h = el.offsetHeight
    const candidates = [
      { left: a.left, top: a.bottom + gap }, { left: a.right - w, top: a.bottom + gap },
      { left: a.left, top: a.top - h - gap }, { left: a.right - w, top: a.top - h - gap },
      { left: a.right + gap, top: a.top }, { left: a.left - w - gap, top: a.top },
      { left: a.right + gap, top: a.bottom - h }, { left: a.left - w - gap, top: a.bottom - h },
    ]
    const fits = candidates.find(c => c.left >= margin && c.top >= margin && c.left + w <= vw - margin && c.top + h <= vh - margin)
    if (fits) { setPos(fits); return }
    const below = vh - a.bottom - gap - margin, above = a.top - gap - margin
    const left = Math.min(Math.max(margin, a.left), vw - w - margin)
    if (below >= above) setPos({ left, top: a.bottom + gap, maxHeight: Math.max(80, below) })
    else setPos({ left, top: margin, maxHeight: Math.max(80, above) })
  }, [entry, anchor])
  const rows = entry.tooltip.length ? entry.tooltip : [{ kind: 'plain', label: 'kwd_no', value: 'tooltip 데이터가 없습니다.' } as TooltipRow]
  return (
    <div id="kwd-tt-float" ref={ref} role="dialog" aria-label={`${entry.code} 상세 정보`} onMouseEnter={onEnter} onMouseLeave={onLeave}
      className="kwd-tooltip"
      style={{ left: pos.left, top: pos.top, maxHeight: pos.maxHeight }}>
      <table className="kwd-tooltip-table">
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <th scope="row">{row.label}</th>
              <td>{rowValue(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
