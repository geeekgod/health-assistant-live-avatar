'use client'

import { useEffect, useRef } from 'react'
import { Loader2, Wrench } from 'lucide-react'
import { formatToolPayload } from '@/lib/phone'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'

export interface ToolCallEvent {
  type: 'tool_call'
  session_id: string
  tool: string
  status: 'running' | 'done' | 'error'
  message: string
  result: Record<string, unknown>
  timestamp: string
}

interface ToolActivityFeedProps {
  events: ToolCallEvent[]
  toolLabels: Record<string, string>
}

function toolLabel(event: ToolCallEvent, toolLabels: Record<string, string>): string {
  return event.message || toolLabels[event.tool] || event.tool.replace(/_/g, ' ')
}

function toolBadgeVariant(status: ToolCallEvent['status']) {
  if (status === 'running') return 'secondary' as const
  if (status === 'done') return 'default' as const
  return 'destructive' as const
}

export default function ToolActivityFeed({ events, toolLabels }: ToolActivityFeedProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  return (
    <div className="flex min-h-0 flex-col border-t border-border">
      <div className="shrink-0 px-4 py-3">
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
          Tool activity
        </p>
      </div>
      <ScrollArea className="max-h-40 min-h-0 flex-1">
        <div className="space-y-2 px-4 pb-4 font-mono text-sm">
          {events.length === 0 ? (
            <p className="text-xs text-muted-foreground/60">No tools invoked yet</p>
          ) : (
            events.map((event, i) => {
              const args = event.result?.args as Record<string, unknown> | undefined
              const displayArgs = args ? formatToolPayload(args) : undefined
              const displayResult =
                event.status !== 'running' && event.result
                  ? formatToolPayload(
                      Object.fromEntries(
                        Object.entries(event.result).filter(([k]) => k !== 'args'),
                      ),
                    )
                  : undefined
              return (
                <div
                  key={`${event.tool}-${event.timestamp}-${i}`}
                  className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-xs font-medium text-amber-100">
                      <Wrench className="h-3 w-3" />
                      {toolLabel(event, toolLabels)}
                    </span>
                    <Badge variant={toolBadgeVariant(event.status)} className="capitalize">
                      {event.status === 'running' ? (
                        <span className="flex items-center gap-1">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          running
                        </span>
                      ) : (
                        event.status
                      )}
                    </Badge>
                  </div>
                  {displayArgs && Object.keys(displayArgs).length > 0 && (
                    <pre className="mt-2 overflow-x-auto rounded-md bg-black/30 p-2 text-[10px] text-muted-foreground">
                      {JSON.stringify(displayArgs, null, 2)}
                    </pre>
                  )}
                  {displayResult && Object.keys(displayResult).length > 0 && (
                    <pre className="mt-2 overflow-x-auto rounded-md bg-black/30 p-2 text-[10px] text-emerald-200/80">
                      {JSON.stringify(displayResult, null, 2)}
                    </pre>
                  )}
                </div>
              )
            })
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>
    </div>
  )
}
