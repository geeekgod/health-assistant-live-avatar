import type { AgentConfig } from '@/lib/api'

export const SESSION_STORAGE_KEY = 'health-assistant-session'

export interface StoredSession {
  sessionId: string
  token: string
  url: string
  agent_config: AgentConfig
  avatarProvider: string
  ttsProvider: string
}

export function saveSession(session: StoredSession): void {
  sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session))
}

export function loadSession(): StoredSession | null {
  const raw = sessionStorage.getItem(SESSION_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as StoredSession
  } catch {
    return null
  }
}

export function clearSession(): void {
  sessionStorage.removeItem(SESSION_STORAGE_KEY)
}
