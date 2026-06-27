const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type AvatarProvider = 'bey' | 'tavus'
export type TtsProvider = 'cartesia' | 'gemini'

export interface AgentConfig {
  system_prompt?: string
  greeting?: string
  template_id?: string
  tool_labels?: Record<string, string>
}

export interface CreateSessionResponse {
  sessionId: string
  token: string
  url: string
  agent_config: AgentConfig
}

export interface TranscriptEntry {
  role: string
  text: string
  source?: string
  timestamp?: string
}

export interface ToolEventRecord {
  tool_name: string
  status: string
  args: Record<string, unknown>
  result: Record<string, unknown>
  timestamp: string | null
}

export interface ConversationListItem {
  session_id: string
  template_id: string
  status: string
  summary_status: string
  started_at: string | null
  ended_at: string | null
  preview: string | null
}

export interface SummaryResponse {
  session_id: string
  template_id: string
  status: string
  summary_status: string
  summary_json: Record<string, unknown> | null
  brief_summary: string | null
  started_at: string | null
  ended_at: string | null
  transcript: TranscriptEntry[]
  tool_events: ToolEventRecord[]
  recording_available: boolean
  recording_url: string | null
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body.detail ?? res.statusText
  } catch {
    return res.statusText
  }
}

export async function createSession(
  avatar: AvatarProvider,
  tts: TtsProvider,
): Promise<CreateSessionResponse> {
  const res = await fetch(`${API_URL}/api/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      template_id: 'healthcare_front_desk',
      avatar_provider: avatar,
      tts_provider: tts,
    }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function endSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/sessions/${sessionId}/end`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function listConversations(): Promise<ConversationListItem[]> {
  const res = await fetch(`${API_URL}/api/sessions`, { cache: 'no-store' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function getSummary(sessionId: string): Promise<SummaryResponse> {
  const res = await fetch(`${API_URL}/api/summaries/${sessionId}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export function recordingSrc(recordingUrl: string | null): string | null {
  if (!recordingUrl) return null
  if (recordingUrl.startsWith('http')) return recordingUrl
  return `${API_URL}${recordingUrl}`
}

export { API_URL }
