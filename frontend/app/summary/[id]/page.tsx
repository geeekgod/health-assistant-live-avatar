'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getSummary } from '@/lib/api'

function SummarySkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-24 rounded-lg bg-secondary" />
      <div className="h-24 rounded-lg bg-secondary" />
      <p className="text-center text-sm text-muted-foreground">
        Generating summary… (usually under 10 seconds)
      </p>
    </div>
  )
}

function formatFieldLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function SummaryContent({ summary }: { summary: Record<string, unknown> }) {
  const appointmentDate = summary.appointment_date as string | null | undefined
  const appointmentTime = summary.appointment_time as string | null | undefined
  const hasAppointment = appointmentDate || appointmentTime

  const skipKeys = new Set(['bookings', 'tools_used'])
  const scalarFields = Object.entries(summary).filter(
    ([key, val]) =>
      !skipKeys.has(key) &&
      val != null &&
      val !== '' &&
      typeof val !== 'object',
  )

  return (
    <div className="space-y-6">
      {hasAppointment && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg text-green-400">Appointment</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {appointmentDate && <p>Date: {String(appointmentDate)}</p>}
            {appointmentTime && <p>Time: {String(appointmentTime)}</p>}
          </CardContent>
        </Card>
      )}

      {Array.isArray(summary.bookings) && summary.bookings.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg text-green-400">Bookings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(summary.bookings as Array<{ date?: string; time?: string }>).map((b, i) => (
              <div key={i} className="rounded-md bg-secondary/50 p-3 text-sm">
                {b.date && <p>{b.date}</p>}
                {b.time && <p className="text-muted-foreground">{b.time}</p>}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {scalarFields.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg text-blue-400">Call summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {scalarFields.map(([key, val]) => (
              <div key={key} className="border-b border-border pb-2 last:border-0">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                  {formatFieldLabel(key)}
                </p>
                <p className="text-sm">{String(val)}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {Array.isArray(summary.tools_used) && summary.tools_used.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg text-purple-400">Tools used</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {(summary.tools_used as string[]).map((tool) => (
              <Badge key={tool} variant="secondary">
                {tool.replace(/_/g, ' ')}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <details className="rounded-lg border border-border p-4">
        <summary className="cursor-pointer text-sm text-muted-foreground">Raw JSON</summary>
        <pre className="mt-4 overflow-x-auto rounded-md bg-secondary/50 p-4 text-xs">
          {JSON.stringify(summary, null, 2)}
        </pre>
      </details>
    </div>
  )
}

export default function SummaryPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [summaryStatus, setSummaryStatus] = useState<string>('pending')
  const [summaryJson, setSummaryJson] = useState<Record<string, unknown> | null>(null)
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
        const data = await getSummary(sessionId)
        if (cancelled) return
        setSummaryStatus(data.summary_status)

        if (data.summary_status === 'ready' && data.summary_json) {
          setSummaryJson(data.summary_json)
          return
        }
        if (data.summary_status === 'error') {
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
  }, [sessionId, router])

  const pending = summaryStatus === 'pending' || summaryStatus === 'generating'

  return (
    <main className="min-h-screen p-6 md:p-10">
      <div className="mx-auto max-w-2xl">
        <Link href="/" className="text-sm text-primary hover:underline">
          ← New call
        </Link>
        <h1 className="mt-4 text-3xl font-bold">Call summary</h1>
        {sessionId && (
          <p className="mt-2 font-mono text-sm text-muted-foreground">{sessionId}</p>
        )}

        <div className="mt-8">
          {error && (
            <Alert variant="destructive" className="mb-6">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {pending && !summaryJson && !error && <SummarySkeleton />}
          {summaryJson && <SummaryContent summary={summaryJson} />}
        </div>
      </div>
    </main>
  )
}
