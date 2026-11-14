import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'

/* ---------- small primitives ---------- */
export function Help({ text }: { text?: string }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const closeOutside = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [open])
  if (!text) return null
  return <button ref={ref} type="button" className="help" aria-label="도움말 보기" aria-expanded={open}
    onClick={event => { event.preventDefault(); event.stopPropagation(); setOpen(value => !value) }}>
    ?<span className={`help-tooltip${open ? ' open' : ''}`} role="tooltip">{text}</span>
  </button>
}

export function FieldLabel({ label, help, htmlFor }: { label: ReactNode; help?: string; htmlFor?: string }) {
  if (!label) return null
  return <label className="field" htmlFor={htmlFor}>{label}<Help text={help} /></label>
}

export type AlertKind = 'success' | 'info' | 'warning' | 'error'
export function Alert({ kind, children }: { kind: AlertKind; children: ReactNode }) {
  if (children === null || children === undefined || children === '') return null
  const icon = { success: '✅', info: 'ℹ️', warning: '⚠️', error: '⛔' }[kind]
  return <div className={`alert ${kind}`} role={kind === 'error' ? 'alert' : 'status'}><span aria-hidden>{icon} </span>{children}</div>
}

export type Notice = { kind: AlertKind; text: string } | null
export function NoticeView({ notice }: { notice: Notice }) {
  return notice ? <Alert kind={notice.kind}>{notice.text}</Alert> : null
}

export function Spinner({ text }: { text?: string }) {
  return <div className="row center tight" style={{ margin: '.5rem 0' }}><span className="spinner" />{text && <span className="caption">{text}</span>}</div>
}

export function Button({ children, onClick, primary, disabled, small, full, title, className, type = 'button' }: {
  children: ReactNode; onClick?: () => void; primary?: boolean; disabled?: boolean; small?: boolean; full?: boolean; title?: string
  className?: string; type?: 'button' | 'submit'
}) {
  const cls = ['btn', primary && 'primary', small && 'small', full && 'full', className].filter(Boolean).join(' ')
  return <button type={type} className={cls} onClick={onClick} disabled={disabled} title={title}>{children}</button>
}

export function TextInput({ label, value, onChange, help, placeholder, type = 'text', disabled, maxLength, onEnter, autoComplete }: {
  label?: ReactNode; value: string; onChange: (v: string) => void; help?: string; placeholder?: string
  type?: 'text' | 'email' | 'password' | 'date'; disabled?: boolean; maxLength?: number; onEnter?: () => void; autoComplete?: string
}) {
  const id = useId()
  return (
    <div>
      <FieldLabel label={label} help={help} htmlFor={id} />
      <input id={id} type={type} value={value} placeholder={placeholder} disabled={disabled} maxLength={maxLength}
        autoComplete={autoComplete}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && onEnter) { e.preventDefault(); onEnter() } }} />
    </div>
  )
}

export function NumberInput({ label, value, onChange, min, max, step = 1, help, disabled }: {
  label?: ReactNode; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; help?: string; disabled?: boolean
}) {
  const id = useId()
  const [text, setText] = useState(String(value))
  useEffect(() => setText(String(value)), [value])
  const commit = (raw: string) => {
    let n = Number(raw)
    if (!Number.isFinite(n)) n = value
    if (min !== undefined) n = Math.max(min, n)
    if (max !== undefined) n = Math.min(max, n)
    n = Math.round(n / step) * step
    setText(String(n))
    if (n !== value) onChange(n)
  }
  const bump = (d: number) => commit(String(value + d))
  return (
    <div>
      <FieldLabel label={label} help={help} htmlFor={id} />
      <div className="row tight center" style={{ flexWrap: 'nowrap' }}>
        <input id={id} type="number" value={text} min={min} max={max} step={step} disabled={disabled}
          onChange={e => setText(e.target.value)} onBlur={e => commit(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') commit((e.target as HTMLInputElement).value) }} />
        <Button small onClick={() => bump(-step)} disabled={disabled || (min !== undefined && value <= min)}>−</Button>
        <Button small onClick={() => bump(step)} disabled={disabled || (max !== undefined && value >= max)}>+</Button>
      </div>
    </div>
  )
}

export function TextArea({ label, value, onChange, rows = 4, help, placeholder, maxLength, disabled, height }: {
  label?: ReactNode; value: string; onChange: (v: string) => void; rows?: number; help?: string; placeholder?: string
  maxLength?: number; disabled?: boolean; height?: number
}) {
  const id = useId()
  return (
    <div>
      <FieldLabel label={label} help={help} htmlFor={id} />
      <textarea id={id} rows={rows} value={value} placeholder={placeholder} maxLength={maxLength} disabled={disabled}
        style={height ? { height } : undefined} onChange={e => onChange(e.target.value)} />
      {maxLength !== undefined && <div className="counter">{value.length}/{maxLength}</div>}
    </div>
  )
}

export function Select<T extends string>({ label, value, options, onChange, help, disabled, format }: {
  label?: ReactNode; value: T; options: readonly T[]; onChange: (v: T) => void; help?: string; disabled?: boolean
  format?: (v: T) => string
}) {
  const id = useId()
  return (
    <div>
      <FieldLabel label={label} help={help} htmlFor={id} />
      <select id={id} value={value} disabled={disabled} onChange={e => onChange(e.target.value as T)}>
        {options.map(o => <option key={o} value={o}>{format ? format(o) : o}</option>)}
      </select>
    </div>
  )
}

export function Checkbox({ label, checked, onChange, help, disabled }: {
  label: ReactNode; checked: boolean; onChange: (v: boolean) => void; help?: string; disabled?: boolean
}) {
  return (
    <label className="check">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={e => onChange(e.target.checked)} />
      <span>{label}<Help text={help} /></span>
    </label>
  )
}

export function Radio<T extends string>({ label, value, options, onChange, help, horizontal, format, optionHelp, disabled }: {
  label?: ReactNode; value: T; options: readonly T[]; onChange: (v: T) => void; help?: string; horizontal?: boolean
  format?: (v: T) => ReactNode; optionHelp?: (v: T) => string | undefined; disabled?: boolean
}) {
  const name = useId()
  return (
    <div role="radiogroup">
      <FieldLabel label={label} help={help} />
      <div className={`radio-group${horizontal ? ' horizontal' : ''}`}>
        {options.map(o => (
          <label key={o} className="radio">
            <input type="radio" name={name} checked={value === o} disabled={disabled} onChange={() => onChange(o)} />
            <span>{format ? format(o) : o}<Help text={optionHelp?.(o)} /></span>
          </label>
        ))}
      </div>
    </div>
  )
}

export function MultiSelect({ label, value, options, optionLabels, onChange, help, placeholder = 'Choose options', disabled }: {
  label?: ReactNode; value: string[]; options: readonly string[]; optionLabels?: Readonly<Record<string, string>>; onChange: (v: string[]) => void; help?: string
  placeholder?: string; disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const remaining = options.filter(o => !value.includes(o) && o.toLowerCase().includes(query.toLowerCase()))
  return (
    <div ref={ref}>
      <FieldLabel label={label} help={help} />
      <div className="ms">
        <div className={`ms-box${open ? ' focus' : ''}`} onClick={() => !disabled && setOpen(true)}>
          {value.map(v => (
            <span key={v} className="ms-chip">{optionLabels?.[v] ?? v}
              <button type="button" aria-label={`${v} 제거`} disabled={disabled}
                onClick={e => { e.stopPropagation(); onChange(value.filter(x => x !== v)) }}>×</button>
            </span>
          ))}
          <input value={query} disabled={disabled} placeholder={value.length ? '' : placeholder}
            onChange={e => { setQuery(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
            onKeyDown={e => {
              if (e.key === 'Backspace' && !query && value.length) onChange(value.slice(0, -1))
              if (e.key === 'Enter' && remaining[0]) { e.preventDefault(); onChange([...value, remaining[0]]); setQuery('') }
              if (e.key === 'Escape') setOpen(false)
            }} />
          {value.length > 0 && !disabled && (
            <button type="button" className="btn link" style={{ textDecoration: 'none', color: 'var(--muted)' }}
              onClick={e => { e.stopPropagation(); onChange([]) }} aria-label="모두 지우기">×</button>
          )}
        </div>
        {open && !disabled && (
          <div className="ms-list">
            {remaining.length ? remaining.map(o => (
              <div key={o} onMouseDown={e => { e.preventDefault(); onChange([...value, o]); setQuery('') }}>{optionLabels?.[o] ?? o}</div>
            )) : <div className="ms-placeholder">No results</div>}
          </div>
        )}
      </div>
    </div>
  )
}

export function Expander({ title, children, defaultOpen = false }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details className="expander" open={defaultOpen || undefined}>
      <summary>{title}</summary>
      <div className="expander-body">{children}</div>
    </details>
  )
}

export function Dialog({ title, onClose, children, wide }: { title: ReactNode; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [onClose])
  return (
    <div className="dialog-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`dialog${wide ? ' wide' : ''}`} role="dialog" aria-modal="true">
        <button className="dialog-close" onClick={onClose} aria-label="닫기">×</button>
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  )
}

export function Tabs<K extends string>({ tabs, active, onChange, sub }: {
  tabs: readonly (readonly [K, string])[]; active: K; onChange: (k: K) => void; sub?: boolean
}) {
  return (
    <div className={`tabs${sub ? ' subtabs' : ''}`} role="tablist">
      {tabs.map(([key, label]) => (
        <button key={key} role="tab" aria-selected={active === key} className={`tab${active === key ? ' active' : ''}`}
          onClick={() => onChange(key)}>{label}</button>
      ))}
    </div>
  )
}

/* ---------- data table ---------- */
export type Column<R> = {
  key: string
  label?: string
  width?: number | string
  num?: boolean
  render?: (row: R, index: number) => ReactNode
}

export function DataTable<R extends Record<string, unknown>>({
  rows, columns, rowKey, selectable, selected, onSelectedChange, showIndex = true, emptyText = '데이터가 없습니다.',
  selectLabel = '선택',
}: {
  rows: readonly R[]; columns: readonly Column<R>[]; rowKey: (row: R, index: number) => string
  selectable?: boolean; selected?: ReadonlySet<string>; onSelectedChange?: (next: Set<string>) => void
  showIndex?: boolean; emptyText?: string; selectLabel?: string
}) {
  const keys = useMemo(() => rows.map(rowKey), [rows, rowKey])
  const allOn = selectable && keys.length > 0 && keys.every(k => selected?.has(k))
  const toggle = (k: string) => {
    const next = new Set(selected)
    if (next.has(k)) next.delete(k); else next.add(k)
    onSelectedChange?.(next)
  }
  const toggleAll = () => {
    const next = new Set(selected)
    if (allOn) keys.forEach(k => next.delete(k)); else keys.forEach(k => next.add(k))
    onSelectedChange?.(next)
  }
  return (
    <div className="table-wrap">
      <table className="grid">
        <thead>
          <tr>
            {selectable && <th className="sel"><input type="checkbox" aria-label="전체 선택" checked={!!allOn} onChange={toggleAll} title={selectLabel} /></th>}
            {showIndex && <th className="num"></th>}
            {columns.map(c => <th key={c.key} className={c.num ? 'num' : undefined} style={c.width ? { minWidth: c.width } : undefined}>{c.label ?? c.key}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={columns.length + (selectable ? 1 : 0) + (showIndex ? 1 : 0)} className="caption">{emptyText}</td></tr>}
          {rows.map((row, i) => {
            const k = keys[i]
            const on = selected?.has(k)
            return (
              <tr key={k} className={on ? 'selected' : undefined}>
                {selectable && <td className="sel"><input type="checkbox" aria-label={`${i + 1}행 선택`} checked={!!on} onChange={() => toggle(k)} /></td>}
                {showIndex && <td className="num idx">{i}</td>}
                {columns.map(c => (
                  <td key={c.key} className={c.num ? 'num' : undefined}>
                    {c.render ? c.render(row, i) : formatCell(row[c.key])}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function formatCell(value: unknown): ReactNode {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? '✔' : ''
  return String(value)
}

/* ---------- pagination ---------- */
export function Pager({ page, pageCount, onChange, total, pageSize }: {
  page: number; pageCount: number; onChange: (p: number) => void; total?: number; pageSize?: number
}) {
  if (pageCount <= 1 && total === undefined) return null
  return (
    <div className="row center tight mt">
      <Button small onClick={() => onChange(page - 1)} disabled={page <= 1}>이전</Button>
      <span className="caption">{page} / {Math.max(1, pageCount)} 페이지{total !== undefined && pageSize ? ` · 총 ${total.toLocaleString()}개` : ''}</span>
      <Button small onClick={() => onChange(page + 1)} disabled={page >= pageCount}>다음</Button>
    </div>
  )
}

export function errorText(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}
