import { useEffect, useMemo, useRef, useState } from 'react'
import {
  deleteAdminKeywords, downloadKeywordTemplate, loadAdminDropdownSettings, loadApprovedPartials, loadNormalizationSettings,
  saveAdminDropdownSettings, saveAdminKeywords, saveApprovedPartials, saveNormalizationSettings, uploadAdminKeywords,
} from '../lib/api.ts'
import {
  CRITERIA_COL, DATETIME_COLUMNS, REG_DATE_COL, displayHeader, formatDatetime, koSorted, nextKwdNo, normalizedDropdown,
  nowKstString, sortForDisplay, uniqueValues,
} from '../lib/catalog.ts'
import { downloadBlob, downloadCsv } from '../lib/csv.ts'
import { COUNT_COL, DB_COLS, LAST_COL, type ApprovedPartialRules, type DropdownSettings, type KeywordRow } from '../lib/types.ts'
import { useStore } from '../store.tsx'
import { Alert, Button, DataTable, Expander, MultiSelect, Pager, Radio, Select, Spinner, TextArea, TextInput, errorText } from '../components/ui.tsx'

const DIRECT = '(직접 입력)'
const DEFAULT_SYMBOLS = ['/', '&', ',', '*']
type Msg = { kind: 'success' | 'info' | 'warning' | 'error'; text: string } | null

function conflictText(error: unknown): string {
  const text = errorText(error)
  if (/changed|Reload/i.test(text)) return '데이터가 변경되었습니다. 새로 불러온 후 다시 시도하세요.'
  return text
}

export function KeywordAdminTab() {
  const { catalog } = useStore()
  return (
    <div>
      <h3>키워드 관리 (편집/삭제/템플릿/업로드)</h3>
      <Expander title="공통 분석 규칙 — 모든 사용자에게 적용"><CommonRules /></Expander>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div className="col" style={{ flex: 1.15 }}><UploadSection /></div>
        <div className="col" style={{ flex: 1 }}><DeleteSection /></div>
      </div>
      <AddKeywordSection />
      <DropdownDeleteSection />
      {catalog && <CatalogEditor />}
    </div>
  )
}

/* ---------- common analysis rules ---------- */
function CommonRules() {
  const { catalog } = useStore()
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [settings, setSettings] = useState<{ ignored_symbols: string[]; extra_suffixes: string[] } | null>(null)
  const [suffixText, setSuffixText] = useState('')
  const [symbolText, setSymbolText] = useState('')
  const [partials, setPartials] = useState<{ keywords: { kwd_no: string; term: string }[]; rules: ApprovedPartialRules } | null>(null)
  const [selected, setSelected] = useState('')
  const [exprText, setExprText] = useState('')

  const load = async () => {
    try {
      const [s, p] = await Promise.all([loadNormalizationSettings(), loadApprovedPartials()])
      setSettings(s); setSuffixText(s.extra_suffixes.join('\n')); setSymbolText(s.ignored_symbols.join('\n'))
      setPartials(p)
    } catch (e) { setError(`승인 표현을 불러오거나 저장하지 못했습니다: ${errorText(e)}`) }
  }
  useEffect(() => { void load() }, [catalog?.revision]) // eslint-disable-line react-hooks/exhaustive-deps

  const keywordOptions = useMemo(() => (partials?.keywords ?? [])
    .slice().sort((a, b) => a.kwd_no.toLowerCase().localeCompare(b.kwd_no.toLowerCase()))
    .map(k => `${k.kwd_no} · ${k.term}`), [partials])
  useEffect(() => { if (!selected && keywordOptions[0]) setSelected(keywordOptions[0]) }, [keywordOptions, selected])
  const current = partials?.keywords.find(k => `${k.kwd_no} · ${k.term}` === selected)
  const savedRule = current ? partials?.rules[current.kwd_no] : undefined
  const savedExpressions = savedRule && savedRule.term === current?.term ? savedRule.expressions : []
  useEffect(() => { setExprText(savedExpressions.join('\n')) }, [selected, partials]) // eslint-disable-line react-hooks/exhaustive-deps

  const saveRules = async (symbols: string[], suffixes: string[], message: string) => {
    setError(''); setNotice('')
    try {
      const s = await saveNormalizationSettings(symbols.length ? symbols : DEFAULT_SYMBOLS, suffixes)
      setSettings(s); setSuffixText(s.extra_suffixes.join('\n')); setSymbolText(s.ignored_symbols.join('\n'))
      setNotice(message)
    } catch { setError('저장하지 못했습니다. 연결과 권한을 확인하세요.') }
  }

  return (
    <div>
      <div className="caption" style={{ whiteSpace: 'pre-wrap' }}>{'저장한 규칙은 이후 분석부터 모든 사용자에게 적용됩니다.\n\n이번 분석 옵션은 분석하기 탭에서 선택합니다.'}</div>
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      <Expander title="일부 일치 — 승인된 부분 표현">
        <div className="caption" style={{ whiteSpace: 'pre-wrap' }}>{'FIXED275 일부 일치에만 적용합니다. 공통 내용어 토큰은 승인 없이 자동 검사합니다.\n\n자동 분석에서 누락된 의미 있는 부분 표현만 키워드별로 승인하세요.\n\n예시) 안티에이징 → 에이징. 티에이 같은 무의미한 조각은 승인하지 마세요.\n\n등록명을 바꾸면 기존 승인은 적용되지 않습니다.'}</div>
        {!partials ? <Spinner /> : !partials.keywords.length ? <Alert kind="info">먼저 키워드를 등록하세요.</Alert> : (
          <form className="stack mt" onSubmit={async e => {
            e.preventDefault()
            if (!current) return
            setError(''); setNotice('')
            try {
              const expressions = exprText.split('\n').map(s => s.trim()).filter(Boolean)
              await saveApprovedPartials(current.kwd_no, current.term, savedExpressions, expressions)
              await load()
              setNotice('승인 표현을 저장했습니다. 다음 분석부터 적용됩니다.')
            } catch (err) { setError(`승인 표현을 불러오거나 저장하지 못했습니다: ${errorText(err)}`) }
          }}>
            <Select label="승인할 키워드" value={selected} options={keywordOptions} onChange={setSelected} />
            <TextArea label="승인할 부분 표현 — 한 줄에 하나" value={exprText} onChange={setExprText} />
            <div><Button type="submit">승인 표현 저장</Button></div>
          </form>
        )}
      </Expander>
      <Expander title="기존 API용 조사·어미 허용 목록">
        <div className="caption" style={{ whiteSpace: 'pre-wrap' }}>{'기존 similar API의 변형 규칙 검사에서만 참조합니다.\n\n현재 화면의 완전 일치와 일부 일치에는 적용하지 않습니다.'}</div>
        <div className="caption" style={{ whiteSpace: 'pre-wrap' }}>{'기본 목록과 추가 목록을 합쳐 사용합니다.\n\n별도 합성어 규칙도 적용합니다.\n\n예시) 등록 키워드: 여드름\n\n- O · 입력 여드름에는 → 여드름 검출\n- X · 입력 뾰루지 → 여드름 미검출'}</div>
        <div className="caption">으로·로·에는은 이미 기본 목록에 포함되어 있어 추가로 저장하지 않아도 됩니다.</div>
        <div className="caption">기본 목록은 서버 공통 설정입니다.</div>
        <TextArea label="추가로 허용할 말 — 한 줄에 하나 또는 쉼표로 구분" value={suffixText} onChange={setSuffixText} />
        <div className="row tight mt">
          <Button onClick={() => saveRules(settings?.ignored_symbols ?? DEFAULT_SYMBOLS,
            [...new Set(suffixText.split(/[\n,]+/).map(s => s.trim()).filter(Boolean))], '허용 목록을 저장했습니다. 이후 분석부터 공통 적용됩니다.')}>허용 목록 저장</Button>
          <Button onClick={() => saveRules(settings?.ignored_symbols ?? DEFAULT_SYMBOLS, [], '허용 목록을 저장했습니다. 이후 분석부터 공통 적용됩니다.')}>추가 항목 모두 제거</Button>
        </div>
      </Expander>
      <Expander title="공백으로 처리할 기호 목록">
        <div className="caption" style={{ whiteSpace: 'pre-wrap' }}>{'분석 화면에서 기호 처리를 켜면 이 목록의 기호를 공백으로 바꿉니다.\n\n띄어쓰기 차이 허용은 별도로 선택합니다.'}</div>
        <div className="caption" style={{ whiteSpace: 'pre-wrap' }}>{'기호는 한 줄에 하나씩 입력하세요.\n\n쉼표(,)도 한 줄에 그대로 입력합니다.\n\n목록을 비우면 기존 기본값 / & , *가 적용됩니다.'}</div>
        <TextArea label="비교 시 처리할 기호 — 한 줄에 하나" value={symbolText} onChange={setSymbolText} />
        <div className="row tight mt">
          <Button onClick={() => {
            const symbols = [...new Set(symbolText.split('\n').map(s => s.trim()).filter(Boolean))]
            if (symbols.some(s => [...s].length !== 1)) { setError('각 줄에는 문자 하나만 입력하세요. 저장하지 않았습니다.'); return }
            void saveRules(symbols, settings?.extra_suffixes ?? [], '기호 목록을 저장했습니다. 이후 분석부터 공통 적용됩니다.')
          }}>기호 목록 저장</Button>
          <Button onClick={() => saveRules(DEFAULT_SYMBOLS, settings?.extra_suffixes ?? [], '기호 목록을 저장했습니다. 이후 분석부터 공통 적용됩니다.')}>기본 기호로 복원</Button>
        </div>
      </Expander>
    </div>
  )
}

/* ---------- upload ---------- */
function UploadSection() {
  const { catalog, reloadCatalog } = useStore()
  const [mode, setMode] = useState<'merge' | 'overwrite'>('merge')
  const [file, setFile] = useState<File | null>(null)
  const [msg, setMsg] = useState<Msg>(null)
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const upload = async () => {
    if (!file) return
    setBusy(true); setMsg(null)
    try {
      const fresh = await reloadCatalog()
      const result = await uploadAdminKeywords(file, mode, fresh?.revision ?? catalog?.revision ?? 0)
      await reloadCatalog()
      setMsg({ kind: 'success', text: `업로드 완료 — 추가 ${result.added_count}건, (내부 중복제거 ${result.dedup_removed}건) 저장됨.` })
      setFile(null); if (input.current) input.current.value = ''
    } catch (e) {
      await reloadCatalog()
      setMsg({ kind: 'error', text: `업로드 처리 중 오류: ${conflictText(e)}` })
    } finally { setBusy(false) }
  }
  return (
    <div>
      <h4>📂 키워드 업로드 (.csv / .xlsx)</h4>
      <Radio label="업로드 모드" value={mode} options={['merge', 'overwrite'] as const}
        format={m => (m === 'merge' ? '기존 유지 + 새로 추가' : '완전 덮어쓰기')} onChange={setMode} />
      <label className="field mt">키워드 템플릿 업로드</label>
      <input ref={input} type="file" accept=".csv,.xlsx" onChange={e => {
        const f = e.target.files?.[0] ?? null
        if (f && !/\.(csv|xlsx)$/i.test(f.name)) { setMsg({ kind: 'error', text: '지원하지 않는 파일 형식입니다. CSV 또는 XLSX를 업로드하세요.' }); setFile(null); return }
        setMsg(null); setFile(f)
      }} />
      <div className="row tight mt">
        <Button primary disabled={!file || busy} onClick={upload}>업로드</Button>
      </div>
      {busy && <Spinner />}
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <label className="field mt">업로드 템플릿 다운로드</label>
      <div className="row tight">
        <Button onClick={() => downloadCsv('keyword_template.csv', DB_COLS, [])}>CSV 템플릿 다운로드</Button>
        <Button onClick={async () => {
          try { downloadBlob(await downloadKeywordTemplate(), 'keyword_template.xlsx') }
          catch (e) { setMsg({ kind: 'info', text: `엑셀 템플릿은 현재 환경에 openpyxl/xlsxwriter가 없어 CSV 템플릿으로 대체합니다. (세부: ${errorText(e)})` }) }
        }}>엑셀 템플릿 다운로드</Button>
      </div>
    </div>
  )
}

/* ---------- delete ---------- */
function DeleteSection() {
  const { catalog, reloadCatalog } = useStore()
  const [codes, setCodes] = useState<string[]>([])
  const [confirming, setConfirming] = useState(false)
  const [msg, setMsg] = useState<Msg>(null)
  const options = useMemo(() => (catalog?.rows ?? []).map(r => String(r.kwd_no)).sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())), [catalog])
  const run = async () => {
    setMsg(null)
    try {
      const fresh = await reloadCatalog()
      const result = await deleteAdminKeywords(fresh?.revision ?? 0, codes)
      await reloadCatalog()
      setMsg({ kind: 'success', text: `${result.deleted}건 삭제 완료` })
      setCodes([]); setConfirming(false)
    } catch (e) { setConfirming(false); setMsg({ kind: 'error', text: conflictText(e) }) }
  }
  return (
    <div>
      <h4>키워드 삭제</h4>
      <MultiSelect label="삭제할 항목 선택 (kwd_no 기준)" value={codes} options={options} onChange={v => { setCodes(v); setConfirming(false) }} />
      <div className="mt">
        {!confirming ? (
          <Button onClick={() => { if (!codes.length) { setMsg({ kind: 'warning', text: '삭제할 항목을 선택하세요.' }); return } setMsg(null); setConfirming(true) }}>선택 삭제</Button>
        ) : (
          <>
            <Alert kind="warning">{`선택한 ${codes.length}건을 삭제합니다. 삭제한 키워드는 되돌릴 수 없습니다.`}</Alert>
            <div className="row tight"><Button onClick={() => setConfirming(false)}>취소</Button><Button primary onClick={run}>삭제 확인</Button></div>
          </>
        )}
      </div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
    </div>
  )
}

/* ---------- add keyword ---------- */
function AddKeywordSection() {
  const { catalog, reloadCatalog, reloadDropdowns } = useStore()
  const [settings, setSettings] = useState<DropdownSettings | null>(null)
  const [term, setTerm] = useState('')
  const [category, setCategory] = useState('')
  const [risk, setRisk] = useState('')
  const [detail, setDetail] = useState('')
  const [evidence, setEvidence] = useState('')
  const [alt, setAlt] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [customCode, setCustomCode] = useState('')
  const [newDetail, setNewDetail] = useState('')
  const [newEvidence, setNewEvidence] = useState('')
  const [newAlt, setNewAlt] = useState('')
  const [msg, setMsg] = useState<Msg>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { loadAdminDropdownSettings().then(setSettings).catch(() => undefined) }, [catalog?.revision])

  const rows = catalog?.rows ?? []
  const lists = useMemo(() => ({
    category: [...koSorted(uniqueValues(rows, '상품카테고리')), DIRECT],
    risk: koSorted(uniqueValues(rows, '리스크 등급')),
    detail: [...normalizedDropdown(settings?.opt_details ?? []), DIRECT],
    evidence: [...normalizedDropdown(uniqueValues(rows, '증빙자료유형')), DIRECT],
    alt: [...normalizedDropdown(settings?.opt_alt_terms ?? []), DIRECT],
  }), [rows, settings])
  const pick = (value: string, list: string[]) => (list.includes(value) ? value : list[0] ?? '')
  const cat = pick(category, lists.category), rk = pick(risk, lists.risk), dt = pick(detail, lists.detail)
  const ev = pick(evidence, lists.evidence), al = pick(alt, lists.alt)

  const add = async () => {
    setMsg(null)
    if (!term.trim()) { setMsg({ kind: 'error', text: '키워드명은 필수입니다.' }); return }
    const resolve = (choice: string, typed: string) => (choice === DIRECT ? typed.trim() : choice)
    const finalCat = resolve(cat, newCategory), finalDetail = resolve(dt, newDetail), finalEv = resolve(ev, newEvidence), finalAlt = resolve(al, newAlt)
    if ([[cat, finalCat], [dt, finalDetail], [ev, finalEv], [al, finalAlt]].some(([c, v]) => c === DIRECT && !v)) {
      setMsg({ kind: 'error', text: '새 항목을 입력했으면 값을 채우거나 기존 목록에서 선택하세요.' }); return
    }
    setBusy(true)
    try {
      const fresh = await reloadCatalog()
      if (!fresh) throw new Error('키워드 DB를 불러오지 못했습니다.')
      let code = ''
      const custom = /^([A-Za-z]+)(\d+)$/.exec(customCode.trim())
      if (cat === DIRECT && custom) code = custom[1].toUpperCase() + custom[2]
      if (code && fresh.rows.some(r => String(r.kwd_no).trim().toLowerCase() === code.toLowerCase())) {
        setMsg({ kind: 'warning', text: `${code}은(는) 이미 존재하는 키워드 번호입니다. 다른 번호를 지정해 주세요.` }); return
      }
      if (!code) code = nextKwdNo(finalCat, fresh.rows)
      const newRow: KeywordRow = Object.fromEntries(fresh.columns.map(c => [c, ''])) as KeywordRow
      Object.assign(newRow, {
        kwd_no: code, '키워드명': term.trim(), '상품카테고리': finalCat, '리스크 등급': rk, '대체키워드': finalAlt,
        [CRITERIA_COL]: finalDetail, '증빙자료유형': finalEv, [COUNT_COL]: '0', [LAST_COL]: '', [REG_DATE_COL]: nowKstString(),
      })
      await saveAdminKeywords(fresh.revision ?? 0, [...fresh.rows, newRow])
      await reloadCatalog()
      setMsg({ kind: 'success', text: `[${code}] '${term.trim()}' 추가 및 저장됨` })
      // Newly typed values join their dropdown lists (L5627-5638).
      if (settings && (cat === DIRECT || dt === DIRECT || ev === DIRECT || al === DIRECT)) {
        const next = { ...settings }
        if (cat === DIRECT) next.opt_categories = [...new Set([...next.opt_categories, finalCat])]
        if (dt === DIRECT) next.opt_details = [...new Set([...next.opt_details, finalDetail])]
        if (ev === DIRECT) next.opt_evidences = [...new Set([...next.opt_evidences, finalEv])]
        if (al === DIRECT) next.opt_alt_terms = [...new Set([...next.opt_alt_terms, finalAlt])]
        setSettings(await saveAdminDropdownSettings(next))
        await reloadDropdowns()
      }
      setTerm(''); setNewCategory(''); setCustomCode(''); setNewDetail(''); setNewEvidence(''); setNewAlt('')
    } catch (e) {
      await reloadCatalog()
      setMsg({ kind: 'error', text: conflictText(e) })
    } finally { setBusy(false) }
  }

  return (
    <div className="mt">
      <h3>키워드 입력/관리</h3>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div className="col"><TextInput label="키워드명 *" value={term} onChange={setTerm} placeholder="예: 필러" /></div>
        <div className="col"><Select label="상품카테고리" value={cat} options={lists.category} onChange={setCategory} /></div>
        <div className="col"><Select label="리스크 등급" value={rk} options={lists.risk} onChange={setRisk} /></div>
      </div>
      <div className="row mt" style={{ alignItems: 'flex-start' }}>
        <div className="col"><Select label="리스크 등급별 세부 심의기준" value={dt} options={lists.detail} onChange={setDetail} /></div>
        <div className="col"><Select label="증빙자료유형" value={ev} options={lists.evidence} onChange={setEvidence} /></div>
        <div className="col"><Select label="대체키워드" value={al} options={lists.alt} onChange={setAlt} /></div>
      </div>
      {cat === DIRECT && (
        <div className="row mt">
          <div className="col" style={{ flex: 2 }}><TextInput label="새 카테고리 입력" value={newCategory} onChange={setNewCategory} /></div>
          <div className="col"><TextInput label="키워드NO (선택, 예: P001)" value={customCode} onChange={setCustomCode} /></div>
        </div>
      )}
      {dt === DIRECT && <div className="mt"><TextInput label="새 세부 심의기준 입력" value={newDetail} onChange={setNewDetail} /></div>}
      {ev === DIRECT && <div className="mt"><TextInput label="새 증빙자료유형 입력" value={newEvidence} onChange={setNewEvidence} /></div>}
      {al === DIRECT && <div className="mt"><TextInput label="새 대체키워드 입력" value={newAlt} onChange={setNewAlt} /></div>}
      <div className="mt"><Button primary onClick={add} disabled={busy}>추가</Button></div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
    </div>
  )
}

/* ---------- dropdown value deletion ---------- */
const DROPDOWN_TARGETS: Record<string, keyof DropdownSettings> = {
  '대체키워드': 'opt_alt_terms', '리스크 등급': 'opt_risks', '리스크 등급별 세부 심의기준': 'opt_details', '상품카테고리': 'opt_categories', '증빙자료유형': 'opt_evidences',
}
function DropdownDeleteSection() {
  const { reloadDropdowns } = useStore()
  const [settings, setSettings] = useState<DropdownSettings | null>(null)
  const [target, setTarget] = useState(koSorted(Object.keys(DROPDOWN_TARGETS))[0])
  const [value, setValue] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [msg, setMsg] = useState<Msg>(null)
  useEffect(() => { loadAdminDropdownSettings().then(setSettings).catch(() => undefined) }, [])
  const values = settings ? koSorted(settings[DROPDOWN_TARGETS[target]]) : []
  useEffect(() => { setValue(values[0] ?? ''); setConfirming(false) }, [target, settings]) // eslint-disable-line react-hooks/exhaustive-deps
  const run = async () => {
    if (!settings) return
    const key = DROPDOWN_TARGETS[target]
    if (!settings[key].includes(value)) { setMsg({ kind: 'info', text: '이미 삭제되었거나 존재하지 않습니다.' }); setConfirming(false); return }
    try {
      const saved = await saveAdminDropdownSettings({ ...settings, [key]: settings[key].filter(v => v !== value) })
      setSettings(saved); await reloadDropdowns()
      setMsg({ kind: 'success', text: `삭제 완료: ${target} → ${value}` })
    } catch (e) { setMsg({ kind: 'error', text: errorText(e) }) }
    setConfirming(false)
  }
  return (
    <Expander title="드롭다운 값 삭제 (관리자)">
      <Select label="대상 목록" value={target} options={koSorted(Object.keys(DROPDOWN_TARGETS))} onChange={setTarget} />
      {values.length > 0 && <div className="mt"><Select label="삭제할 값 선택" value={value} options={values} onChange={setValue} /></div>}
      <div className="mt">
        {!confirming ? (
          <Button onClick={() => { if (!value) { setMsg({ kind: 'warning', text: '삭제할 값을 선택하세요.' }); return } setMsg(null); setConfirming(true) }}>삭제</Button>
        ) : (
          <>
            <Alert kind="warning">{`${target}에서 '${value}' 값을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}</Alert>
            <div className="row tight"><Button primary onClick={run}>예, 삭제</Button><Button onClick={() => setConfirming(false)}>아니오</Button></div>
          </>
        )}
      </div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
    </Expander>
  )
}

/* ---------- editable catalog ---------- */
type EditMode = 'dropdown' | 'free'
const READ_ONLY = new Set(['kwd_no', COUNT_COL, LAST_COL])
const PAGE_SIZE = 100

function CatalogEditor() {
  const { catalog, dropdowns, reloadCatalog } = useStore()
  const [mode, setMode] = useState<EditMode>('dropdown')
  const [drafts, setDrafts] = useState<Record<EditMode, Record<string, Record<string, string>>>>({ dropdown: {}, free: {} })
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<{ code: string; column: string } | null>(null)
  const [msg, setMsg] = useState<Msg>(null)
  const [busy, setBusy] = useState(false)
  if (!catalog) return null
  const rows = sortForDisplay(catalog.rows)
  const columns = catalog.columns
  const edits = drafts[mode]
  const dirty = Object.keys(edits).length

  const selectOptions = (column: string): string[] | null => {
    if (mode !== 'dropdown') return null
    const values = (c: string) => uniqueValues(catalog.rows, c)
    if (column === '상품카테고리') return ['', ...koSorted(new Set([...(dropdowns?.opt_categories ?? []), ...values(column)]))]
    if (column === '리스크 등급') return ['', ...koSorted(new Set([...(dropdowns?.opt_risks ?? []), ...values(column)]))]
    if (column === CRITERIA_COL) return ['', ...normalizedDropdown([...(dropdowns?.opt_details ?? []), ...values(column)]), DIRECT]
    if (column === '증빙자료유형') return ['', ...koSorted(new Set([...(dropdowns?.opt_evidences ?? []), ...values(column)]))]
    if (column === '대체키워드') return ['', ...normalizedDropdown([...(dropdowns?.opt_alt_terms ?? []), ...values(column)]), DIRECT]
    return null
  }

  const valueOf = (row: KeywordRow, column: string) => edits[row.kwd_no]?.[column] ?? String(row[column] ?? '')
  const setValue = (code: string, column: string, value: string) => setDrafts(d => {
    const original = String(catalog.rows.find(r => r.kwd_no === code)?.[column] ?? '')
    const rowEdits = { ...(d[mode][code] ?? {}) }
    if (value === original) delete rowEdits[column]; else rowEdits[column] = value
    const modeEdits = { ...d[mode] }
    if (Object.keys(rowEdits).length) modeEdits[code] = rowEdits; else delete modeEdits[code]
    return { ...d, [mode]: modeEdits }
  })

  const save = async () => {
    setMsg(null); setBusy(true)
    try {
      const fresh = await reloadCatalog()
      if (!fresh || fresh.revision !== catalog.revision) throw new Error('changed')
      const out = fresh.rows.map(r => {
        const e = edits[r.kwd_no]
        return e ? { ...r, ...e } : r
      })
      await saveAdminKeywords(fresh.revision ?? 0, out)
      await reloadCatalog()
      setDrafts({ dropdown: {}, free: {} })
      setMsg({ kind: 'success', text: '수정 내용 저장 완료' })
    } catch (e) {
      await reloadCatalog()
      setMsg({ kind: 'error', text: conflictText(e) === 'changed' ? '데이터가 변경되었습니다. 새로 불러온 후 다시 시도하세요.' : conflictText(e) })
    } finally { setBusy(false) }
  }

  const pageRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))

  return (
    <div className="mt">
      <hr />
      <Radio label="편집 모드 선택" horizontal value={mode} options={['dropdown', 'free'] as const}
        format={m => (m === 'dropdown' ? '드롭다운(제한 입력)' : '자유 입력')} onChange={m => { setMode(m); setEditing(null) }} />
      <div className="caption">셀을 클릭해 수정한 뒤 변경사항 저장을 누르세요. kwd_no·조회 수·마지막 검색일자는 수정할 수 없습니다.{dirty ? ` 수정 대기: ${dirty}행` : ''}</div>
      <div className="table-wrap mt">
        <table className="grid">
          <thead><tr><th className="num"></th>{columns.map(c => <th key={c}>{displayHeader(c)}</th>)}</tr></thead>
          <tbody>
            {pageRows.map((row, i) => (
              <tr key={row.kwd_no}>
                <td className="num idx">{(page - 1) * PAGE_SIZE + i}</td>
                {columns.map(c => {
                  const value = valueOf(row, c)
                  const changed = edits[row.kwd_no]?.[c] !== undefined
                  const isEditing = editing?.code === row.kwd_no && editing.column === c
                  if (READ_ONLY.has(c)) return <td key={c}>{DATETIME_COLUMNS.has(c) ? formatDatetime(value) : value}</td>
                  if (!isEditing) {
                    return (
                      <td key={c} tabIndex={0} style={{ cursor: 'text', background: changed ? '#fff7d6' : undefined }}
                        onClick={() => setEditing({ code: row.kwd_no, column: c })}
                        onKeyDown={e => { if (e.key === 'Enter') setEditing({ code: row.kwd_no, column: c }) }}>
                        {DATETIME_COLUMNS.has(c) ? formatDatetime(value) : value}
                      </td>
                    )
                  }
                  const opts = selectOptions(c)
                  return (
                    <td key={c}>
                      {opts ? (
                        <select autoFocus value={value} onBlur={() => setEditing(null)} onChange={e => setValue(row.kwd_no, c, e.target.value)}>
                          {(opts.includes(value) ? opts : [...opts, value]).map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <textarea autoFocus rows={c === CRITERIA_COL ? 4 : 1} value={value} onBlur={() => setEditing(null)}
                          onChange={e => setValue(row.kwd_no, c, e.target.value)}
                          onKeyDown={e => { if (e.key === 'Escape') setEditing(null) }} />
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager page={page} pageCount={pageCount} onChange={setPage} total={rows.length} pageSize={PAGE_SIZE} />
      <div className="row tight mt">
        <Button primary onClick={save} disabled={busy || !dirty}>변경사항 저장</Button>
        {dirty > 0 && <Button onClick={() => setDrafts(d => ({ ...d, [mode]: {} }))}>수정 취소</Button>}
      </div>
      {busy && <Spinner />}
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div className="caption mt">현재 저장된 항목: {catalog.rows.length}</div>
      <DataTable rows={rows} rowKey={r => r.kwd_no}
        columns={columns.map(c => ({ key: c, label: displayHeader(c), render: (r: KeywordRow) => (DATETIME_COLUMNS.has(c) ? formatDatetime(r[c]) : r[c] ?? '') }))} />
    </div>
  )
}
