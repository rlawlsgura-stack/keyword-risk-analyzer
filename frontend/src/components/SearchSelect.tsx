import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import { FieldLabel } from './ui.tsx'

/** Streamlit selectbox with type-to-filter ("contains") and an optional empty state. */
export function SearchSelect({ label, value, options, onChange, placeholder, disabled, help, maxShown = 200 }: {
  label?: ReactNode; value: string | null; options: readonly string[]; onChange: (v: string | null) => void
  placeholder?: string; disabled?: boolean; help?: string; maxShown?: number
}) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (q ? options.filter(o => o.toLowerCase().includes(q)) : options).slice(0, maxShown)
  }, [options, query, maxShown])
  return (
    <div ref={ref}>
      <FieldLabel label={label} help={help} htmlFor={id} />
      <div className="ms">
        <input id={id} disabled={disabled} placeholder={value ?? placeholder} value={open ? query : value ?? ''}
          onFocus={() => { setOpen(true); setQuery('') }}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onKeyDown={e => {
            if (e.key === 'Enter' && filtered[0]) { e.preventDefault(); onChange(filtered[0]); setOpen(false) }
            if (e.key === 'Escape') setOpen(false)
          }} />
        {open && !disabled && (
          <div className="ms-list">
            {filtered.length ? filtered.map(o => (
              <div key={o} className={o === value ? 'on' : undefined}
                onMouseDown={e => { e.preventDefault(); onChange(o); setOpen(false) }}>{o}</div>
            )) : <div className="ms-placeholder">No results</div>}
          </div>
        )}
      </div>
    </div>
  )
}
