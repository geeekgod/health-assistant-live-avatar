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

const TOOL_LABELS: Record<string, string> = {
  identify_user: 'Looking up patient record',
  fetch_slots: 'Checking available appointments',
  book_appointment: 'Booking appointment',
  retrieve_appointments: 'Fetching appointments',
  cancel_appointment: 'Cancelling appointment',
  modify_appointment: 'Rescheduling appointment',
  end_conversation: 'Ending call',
}

function SummarySkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-16 rounded-lg bg-secondary" />
      <div className="h-48 rounded-lg bg-secondary" />
      <div className="h-64 rounded-lg bg-secondary" />
      <p className="text-center text-sm text-muted-foreground">
        Generating summary… (usually under 10 seconds)
      </p>
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
    <Card className="border-primary/30 bg-primary/5">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium">At a glance</CardTitle>
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
            No recording available for this session. Drop a{' '}
            <code className="rounded bg-secondary px-1 text-xs">.wav</code> or{' '}
            <code className="rounded bg-secondary px-1 text-xs">.mp3</code> file at{' '}
            <code className="rounded bg-secondary px-1 text-xs">
              backend/recordings/{data.session_id}.wav
            </code>{' '}
            to enable playback.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function TranscriptSection({ transcript }: { transcript: TranscriptEntry[] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageSquare className="h-4 w-4" />
          Transcript
        </CardTitle>
      </CardHeader>
      <CardContent>
        {transcript.length === 0 ? (
          <p className="text-sm text-muted-foreground">No transcript captured.</p>
        ) : (
          <ScrollArea className="max-h-[28rem]">
            <div className="space-y-3 pr-4">
              {transcript.map((entry, i) => (
                <div
                  key={`${entry.role}-${i}`}
                  className={`rounded-lg px-3 py-2 text-sm ${
                    entry.role === 'user'
                      ? 'ml-6 bg-blue-500/10 text-blue-100'
                      : 'mr-6 bg-secondary/80'
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
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Wrench className="h-4 w-4" />
          Tool execution flow
        </CardTitle>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tools were invoked.</p>
        ) : (
          <div className="relative space-y-0">
            {events.map((event, i) => (
              <div key={`${event.tool_name}-${event.timestamp}-${i}`} className="relative flex gap-4 pb-6 last:pb-0">
                {i < events.length - 1 && (
                  <div className="absolute left-[11px] top-6 h-[calc(100%-12px)] w-px bg-border" />
                )}
                <div className="relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-[10px] font-bold text-amber-200">
                  {i + 1}
                </div>
                <div className="min-w-0 flex-1 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
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
                      <pre className="mt-1 overflow-x-auto rounded-md bg-black/30 p-2 text-[11px] text-muted-foreground">
                        {JSON.stringify(event.args, null, 2)}
                      </pre>
                    </div>
                  )}
                  {event.result && Object.keys(event.result).length > 0 && (
                    <div className="mt-2">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        Output
                      </p>
                      <pre className="mt-1 overflow-x-auto rounded-md bg-black/30 p-2 text-[11px] text-emerald-200/80">
                        {JSON.stringify(event.result, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
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
          <div key={key} className="rounded-md bg-secondary/50 p-3">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {formatFieldLabel(key)}
            </p>
            <p className="mt-1 text-sm">{String(val)}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

export default function SummaryPage({ params }: { params: Promise<{ id: string }> }) {
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
        <Link href="/" className="text-sm text-primary hover:underline">
          ← New call
        </Link>
        <h1 className="mt-4 text-3xl font-bold">Call summary</h1>
        {sessionId && (
          <p className="mt-2 font-mono text-sm text-muted-foreground">{sessionId}</p>
        )}

        <div className="mt-8 space-y-6">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {!data && !error && <SummarySkeleton />}

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
