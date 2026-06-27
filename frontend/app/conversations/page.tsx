'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ChevronRight, MessageSquare } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { listConversations, type ConversationListItem } from '@/lib/api'

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function statusVariant(status: string) {
  if (status === 'ended') return 'secondary' as const
  if (status === 'active') return 'default' as const
  return 'outline' as const
}

export default function ConversationsPage() {
  const [items, setItems] = useState<ConversationListItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await listConversations()
        if (!cancelled) setItems(data)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load conversations')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="min-h-screen p-6 md:p-10">
      <div className="mx-auto max-w-3xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link href="/" className="text-sm text-primary hover:underline">
              ← New call
            </Link>
            <h1 className="mt-4 text-3xl font-bold">Conversations</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Past calls with transcripts, tool activity, and summaries
            </p>
          </div>
        </div>

        <div className="mt-8 space-y-3">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {loading && (
            <p className="text-center text-sm text-muted-foreground">Loading conversations…</p>
          )}

          {!loading && !error && items.length === 0 && (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                <MessageSquare className="h-10 w-10 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">No conversations yet.</p>
                <Link href="/" className="text-sm text-primary hover:underline">
                  Start your first call
                </Link>
              </CardContent>
            </Card>
          )}

          {items.map((item) => (
            <Link key={item.session_id} href={`/conversations/${item.session_id}`}>
              <Card className="transition-colors hover:border-primary/40 hover:bg-card/80">
                <CardContent className="flex items-center gap-4 py-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-mono text-sm">{item.session_id.slice(0, 8)}…</p>
                      <Badge variant={statusVariant(item.status)} className="capitalize">
                        {item.status}
                      </Badge>
                    </div>
                    {item.preview && (
                      <p className="mt-1 truncate text-sm text-muted-foreground">{item.preview}</p>
                    )}
                    <p className="mt-1 text-xs text-muted-foreground">
                      {formatTime(item.started_at)}
                      {item.ended_at && ` → ${formatTime(item.ended_at)}`}
                    </p>
                  </div>
                  <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </main>
  )
}
