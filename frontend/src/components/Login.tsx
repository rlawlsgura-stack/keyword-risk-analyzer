import { useEffect, useState, type FormEvent } from 'react'
import { supabase } from '../lib/supabase.ts'
import { Alert, Button, TextInput } from './ui.tsx'

/** Redirect target for signup/recovery mails: scheme + host + path (L1630). */
export function redirectUrl(): string {
  const configured = import.meta.env.VITE_APP_PUBLIC_URL as string | undefined
  if (configured) return configured
  const { origin, pathname } = window.location
  return origin + pathname
}

type View = 'login' | 'signup' | 'password_reset_request'

/**
 * A message that must survive the login screen being remounted. With e-mail confirmation off,
 * signUp signs the new user in (and we sign them out again), which re-renders the screen.
 */
let pendingFlash = ''

function statusOf(error: unknown): number {
  return Number((error as { status?: number } | null)?.status ?? 0)
}

export function LoginScreen({ flash }: { flash?: string }) {
  const [view, setView] = useState<View>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ text: string; captions: string[] } | null>(null)
  const [info, setInfo] = useState('')
  // Read without clearing (StrictMode runs initializers twice); clear after mount.
  const [success, setSuccess] = useState(() => pendingFlash || flash || '')
  useEffect(() => { pendingFlash = '' }, [])

  const go = (next: View) => { setView(next); setError(null); setInfo(''); setSuccess(''); setPassword(''); setPassword2('') }

  const login = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    setBusy(true); setError(null)
    const { error: err } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    setBusy(false)
    if (err) setError({ text: '로그인에 실패했습니다. 계정과 비밀번호를 확인하세요.', captions: [`Supabase response: ${err.message}`] })
  }

  const signup = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    if (!email.trim() || !password) { setError({ text: '이메일과 비밀번호를 모두 입력하세요.', captions: [] }); return }
    if (password !== password2) { setError({ text: '비밀번호가 서로 다릅니다.', captions: [] }); return }
    setBusy(true); setError(null)
    const { error: err } = await supabase.auth.signUp({ email: email.trim(), password, options: { emailRedirectTo: redirectUrl() } })
    setBusy(false)
    if (err) {
      const status = statusOf(err)
      const captions = [`Supabase response: ${err.message}`]
      if (status === 400) captions.push('가입 허용, Redirect URLs, 이메일 확인 및 비밀번호 정책을 확인하세요.')
      if (status === 429) captions.push('가입 요청 한도에 걸렸습니다. 잠시 후 다시 시도하세요.')
      if (status >= 500) captions.push('Supabase Auth의 확인 이메일 발송(SMTP) 설정을 확인하세요.')
      captions.push(redirectUrl())
      setError({ text: '회원가입 요청을 처리하지 못했습니다.', captions })
      return
    }
    const message = '가입 요청을 처리했습니다. 이메일 확인 후 관리자에게 사용 승인을 요청하세요. 승인 전까지는 앱에 접근할 수 없습니다.'
    pendingFlash = message
    // Supabase may sign the new account in immediately when e-mail confirmation is off.
    await supabase.auth.signOut().catch(() => undefined)
    go('login')
    setSuccess(message)
  }

  const recover = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    if (!email.trim()) { setError({ text: '계정 이메일을 입력하세요.', captions: [] }); return }
    setBusy(true); setError(null); setInfo('')
    const { error: err } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: redirectUrl() })
    setBusy(false)
    if (err) {
      const status = statusOf(err)
      const captions = [`Supabase response: ${err.message}`]
      if (status === 400) captions.push('HTTP 400: Redirect URLs 항목과 아래 이동 주소가 일치하는지 확인하세요.')
      if (status === 429) captions.push('HTTP 429: 요청 한도에 걸렸습니다. 잠시 후 다시 시도하세요.')
      if (status >= 500) captions.push('HTTP 500: Auth 이메일 발송(SMTP) 설정과 이메일 템플릿을 확인하세요.')
      captions.push(redirectUrl())
      setError({ text: '복구 이메일 요청을 실패했습니다.', captions })
      return
    }
    setInfo('해당 이메일의 계정이 있으면 비밀번호 복구 링크를 보냈습니다.')
  }

  return (
    <div className="centered" style={{ maxWidth: '26rem' }}>
      <h3>사내 계정 로그인</h3>
      {success && <Alert kind="success">{success}</Alert>}
      {view === 'login' && (
        <form onSubmit={login} className="stack expander" style={{ padding: '1rem' }}>
          <TextInput label="이메일" type="email" value={email} onChange={setEmail} autoComplete="username" />
          <TextInput label="비밀번호" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
          <div><Button type="submit" disabled={busy}>로그인</Button></div>
        </form>
      )}
      {view === 'signup' && (
        <form onSubmit={signup} className="stack expander" style={{ padding: '1rem' }}>
          <TextInput label="이메일" type="email" value={email} onChange={setEmail} autoComplete="username" />
          <TextInput label="비밀번호" type="password" value={password} onChange={setPassword} autoComplete="new-password" />
          <TextInput label="비밀번호 확인" type="password" value={password2} onChange={setPassword2} autoComplete="new-password" />
          <div><Button type="submit" disabled={busy}>회원가입</Button></div>
        </form>
      )}
      {view === 'password_reset_request' && (
        <form onSubmit={recover} className="stack expander" style={{ padding: '1rem' }}>
          <TextInput label="계정 이메일" type="email" value={email} onChange={setEmail} autoComplete="username" />
          <div><Button type="submit" disabled={busy}>복구 이메일 보내기</Button></div>
        </form>
      )}
      {busy && <span className="spinner" />}
      {error && (
        <>
          <Alert kind="error">{error.text}</Alert>
          {error.captions.map(c => <div key={c} className="caption">{c}</div>)}
        </>
      )}
      {info && <Alert kind="info">{info}</Alert>}
      <div className="stack mt" style={{ alignItems: 'flex-start' }}>
        {view === 'login' ? (
          <>
            <Button onClick={() => go('password_reset_request')}>비밀번호를 잊으셨나요?</Button>
            <Button onClick={() => go('signup')}>회원가입</Button>
          </>
        ) : (
          <Button onClick={() => go('login')}>로그인 화면으로 돌아가기</Button>
        )}
      </div>
    </div>
  )
}

export function NewPasswordScreen({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    if (!password) { setError('새 비밀번호를 입력하세요.'); return }
    if (password !== password2) { setError('두 비밀번호가 서로 다릅니다.'); return }
    setBusy(true); setError('')
    const { error: err } = await supabase.auth.updateUser({ password })
    setBusy(false)
    if (err) { setError('비밀번호를 변경하지 못했습니다. 복구 링크가 만료되었거나 비밀번호 정책을 확인해야 합니다.'); return }
    await supabase.auth.signOut().catch(() => undefined)
    onDone()
  }
  return (
    <div className="centered" style={{ maxWidth: '26rem' }}>
      <h3>새 비밀번호 설정</h3>
      <div className="caption">복구 링크가 확인되었습니다. 새 비밀번호를 입력하세요.</div>
      <form onSubmit={submit} className="stack expander" style={{ padding: '1rem' }}>
        <TextInput label="새 비밀번호" type="password" value={password} onChange={setPassword} autoComplete="new-password" />
        <TextInput label="새 비밀번호 확인" type="password" value={password2} onChange={setPassword2} autoComplete="new-password" />
        <div><Button type="submit" disabled={busy}>비밀번호 변경</Button></div>
      </form>
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
