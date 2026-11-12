import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
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
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [listRect, setListRect] = useState<DOMRect | null>(null)
  useEffect(() => {
    if (!open) return
    const update = () => {
      const rect = inputRef.current?.getBoundingClientRect()
      if (rect) setListRect(rect)
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [open])
  useEffect(() => {
    const close = (e: MouseEvent) => {
      const target = e.target as Node
      if (!ref.current?.contains(target) && !listRef.current?.contains(target)) setOpen(false)
    }
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
        <input ref={inputRef} id={id} type="text" disabled={disabled} placeholder={value ?? placeholder} value={open ? query : value ?? ''}
          onFocus={() => { setOpen(true); setQuery('') }}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onKeyDown={e => {
            if (e.key === 'Enter' && filtered[0]) { e.preventDefault(); onChange(filtered[0]); setOpen(false) }
            if (e.key === 'Escape') setOpen(false)
          }} />
        {open && !disabled && listRect && createPortal(
          <div ref={listRef} className="ms-list" style={{ position: 'fixed', left: Math.max(8, Math.min(listRect.left, window.innerWidth - Math.max(listRect.width, 520) - 8)), top: listRect.bottom + 4,
            width: `min(${Math.max(listRect.width, 520)}px, calc(100vw - 16px))`, maxHeight: `min(260px, calc(100vh - ${listRect.bottom + 12}px))`, zIndex: 1000 }}>
            {filtered.length ? filtered.map(o => (
              <div key={o} className={o === value ? 'on' : undefined}
                onMouseDown={e => { e.preventDefault(); onChange(o); setOpen(false) }}>{o}</div>
            )) : <div className="ms-placeholder">No results</div>}
          </div>, document.body,
        )}
      </div>
    </div>
  )
}
