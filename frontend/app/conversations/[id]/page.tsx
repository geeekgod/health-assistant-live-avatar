'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Clock, Headphones, MessageSquare, Wrench } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  getSummary,
  recordingSrc,
  type SummaryResponse,
  type ToolEventRecord,
  type TranscriptEntry,
} from '@/lib/api'
import { formatIndianPhone, formatToolPayload } from '@/lib/phone'

const TOOL_LABELS: Record<string, string> = {
  identify_user: 'Looking up patient record',
  fetch_slots: 'Checking available appointments',
  book_appointment: 'Booking appointment',
  retrieve_appointments: 'Fetching appointments',
  cancel_appointment: 'Cancelling appointment',
  modify_appointment: 'Rescheduling appointment',
  end_conversation: 'Ending call',
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-16 rounded-base border-2 border-foreground bg-secondary shadow-brutal-sm" />
      <div className="h-48 rounded-base border-2 border-foreground bg-secondary shadow-brutal-sm" />
      <div className="h-64 rounded-base border-2 border-foreground bg-secondary shadow-brutal-sm" />
      <p className="text-center text-sm text-muted-foreground">Loading conversation…</p>
    </div>
  )
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function formatFieldLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatFieldValue(key: string, val: unknown): string {
  if (key === 'patient_phone') return formatIndianPhone(val)
  return String(val)
}

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, ' ')
}

function statusBadgeVariant(status: string) {
  if (status === 'success' || status === 'done') return 'default' as const
  if (status === 'error') return 'destructive' as const
  return 'secondary' as const
}

function BriefSummaryCard({ data }: { data: SummaryResponse }) {
  const brief =
    data.brief_summary ||
    (data.summary_json
      ? [
          data.summary_json.patient_name,
          data.summary_json.chief_complaint
            ? `— ${data.summary_json.chief_complaint}`
            : null,
        ]
          .filter(Boolean)
          .join(' ')
      : null)

  return (
    <Card className="bg-accent/20">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">At a glance</CardTitle>
      </CardHeader>
      <CardContent>
        {brief ? (
          <p className="text-sm leading-relaxed text-foreground">{brief}</p>
        ) : (
          <p className="text-sm text-muted-foreground">No summary extracted yet.</p>
        )}
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatTime(data.started_at)}
            {data.ended_at && ` → ${formatTime(data.ended_at)}`}
          </span>
          <Badge variant="outline" className="capitalize">
            {data.status}
          </Badge>
        </div>
      </CardContent>
    </Card>
  )
}

function RecordingSection({ data }: { data: SummaryResponse }) {
  const src = recordingSrc(data.recording_url)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Headphones className="h-4 w-4" />
          Call recording
        </CardTitle>
      </CardHeader>
      <CardContent>
        {src ? (
          <audio controls preload="metadata" className="w-full" src={src}>
            Your browser does not support audio playback.
          </audio>
        ) : (
          <p className="text-sm text-muted-foreground">
            No recording was captured for this call.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

const SCROLL_PANEL_HEIGHT = 'h-96'

function TranscriptSection({ transcript }: { transcript: TranscriptEntry[] }) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageSquare className="h-4 w-4" />
          Transcript
        </CardTitle>
      </CardHeader>
      <CardContent className="min-h-0">
        {transcript.length === 0 ? (
          <p className="text-sm text-muted-foreground">No transcript captured.</p>
        ) : (
          <ScrollArea className={`${SCROLL_PANEL_HEIGHT} w-full rounded-base border-2 border-foreground bg-muted/30`}>
            <div className="space-y-3 p-4">
              {transcript.map((entry, i) => (
                <div
                  key={`${entry.role}-${i}`}
                  className={`rounded-base border-2 px-3 py-2 text-sm shadow-brutal-sm ${
                    entry.role === 'user'
                      ? 'ml-6 border-foreground bg-secondary'
                      : 'mr-6 border-foreground bg-accent/30'
                  }`}
                >
                  <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    {entry.role === 'user' ? 'Caller' : 'Agent'}
                    {entry.timestamp && (
                      <span className="ml-2 font-normal normal-case">
                        {formatTime(entry.timestamp)}
                      </span>
                    )}
                  </p>
                  <p className="leading-relaxed">{entry.text}</p>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}

function ToolTimeline({ events }: { events: ToolEventRecord[] }) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Wrench className="h-4 w-4" />
          Tool execution flow
        </CardTitle>
      </CardHeader>
      <CardContent className="min-h-0">
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tools were invoked.</p>
        ) : (
          <ScrollArea className={`${SCROLL_PANEL_HEIGHT} w-full rounded-base border-2 border-foreground bg-muted/30`}>
            <div className="relative space-y-0 p-4">
            {events.map((event, i) => (
              <div
                key={`${event.tool_name}-${event.timestamp}-${i}`}
                className="relative flex gap-4 pb-6 last:pb-0"
              >
                {i < events.length - 1 && (
                  <div className="absolute left-[11px] top-6 h-[calc(100%-12px)] w-px bg-border" />
                )}
                <div className="relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-base border-2 border-foreground bg-secondary text-[10px] font-bold">
                  {i + 1}
                </div>
                <div className="min-w-0 flex-1 rounded-base border-2 border-foreground bg-card p-3 shadow-brutal-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium">{toolLabel(event.tool_name)}</span>
                    <div className="flex items-center gap-2">
                      {event.timestamp && (
                        <span className="text-[10px] text-muted-foreground">
                          {formatTime(event.timestamp)}
                        </span>
                      )}
                      <Badge variant={statusBadgeVariant(event.status)} className="capitalize">
                        {event.status}
                      </Badge>
                    </div>
                  </div>
                  {event.args && Object.keys(event.args).length > 0 && (
                    <div className="mt-2">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        Input
                      </p>
                      <pre className="mt-1 overflow-x-auto rounded-base border-2 border-foreground bg-secondary p-2 text-[11px]">
                        {JSON.stringify(formatToolPayload(event.args), null, 2)}
                      </pre>
                    </div>
                  )}
                  {event.result && Object.keys(event.result).length > 0 && (
                    <div className="mt-2">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        Output
                      </p>
                      <pre className="mt-1 overflow-x-auto rounded-base border-2 border-foreground bg-accent/30 p-2 text-[11px]">
                        {JSON.stringify(formatToolPayload(event.result), null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}

function StructuredFields({ summary }: { summary: Record<string, unknown> }) {
  const skipKeys = new Set(['bookings', 'tools_used'])
  const fields = Object.entries(summary).filter(
    ([key, val]) =>
      !skipKeys.has(key) && val != null && val !== '' && typeof val !== 'object',
  )

  if (fields.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Extracted fields</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        {fields.map(([key, val]) => (
          <div key={key} className="rounded-base border-2 border-foreground bg-secondary p-3 shadow-brutal-sm">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {formatFieldLabel(key)}
            </p>
            <p className="mt-1 text-sm">{formatFieldValue(key, val)}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

export default function ConversationDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [data, setData] = useState<SummaryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void params.then((p) => setSessionId(p.id))
  }, [params])

  useEffect(() => {
    if (!sessionId) return

    let cancelled = false
    let attempts = 0
    const maxAttempts = 30

    const poll = async () => {
      if (cancelled || attempts >= maxAttempts) {
        if (!cancelled) setError('Summary generation timed out.')
        return
      }
      attempts++

      try {
        const response = await getSummary(sessionId)
        if (cancelled) return
        setData(response)

        if (response.summary_status === 'ready') return
        if (response.summary_status === 'error') {
          setError('Summary generation failed.')
          return
        }
      } catch {
        /* retry */
      }

      setTimeout(poll, 1000)
    }

    poll()
    return () => {
      cancelled = true
    }
  }, [sessionId])

  const pending =
    data?.summary_status === 'pending' || data?.summary_status === 'generating'

  return (
    <main className="min-h-screen p-6 md:p-10">
      <div className="mx-auto max-w-4xl">
        <Link href="/conversations" className="neo-link text-sm">
          ← All conversations
        </Link>
        <h1 className="mt-4 text-4xl font-bold tracking-tight">Conversation</h1>
        {sessionId && (
          <p className="mt-2 font-mono text-sm text-muted-foreground">{sessionId}</p>
        )}

        <div className="mt-8 space-y-6">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {!data && !error && <LoadingSkeleton />}

          {data && (
            <>
              {pending && (
                <p className="text-center text-sm text-muted-foreground">
                  Generating AI summary…
                </p>
              )}
              <BriefSummaryCard data={data} />
              <RecordingSection data={data} />
              <TranscriptSection transcript={data.transcript} />
              <ToolTimeline events={data.tool_events} />
              {data.summary_json && <StructuredFields summary={data.summary_json} />}
            </>
          )}
        </div>
      </div>
    </main>
  )
}
