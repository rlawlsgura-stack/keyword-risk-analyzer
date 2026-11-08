import { createClient, type SupabaseClient } from '@supabase/supabase-js'

export const SUPABASE_URL: string = import.meta.env.VITE_SUPABASE_URL ?? ''
export const SUPABASE_PUBLISHABLE_KEY: string = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? ''
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export const configurationReady = Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY && API_BASE_URL)

// Streamlit keeps only the refresh token for the current browser tab; sessionStorage
// gives the same "survives refresh, cleared when the tab closes" behaviour.
export const supabase: SupabaseClient | null = configurationReady
  ? createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
      auth: {
        storage: window.sessionStorage,
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: 'implicit',
      },
    })
  : null
