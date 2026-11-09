import { useCallback, useEffect, useState } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { configurationReady, supabase } from './lib/supabase.ts'
import type { Role } from './lib/types.ts'
import { StoreProvider, useStore, type TabKey } from './store.tsx'
import { LoginScreen, NewPasswordScreen } from './components/Login.tsx'
import { Alert, Button, Spinner, Tabs } from './components/ui.tsx'
import { AnalysisTab } from './tabs/AnalysisTab.tsx'
import { OcrTab } from './tabs/OcrTab.tsx'
import { UnmatchedTab } from './tabs/UnmatchedTab.tsx'
import { RequestsTab } from './tabs/RequestsTab.tsx'
import { ChatTab } from './tabs/ChatTab.tsx'
import { ReportTab } from './tabs/ReportTab.tsx'
import { KeywordAdminTab } from './tabs/KeywordAdminTab.tsx'
import { UsersTab } from './tabs/UsersTab.tsx'

export const APP_VERSION = 'REACT-1.10 (FIXED330 기준)'
const TITLE = '🔎 광고심의 자동화 솔루션'

/** The recovery hash is read before supabase-js consumes it (L1660-1686). */
const initialHash = new URLSearchParams(window.location.hash.replace(/^#/, ''))
const recoveryInLink = initialHash.get('type') === 'recovery'
// Supabase sends expired/used links back as "#error=…&error_code=otp_expired" (no type, no token).
const authLinkError = initialHash.get('error_code') ?? initialHash.get('error')
const recoveryLinkBroken = (recoveryInLink && !initialHash.get('access_token')) || Boolean(authLinkError)
// supabase-js may consume the recovery hash (and emit PASSWORD_RECOVERY) before we subscribe,
// so the recovery session would look like an ordinary sign-in. Remember it until the password is set.
let recoveryPending = recoveryInLink && !recoveryLinkBroken

type AuthState =
  | { kind: 'loading' }
  | { kind: 'signed_out'; flash?: string }
  | { kind: 'recovery' }
  | { kind: 'no_role' }
  | { kind: 'error'; text: string }
  | { kind: 'ready'; user: User; role: Role }

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ kind: 'loading' })
  const [connectionError, setConnectionError] = useState(false)

  const resolveSession = useCallback(async (session: Session | null) => {
    if (!supabase) return
    if (!session) { setAuth(prev => (prev.kind === 'signed_out' ? prev : { kind: 'signed_out' })); return }
    const { data, error } = await supabase.auth.getUser()
    if (error || !data.user) {
      if ((error as { status?: number } | null)?.status === 0 || /fetch/i.test(error?.message ?? '')) { setConnectionError(true); return }
      setAuth({ kind: 'error', text: '로그인 세션을 확인할 수 없습니다. 로그아웃 후 다시 로그인하세요.' })
      return
    }
    setConnectionError(false)
    const role = data.user.app_metadata?.role
    if (role !== 'admin' && role !== 'member') { setAuth({ kind: 'no_role' }); return }
    setAuth(prev => (prev.kind === 'ready' && prev.user.id === data.user.id && prev.role === role
      ? prev : { kind: 'ready', user: data.user, role }))
  }, [])

  useEffect(() => {
    if (!supabase) return
    if (recoveryLinkBroken) return
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY' || (recoveryPending && session && event !== 'SIGNED_OUT')) {
        recoveryPending = true
        setAuth({ kind: 'recovery' })
        return
      }
      if (event === 'SIGNED_OUT') { setAuth(prev => (prev.kind === 'signed_out' ? prev : { kind: 'signed_out' })); return }
      if (event === 'INITIAL_SESSION' || event === 'SIGNED_IN' || event === 'USER_UPDATED') void resolveSession(session)
    })
    return () => data.subscription.unsubscribe()
  }, [resolveSession])

  if (!configurationReady) {
    return (
      <div className="centered">
        <h1>{TITLE}</h1>
        <Alert kind="error">연결 설정이 필요합니다. VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY, VITE_API_BASE_URL을 설정하세요.</Alert>
      </div>
    )
  }

  if (recoveryLinkBroken) {
    return (
      <div className="centered">
        <h1>{TITLE}</h1>
        <Alert kind="error">복구 링크가 만료되었거나 이미 사용되었습니다. 비밀번호 찾기를 다시 요청하세요.</Alert>
        <Button onClick={() => { history.replaceState(null, '', window.location.pathname); window.location.reload() }}>로그인 화면으로 돌아가기</Button>
      </div>
    )
  }

  const page = (() => {
    if (connectionError) {
      return (
        <div className="centered">
          <Alert kind="error">로그인 상태를 확인하기 위해 Supabase에 연결할 수 없습니다.</Alert>
          <Button onClick={() => window.location.reload()}>다시 시도</Button>
        </div>
      )
    }
    switch (auth.kind) {
      case 'loading': return <div className="centered"><Alert kind="info">로그인 상태를 확인하고 있습니다…</Alert></div>
      case 'signed_out': return <LoginScreen flash={auth.flash} />
      case 'recovery':
        return <NewPasswordScreen onDone={() => {
          recoveryPending = false
          history.replaceState(null, '', window.location.pathname)
          setAuth({ kind: 'signed_out', flash: '비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요.' })
        }} />
      case 'no_role':
        return <div className="centered"><Alert kind="error">사내 앱 사용 권한이 없습니다. 관리자에게 문의하세요.</Alert>
          <Button onClick={() => supabase?.auth.signOut()}>로그아웃</Button></div>
      case 'error':
        return <div className="centered"><Alert kind="error">{auth.text}</Alert>
          <Button onClick={() => supabase?.auth.signOut()}>로그아웃</Button></div>
      case 'ready': return null
    }
  })()

  if (auth.kind !== 'ready' || connectionError) {
    return (
      <div className="main"><div className="main-inner">
        <h1>{TITLE}</h1>
        {page}
      </div></div>
    )
  }
  return (
    <StoreProvider key={auth.user.id} user={auth.user} role={auth.role}>
      <Shell />
    </StoreProvider>
  )
}

const TAB_LABELS: Record<TabKey, string> = {
  analysis: '스크립트 분석',
  ocr_import: '이미지 OCR분석',
  candidate_pool: '미매칭 후보군',
  requests: '키워드 문의',
  regulation_chat: '심의 Chat-bot',
  report: '분석리포트',
  keyword_admin: '키워드 관리',
  user_admin: '사용자 관리',
}

function Shell() {
  const store = useStore()
  const { user, isAdmin, tab, setTab, catalog, catalogError, reloadCatalog, reloadDropdowns, pending, retryPending } = store
  const [collapsed, setCollapsed] = useState(window.innerWidth < 900)
  const [logoutError, setLogoutError] = useState('')
  const [pendingNote, setPendingNote] = useState('')
  const [reloading, setReloading] = useState(false)

  useEffect(() => { void reloadCatalog(); void reloadDropdowns() }, [reloadCatalog, reloadDropdowns])

  useEffect(() => {
    const tableAtResizeEdge = (event: MouseEvent | PointerEvent) => {
      if (!(event.target instanceof Element)) return null
      const header = event.target.closest('table.grid th') as HTMLTableCellElement | null
      const table = header?.closest('table.grid') as HTMLTableElement | null
      if (!header || !table) return null
      const rect = header.getBoundingClientRect()
      if (rect.right - event.clientX > 8) return null
      return { table, index: header.cellIndex }
    }
    const applyWidths = (table: HTMLTableElement, widths: number[], userResized = false, titleColumn?: number) => {
      const rows = Array.from(table.rows)
      table.classList.add('is-column-fitted')
      table.classList.toggle('is-column-resized', userResized)
      table.style.tableLayout = 'fixed'
      table.style.width = `${widths.reduce((sum, width) => sum + width, 0)}px`
      Array.from(rows[0]?.cells ?? []).forEach((cell, column) => {
        if (widths[column] === undefined || cell.colSpan > 1) return
        cell.style.width = `${widths[column]}px`
        cell.style.boxSizing = 'border-box'
      })
      if (userResized) rows.forEach(row => Array.from(row.cells).forEach((cell, column) => {
        if (column !== titleColumn || cell.colSpan > 1) return
        const value = cell.textContent?.trim() || Array.from(cell.querySelectorAll('input, textarea, select'))
            .map(control => control instanceof HTMLSelectElement ? control.selectedOptions[0]?.text : (control as HTMLInputElement).value)
            .filter(Boolean).join(', ')
        if (value) cell.title = value
      }))
    }
    const measureNaturalWidths = (table: HTMLTableElement) => {
      const context = document.createElement('canvas').getContext('2d')
      if (!context) return Array.from(table.rows[0]?.cells ?? [], cell => cell.getBoundingClientRect().width)
      const widths: number[] = []
      const columnsWithContent: boolean[] = []
      const measureCellStyle = (cell: HTMLTableCellElement) => {
        const style = getComputedStyle(cell)
        return {
          font: `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`,
          padding: parseFloat(style.paddingLeft) + parseFloat(style.paddingRight),
          borders: parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth),
          selectionWidth: cell.classList.contains('sel') ? parseFloat(style.width) || 0 : 0,
        }
      }
      const headerMetrics = Array.from(table.tHead?.rows[0]?.cells ?? [], measureCellStyle)
      const bodyMetrics = Array.from(table.tBodies[0]?.rows[0]?.cells ?? [], measureCellStyle)
      Array.from(table.rows).forEach(row => {
        let column = 0
        Array.from(row.cells).forEach(cell => {
          const span = cell.colSpan || 1
          if (span > 1) { column += span; return }
          const metrics = (row.parentElement === table.tHead ? headerMetrics : bodyMetrics)[column] ?? headerMetrics[column]
          const select = cell.querySelector('select')
          const controls = Array.from(cell.querySelectorAll('input[type="text"], textarea'))
          const controlValues = controls.map(control => (control as HTMLInputElement).value)
          const text = controls.length ? controlValues.join(', ') : select ? select.selectedOptions[0]?.text ?? '' : cell.textContent?.trim() || ''
          const measuredText = text
          const controlPadding = select ? 24 : controls.length ? 12 : 0
          const selectionWidth = cell.classList.contains('sel') ? metrics?.selectionWidth ?? 0 : 0
          if (metrics) context.font = metrics.font
          const width = Math.ceil(Math.max(context.measureText(measuredText).width + controlPadding, selectionWidth) + (metrics?.padding ?? 0) + (metrics?.borders ?? 0) + 1)
          widths[column] = Math.max(widths[column] ?? 0, width)
          if (row.parentElement !== table.tHead && text.trim()) columnsWithContent[column] = true
          column += 1
        })
      })
      Array.from(table.tHead?.rows[0]?.cells ?? []).forEach((cell, column) => {
        if (cell.classList.contains('sel') || columnsWithContent[column]) return
        const metrics = bodyMetrics[column] ?? headerMetrics[column]
        if (metrics) context.font = metrics.font
        const defaultWidth = context.measureText('가'.repeat(20)).width + (metrics?.padding ?? 0) + (metrics?.borders ?? 0) + 1
        widths[column] = Math.max(widths[column] ?? 0, Math.ceil(defaultWidth))
      })
      return widths
    }
    const fitTable = (table: HTMLTableElement) => applyWidths(table, measureNaturalWidths(table))
    const fittedTables = new WeakSet<HTMLTableElement>()
    const contentObservers = new Set<MutationObserver>()
    const initialColumnOrder = new WeakMap<HTMLTableElement, string[]>()
    const currentColumnOrder = new WeakMap<HTMLTableElement, string[]>()
    const sortState = new WeakMap<HTMLTableElement, { key: string; direction: 'asc' | 'desc' }>()
    let activeRange: { table: HTMLTableElement; startRow: number; startCol: number; endRow: number; endCol: number } | null = null
    let suppressClickTable: HTMLTableElement | null = null
    let isPasting = false
    const clearSelection = () => {
      document.querySelectorAll('table.grid td.range-selected, table.grid th.column-selected, table.grid td.column-selected')
        .forEach(cell => cell.classList.remove('range-selected', 'column-selected'))
      activeRange = null
    }
    const paintRange = (range: NonNullable<typeof activeRange>) => {
      clearSelection()
      activeRange = range
      const rowStart = Math.min(range.startRow, range.endRow), rowEnd = Math.max(range.startRow, range.endRow)
      const colStart = Math.min(range.startCol, range.endCol), colEnd = Math.max(range.startCol, range.endCol)
      const rows = Array.from(range.table.tBodies[0]?.rows ?? [])
      for (let row = rowStart; row <= rowEnd; row++) for (let col = colStart; col <= colEnd; col++) {
        rows[row]?.cells[col]?.classList.add('range-selected')
      }
    }
    const columnText = (cell: HTMLTableCellElement) => {
      const input = cell.querySelector('input[type="text"], textarea') as HTMLInputElement | HTMLTextAreaElement | null
      if (input) return input.value
      const select = cell.querySelector('select')
      if (select) return select.selectedOptions[0]?.text ?? ''
      const checkbox = cell.querySelector('input[type="checkbox"]') as HTMLInputElement | null
      if (checkbox) return checkbox.checked ? '✓' : ''
      return (cell.innerText || cell.textContent || '').trim()
    }
    const ensureColumnKeys = (table: HTMLTableElement) => {
      const header = table.rows[0]
      if (!header) return
      let base = initialColumnOrder.get(table)
      const headers = Array.from(header.cells)
      if (!base) {
        const used = new Map<string, number>()
        base = headers.map((cell, index) => {
          const label = cell.textContent?.trim() || `fixed-${index}`
          const count = used.get(label) ?? 0
          used.set(label, count + 1)
          const key = `${label}#${count}`
          cell.dataset.columnKey = key
          return key
        })
        initialColumnOrder.set(table, base)
        currentColumnOrder.set(table, [...base])
      } else headers.forEach((cell, index) => {
        if (!cell.dataset.columnKey && base?.[index]) cell.dataset.columnKey = base[index]
      })
      Array.from(table.rows).forEach(row => Array.from(row.cells).forEach((cell, index) => {
        if (!cell.dataset.columnKey && base?.[index]) cell.dataset.columnKey = base[index]
      }))
      headers.forEach(cell => {
        const label = cell.textContent?.trim()
        const fixed = cell.classList.contains('sel') || !label || cell.querySelector('input, button')
        cell.classList.toggle('table-sortable', !fixed)
        cell.classList.toggle('table-movable', !fixed)
        cell.draggable = !fixed
        if (!fixed) cell.title = '화살표: 정렬 · 제목 영역: 열 선택 및 드래그 이동 · 오른쪽 경계: 너비 조절'
      })
    }
    const arrangeColumns = (table: HTMLTableElement) => {
      const order = currentColumnOrder.get(table)
      if (!order) return
      Array.from(table.rows).forEach(row => {
        const cells = Array.from(row.cells)
        if (cells.length !== order.length || cells.some(cell => cell.colSpan > 1)) return
        const keys = cells.map(cell => cell.dataset.columnKey)
        if (order.every((key, index) => keys[index] === key)) return
        order.forEach(key => {
          const cell = cells.find(item => item.dataset.columnKey === key)
          if (cell) row.append(cell)
        })
      })
    }
    const updateColumnSelection = (table: HTMLTableElement, key: string | null) => {
      Array.from(table.rows).forEach(row => Array.from(row.cells).forEach(cell => {
        cell.classList.toggle('column-selected', !!key && cell.dataset.columnKey === key)
      }))
    }
    const sortedRows = (table: HTMLTableElement, key: string, direction: 'asc' | 'desc') => {
      const header = Array.from(table.rows[0]?.cells ?? []).find(cell => cell.dataset.columnKey === key)
      if (!header) return
      const index = header.cellIndex
      const collator = new Intl.Collator('ko', { numeric: true, sensitivity: 'base' })
      Array.from(table.tBodies).forEach(body => {
        const rows = Array.from(body.rows)
        const ordered = rows.map((row, i) => ({ row, i, value: columnText(row.cells[index]) }))
          .sort((a, b) => {
            const an = Number(a.value.replaceAll(',', '')), bn = Number(b.value.replaceAll(',', ''))
            const numeric = a.value.trim() !== '' && b.value.trim() !== '' && Number.isFinite(an) && Number.isFinite(bn)
            const result = numeric ? an - bn : collator.compare(a.value, b.value)
            return (direction === 'asc' ? result : -result) || a.i - b.i
          })
        if (ordered.some((item, i) => rows[i] !== item.row)) {
          if (table.querySelector('.range-selected, .column-selected')) clearSelection()
          ordered.forEach(item => body.append(item.row))
        }
        Array.from(body.rows).forEach((row, i) => {
          const indexCell = row.querySelector('td.idx')
          if (indexCell && indexCell.textContent !== String(i)) indexCell.textContent = String(i)
        })
      })
    }
    const sortColumn = (table: HTMLTableElement, key: string) => {
      const previous = sortState.get(table)
      const direction = previous?.key === key && previous.direction === 'asc' ? 'desc' : 'asc'
      sortState.set(table, { key, direction })
      table.querySelectorAll<HTMLTableCellElement>('thead th.table-sortable').forEach(cell => {
        cell.setAttribute('data-sort-direction', cell.dataset.columnKey === key ? direction : '')
      })
      clearSelection()
      sortedRows(table, key, direction)
    }
    const refreshTable = (table: HTMLTableElement) => {
      fitTable(table)
      const activeSort = sortState.get(table)
      if (activeSort) sortedRows(table, activeSort.key, activeSort.direction)
    }
    const pendingInputRefresh = new WeakMap<HTMLTableElement, number>()
    const moveColumn = (table: HTMLTableElement, from: string, to: string) => {
      const order = currentColumnOrder.get(table)
      const fromIndex = order?.indexOf(from) ?? -1, toIndex = order?.indexOf(to) ?? -1
      if (!order || fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return
      const next = [...order]
      next.splice(fromIndex, 1)
      next.splice(toIndex, 0, from)
      currentColumnOrder.set(table, next)
      arrangeColumns(table)
      updateColumnSelection(table, null)
      clearSelection()
    }
    const prepareTable = (table: HTMLTableElement) => {
      ensureColumnKeys(table)
      arrangeColumns(table)
      fitTable(table)
      const activeSort = sortState.get(table)
      if (activeSort) sortedRows(table, activeSort.key, activeSort.direction)
    }
    const pendingTableWork = new WeakMap<HTMLTableElement, { prepare: boolean }>()
    const scheduleTableWork = (table: HTMLTableElement, prepare: boolean) => {
      const pending = pendingTableWork.get(table)
      if (pending) {
        pending.prepare ||= prepare
        return
      }
      const work = { prepare }
      requestAnimationFrame(() => {
        pendingTableWork.delete(table)
        if (!table.isConnected) return
        if (work.prepare) prepareTable(table)
        else fitTable(table)
      })
      pendingTableWork.set(table, work)
    }
    const discoverTables = (root: ParentNode) => {
      const tables = [...(root instanceof Element && root.matches('table.grid') ? [root] : []), ...root.querySelectorAll('table.grid')]
      tables.forEach(table => {
        const grid = table as HTMLTableElement
        if (fittedTables.has(grid)) return
        fittedTables.add(grid)
        prepareTable(grid)
        const observer = new MutationObserver(records => {
          scheduleTableWork(grid, records.some(record => record.type === 'childList'))
        })
        observer.observe(grid, { childList: true, characterData: true, subtree: true })
        contentObservers.add(observer)
      })
    }
    discoverTables(document)
    const tableObserver = new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
      if (node instanceof Element) discoverTables(node)
    })))
    tableObserver.observe(document.body, { childList: true, subtree: true })
    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return
      const target = tableAtResizeEdge(event)
      if (target) {
        const { index, table } = target
        const widths = Array.from(table.rows[0]?.cells ?? [], cell => cell.getBoundingClientRect().width)
        const startWidth = widths[index]
        if (startWidth === undefined) return
        const startX = event.clientX
        document.body.style.cursor = 'col-resize'
        applyWidths(table, widths, true)
        const onMove = (move: PointerEvent) => {
          widths[index] = Math.max(40, startWidth + move.clientX - startX)
          applyWidths(table, widths, true, index)
        }
        const onUp = () => {
          document.body.style.cursor = ''
          window.removeEventListener('pointermove', onMove)
          window.removeEventListener('pointerup', onUp)
        }
        window.addEventListener('pointermove', onMove)
        window.addEventListener('pointerup', onUp, { once: true })
        return
      }
      if (!(event.target instanceof Element)) { clearSelection(); return }
      if (event.target.closest('input, select, textarea, button, a')) { clearSelection(); return }
      const cell = event.target.closest('table.grid tbody td') as HTMLTableCellElement | null
      if (!cell) { clearSelection(); return }
      const table = cell.closest('table.grid') as HTMLTableElement
      const rows = Array.from(table.tBodies[0]?.rows ?? [])
      const row = rows.indexOf(cell.parentElement as HTMLTableRowElement)
      const col = cell.cellIndex
      if (row < 0) return
      cell.tabIndex = -1
      cell.focus({ preventScroll: true })
      paintRange({ table, startRow: row, startCol: col, endRow: row, endCol: col })
      document.body.classList.add('grid-selecting')
      let moved = false
      const onMove = (move: PointerEvent) => {
        const underPointer = document.elementFromPoint(move.clientX, move.clientY)
        const nextCell = underPointer instanceof Element ? underPointer.closest('table.grid tbody td') as HTMLTableCellElement | null : null
        if (!nextCell || nextCell.closest('table.grid') !== table) return
        const nextRow = rows.indexOf(nextCell.parentElement as HTMLTableRowElement)
        if (nextRow < 0) return
        if (nextRow !== row || nextCell.cellIndex !== col) moved = true
        paintRange({ table, startRow: row, startCol: col, endRow: nextRow, endCol: nextCell.cellIndex })
      }
      const onUp = () => {
        document.body.classList.remove('grid-selecting')
        if (moved) {
          suppressClickTable = table
          window.setTimeout(() => { if (suppressClickTable === table) suppressClickTable = null }, 0)
        }
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp, { once: true })
    }
    const onDoubleClick = (event: MouseEvent) => {
      const target = tableAtResizeEdge(event)
      if (!target) return
      const { index, table } = target
      const widths = Array.from(table.rows[0]?.cells ?? [], cell => cell.getBoundingClientRect().width)
      const naturalWidths = measureNaturalWidths(table)
      if (naturalWidths[index] === undefined) return
      widths[index] = naturalWidths[index]
      event.preventDefault()
      applyWidths(table, widths, true, index)
    }
    const onHeaderClick = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return
      if (suppressClickTable && event.target.closest('table.grid') === suppressClickTable) {
        event.preventDefault(); event.stopImmediatePropagation(); suppressClickTable = null; return
      }
      const header = event.target.closest('table.grid thead th') as HTMLTableCellElement | null
      const table = header?.closest('table.grid') as HTMLTableElement | null
      if (!header || !table || !header.classList.contains('table-sortable')) return
      const rect = header.getBoundingClientRect()
      const x = event.clientX - rect.left
      if (x <= 26 && rect.right - event.clientX > 8) {
        event.preventDefault(); event.stopImmediatePropagation()
        sortColumn(table, header.dataset.columnKey!)
      } else if (header.getBoundingClientRect().right - event.clientX > 8) {
        clearSelection()
        updateColumnSelection(table, header.dataset.columnKey!)
      }
    }
    const onDragStart = (event: DragEvent) => {
      if (!(event.target instanceof Element)) return
      const header = event.target.closest('table.grid thead th') as HTMLTableCellElement | null
      const table = header?.closest('table.grid') as HTMLTableElement | null
      if (!header || !table || !header.classList.contains('table-movable')) { event.preventDefault(); return }
      const rect = header.getBoundingClientRect()
      if (event.clientX - rect.left <= 26 || rect.right - event.clientX <= 8) { event.preventDefault(); return }
      event.dataTransfer?.setData('text/plain', header.dataset.columnKey ?? '')
      if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
      header.classList.add('column-dragging')
    }
    const onDragOver = (event: DragEvent) => {
      if (event.target instanceof Element && event.target.closest('table.grid thead th.table-movable')) event.preventDefault()
    }
    const onDrop = (event: DragEvent) => {
      if (!(event.target instanceof Element)) return
      const targetHeader = event.target.closest('table.grid thead th.table-movable') as HTMLTableCellElement | null
      const table = targetHeader?.closest('table.grid') as HTMLTableElement | null
      const sourceKey = event.dataTransfer?.getData('text/plain')
      if (!targetHeader || !table || !sourceKey) return
      event.preventDefault()
      moveColumn(table, sourceKey, targetHeader.dataset.columnKey!)
    }
    const onDragEnd = (event: DragEvent) => {
      if (event.target instanceof Element) event.target.closest('th')?.classList.remove('column-dragging')
    }
    const onCopy = (event: ClipboardEvent) => {
      if (!activeRange || !event.clipboardData) return
      const { table, startRow, endRow, startCol, endCol } = activeRange
      const rows = Array.from(table.tBodies[0]?.rows ?? [])
      const values: string[] = []
      for (let r = Math.min(startRow, endRow); r <= Math.max(startRow, endRow); r++) {
        const line: string[] = []
        for (let c = Math.min(startCol, endCol); c <= Math.max(startCol, endCol); c++) {
          line.push(rows[r]?.cells[c] ? columnText(rows[r].cells[c]).replace(/[\t\r\n]+/g, ' ') : '')
        }
        values.push(line.join('\t'))
      }
      event.clipboardData.setData('text/plain', values.join('\n'))
      event.preventDefault()
    }
    const onTableKeyDown = (event: KeyboardEvent) => {
      if (!activeRange || event.altKey || event.ctrlKey || event.metaKey) return
      if ((event.key === ' ' || event.code === 'Space') && !event.shiftKey) {
        if (event.target instanceof Element && event.target.closest('input, select, textarea, button, [contenteditable="true"]')) return
        const range = activeRange
        const rows = Array.from(range.table.tBodies[0]?.rows ?? [])
        const checkboxes: HTMLInputElement[] = []
        for (let row = Math.min(range.startRow, range.endRow); row <= Math.max(range.startRow, range.endRow); row++) {
          for (let col = Math.min(range.startCol, range.endCol); col <= Math.max(range.startCol, range.endCol); col++) {
            const cell = rows[row]?.cells[col]
            if (cell?.classList.contains('sel')) {
              const checkbox = cell.querySelector<HTMLInputElement>('input[type="checkbox"]')
              if (checkbox && !checkbox.disabled) checkboxes.push(checkbox)
            }
          }
        }
        if (checkboxes.length) {
          event.preventDefault()
          const checkedSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked')?.set
          checkboxes.forEach(checkbox => {
            checkedSetter?.call(checkbox, !checkbox.checked)
            checkbox.dispatchEvent(new Event('change', { bubbles: true }))
          })
          return
        }
      }
      const directions: Record<string, [number, number]> = {
        ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1],
      }
      const delta = directions[event.key]
      if (!delta) return
      if (event.target instanceof Element && event.target.closest('input, select, textarea, button, [contenteditable="true"]')) return

      const range = activeRange
      const rows = Array.from(range.table.tBodies[0]?.rows ?? [])
      if (!rows.length) return
      const currentRow = Math.max(0, Math.min(rows.length - 1, range.endRow))
      const currentCol = Math.max(0, Math.min((rows[currentRow]?.cells.length ?? 1) - 1, range.endCol))
      const nextRow = Math.max(0, Math.min(rows.length - 1, currentRow + delta[0]))
      const nextCol = Math.max(0, Math.min((rows[nextRow]?.cells.length ?? 1) - 1, currentCol + delta[1]))
      event.preventDefault()
      if (event.shiftKey) {
        paintRange({ ...range, endRow: nextRow, endCol: nextCol })
      } else {
        paintRange({ table: range.table, startRow: nextRow, startCol: nextCol, endRow: nextRow, endCol: nextCol })
      }
      const nextCell = rows[nextRow]?.cells[nextCol]
      if (nextCell) {
        nextCell.tabIndex = -1
        nextCell.focus({ preventScroll: true })
        nextCell.scrollIntoView({ block: 'nearest', inline: 'nearest' })
      }
    }
    const onPaste = (event: ClipboardEvent) => {
      if (!activeRange || !activeRange.table.isConnected || !event.clipboardData) return
      const text = event.clipboardData.getData('text/plain')
      if (!text) return
      const matrix = text.replace(/\r\n?$/, '').split(/\r\n|\n|\r/).map(line => line.split('\t'))
      const { table, startRow, endRow, startCol, endCol } = activeRange
      const rows = Array.from(table.tBodies[0]?.rows ?? [])
      if (!rows.length) return
      event.preventDefault()

      const rowStart = Math.min(startRow, endRow), colStart = Math.min(startCol, endCol)
      const selectedHeight = Math.abs(endRow - startRow) + 1, selectedWidth = Math.abs(endCol - startCol) + 1
      const repeatCell = matrix.length === 1 && matrix[0].length === 1 && (selectedHeight > 1 || selectedWidth > 1)
      const inputSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      const textareaSetter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
      const selectSetter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
      const checkboxSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked')?.set
      const setText = (control: HTMLInputElement | HTMLTextAreaElement, value: string) => {
        const setter = control instanceof HTMLTextAreaElement ? textareaSetter : inputSetter
        setter?.call(control, value)
        control.dispatchEvent(new Event('input', { bubbles: true }))
      }
      const setSelect = (select: HTMLSelectElement, value: string) => {
        if (!Array.from(select.options).some(option => option.value === value || option.textContent?.trim() === value.trim())) return false
        const option = Array.from(select.options).find(item => item.value === value || item.textContent?.trim() === value.trim())!
        selectSetter?.call(select, option.value)
        select.dispatchEvent(new Event('change', { bubbles: true }))
        return true
      }
      const pasteCell = (cell: HTMLTableCellElement, value: string) => {
        const input = cell.querySelector('input:not([type="checkbox"]):not([type="radio"]):not([type="button"]), textarea') as HTMLInputElement | HTMLTextAreaElement | null
        if (input && !input.disabled && !input.readOnly) { setText(input, value); return }
        const select = cell.querySelector('select')
        if (select && !select.disabled) {
          if (setSelect(select, value)) return
          const direct = select.querySelector<HTMLOptionElement>('option[data-direct-entry]')
          if (!direct) return
          selectSetter?.call(select, direct.value)
          select.dispatchEvent(new Event('change', { bubbles: true }))
          window.requestAnimationFrame(() => {
            const directInput = cell.querySelector('input[type="text"], textarea') as HTMLInputElement | HTMLTextAreaElement | null
            if (directInput && !directInput.disabled && !directInput.readOnly) setText(directInput, value)
          })
          return
        }
        const checkbox = cell.querySelector('input[type="checkbox"]') as HTMLInputElement | null
        if (!checkbox || checkbox.disabled) return
        const normalized = value.trim().toLowerCase()
        const checked = ['✓', '☑', 'true', '1', 'yes', 'y', 'on', 'x'].includes(normalized)
        if (checked || ['', '☐', 'false', '0', 'no', 'n', 'off'].includes(normalized)) {
          checkboxSetter?.call(checkbox, checked)
          checkbox.dispatchEvent(new Event('change', { bubbles: true }))
        }
      }

      isPasting = true
      try {
        if (repeatCell) {
          for (let r = rowStart; r < rowStart + selectedHeight; r++) for (let c = colStart; c < colStart + selectedWidth; c++) {
            const cell = rows[r]?.cells[c]
            if (cell) pasteCell(cell, matrix[0][0])
          }
        } else {
          matrix.forEach((line, r) => line.forEach((value, c) => {
            const cell = rows[rowStart + r]?.cells[colStart + c]
            if (cell) pasteCell(cell, value)
          }))
        }
      } finally {
        isPasting = false
      }
      window.requestAnimationFrame(() => { if (table.isConnected) refreshTable(table) })
    }
    const onTableInput = (event: Event) => {
      if (isPasting) return
      if (!(event.target instanceof Element)) return
      const table = event.target.closest('table.grid') as HTMLTableElement | null
      if (!table) return
      const pending = pendingInputRefresh.get(table)
      if (pending !== undefined) window.clearTimeout(pending)
      pendingInputRefresh.set(table, window.setTimeout(() => {
        pendingInputRefresh.delete(table)
        if (table.isConnected) refreshTable(table)
      }, 120))
    }
    const onTableValueChange = (event: Event) => {
      if (isPasting) return
      if (!(event.target instanceof Element)) return
      const table = event.target.closest('table.grid') as HTMLTableElement | null
      if (!table) return
      const pending = pendingInputRefresh.get(table)
      if (pending !== undefined) window.clearTimeout(pending)
      pendingInputRefresh.delete(table)
      refreshTable(table)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('dblclick', onDoubleClick, true)
    document.addEventListener('click', onHeaderClick, true)
    document.addEventListener('dragstart', onDragStart, true)
    document.addEventListener('dragover', onDragOver)
    document.addEventListener('drop', onDrop)
    document.addEventListener('dragend', onDragEnd, true)
    document.addEventListener('copy', onCopy)
    document.addEventListener('keydown', onTableKeyDown, true)
    document.addEventListener('paste', onPaste)
    document.addEventListener('input', onTableInput)
    document.addEventListener('change', onTableValueChange)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('dblclick', onDoubleClick, true)
      document.removeEventListener('click', onHeaderClick, true)
      document.removeEventListener('dragstart', onDragStart, true)
      document.removeEventListener('dragover', onDragOver)
      document.removeEventListener('drop', onDrop)
      document.removeEventListener('dragend', onDragEnd, true)
      document.removeEventListener('copy', onCopy)
      document.removeEventListener('keydown', onTableKeyDown, true)
      document.removeEventListener('paste', onPaste)
      document.body.classList.remove('grid-selecting')
      document.removeEventListener('input', onTableInput)
      document.removeEventListener('change', onTableValueChange)
      tableObserver.disconnect()
      contentObservers.forEach(observer => observer.disconnect())
    }
  }, [])

  // Tab order and visibility (L3791-3812): every signed-in cloud user is admin or member.
  const tabs: [TabKey, string][] = (['analysis', 'ocr_import', 'candidate_pool', 'requests', 'regulation_chat', 'report'] as TabKey[])
    .concat(isAdmin ? ['keyword_admin', 'user_admin'] : [])
    .map(k => [k, TAB_LABELS[k]])

  const pendingCount = Object.keys(pending).length

  const logout = async () => {
    if (pendingCount) { setLogoutError('아직 저장하지 못한 미매칭 후보가 있습니다. 수집 저장 재시도 후 로그아웃하세요.'); return }
    await supabase?.auth.signOut()
  }

  return (
    <div className="app">
      <button className="sidebar-toggle" onClick={() => setCollapsed(c => !c)} aria-label="사이드바 열기/닫기">{collapsed ? '»' : '«'}</button>
      <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">K</span>
          <span><strong>키워드 리스크</strong><small>ANALYZER</small></span>
        </div>
        <div className="section sidebar-account">
          <span className="sidebar-section-label">계정</span>
          <span className="account-email" title={user.email}>{user.email || '로그인됨'}</span>
          <Button onClick={logout}>로그아웃</Button>
          {logoutError && <Alert kind="error">{logoutError}</Alert>}
        </div>
        <div className="section">
          <span className="sidebar-section-label">데이터 저장소</span>
          <span className="caption">Supabase 공유 저장소</span>
          <Button disabled={reloading} onClick={async () => { setReloading(true); await reloadCatalog(); await reloadDropdowns(); setReloading(false) }}>
            최신 데이터 불러오기
          </Button>
        </div>
      </aside>
      <main className="main">
        <div className="main-inner">
          <header className="page-header">
            <div><span className="page-kicker">KEYWORD RISK WORKSPACE</span><h1>{TITLE}</h1></div>
            <span className="version-badge">앱 버전 · {APP_VERSION}</span>
          </header>
          <Tabs tabs={tabs} active={tab} onChange={setTab} />
          {pendingCount > 0 && (
            <div>
              <Alert kind="warning">미매칭 후보 중 아직 DB에 저장하지 못한 분석이 있습니다. 저장 전에는 로그아웃하지 마세요.</Alert>
              <Button onClick={async () => {
                const { failed } = await retryPending()
                setPendingNote(failed ? '미매칭 후보를 DB에 저장하지 못했습니다. 수집 저장 재시도로 다시 저장하세요.' : '')
                if (!failed) setLogoutError('')
              }}>수집 저장 재시도</Button>
              {pendingNote && <Alert kind="warning">{pendingNote}</Alert>}
            </div>
          )}
          {catalogError && <Alert kind="error">{catalogError}</Alert>}
          {!catalog && !catalogError ? <Spinner text="키워드 DB를 불러오는 중입니다." /> : (
            <>
              {/* Kept mounted so each tab keeps its inputs like Streamlit session state. */}
              <div className="workspace-panel" hidden={tab !== 'analysis'}><AnalysisTab /></div>
              <div className="workspace-panel" hidden={tab !== 'ocr_import'}><OcrTab /></div>
              {tab === 'candidate_pool' && <div className="workspace-panel"><UnmatchedTab /></div>}
              {tab === 'requests' && <div className="workspace-panel"><RequestsTab /></div>}
              <div className="workspace-panel" hidden={tab !== 'regulation_chat'}><ChatTab /></div>
              <div className="workspace-panel" hidden={tab !== 'report'}><ReportTab active={tab === 'report'} /></div>
              {isAdmin && <div className="workspace-panel" hidden={tab !== 'keyword_admin'}><KeywordAdminTab /></div>}
              {isAdmin && <div className="workspace-panel" hidden={tab !== 'user_admin'}><UsersTab /></div>}
            </>
          )}
        </div>
      </main>
    </div>
  )
}
