'use client'

import { Suspense, useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useLocalParticipant,
  useRoomContext,
} from '@livekit/components-react'
import '@livekit/components-styles'
import { Mic, MicOff, PhoneOff } from 'lucide-react'
import { RoomEvent } from 'livekit-client'
import AvatarVideo from '@/components/AvatarVideo'
import ChatInput from '@/components/ChatInput'
import ToolActivityFeed, { type ToolCallEvent } from '@/components/ToolActivityFeed'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { endSession } from '@/lib/api'
import { clearSession, loadSession, type StoredSession } from '@/lib/session'
import {
  mergeAuthoritativeTurn,
  mergeSttPreview,
  type TranscriptSegment,
} from '@/lib/transcript'

type CallStatus = 'idle' | 'connecting' | 'connected' | 'ending' | 'ended' | 'failed'

interface CallState {
  status: CallStatus
  error: string | null
}

type CallAction =
  | { type: 'ROOM_CONNECTED' }
  | { type: 'START_ENDING' }
  | { type: 'ROOM_DISCONNECTED' }
  | { type: 'ERROR'; message: string }

interface TranscriptDataEvent {
  type: 'transcript'
  session_id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: string
}

const initialState: CallState = { status: 'connecting', error: null }

function callReducer(state: CallState, action: CallAction): CallState {
  switch (action.type) {
    case 'ROOM_CONNECTED':
      return { ...state, status: 'connected' }
    case 'START_ENDING':
      return { ...state, status: 'ending' }
    case 'ROOM_DISCONNECTED':
      return { ...state, status: 'ended' }
    case 'ERROR':
      return { ...state, status: 'failed', error: action.message }
    default:
      return state
  }
}

function TranscriptFeed({ transcript }: { transcript: TranscriptSegment[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript.length])

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="space-y-3 p-4 font-mono text-sm">
        {transcript.length === 0 ? (
          <p className="text-muted-foreground/60">Waiting for conversation…</p>
        ) : (
          transcript.map((segment) => {
            const isUser = segment.speaker === 'user'
            return (
              <div
                key={`${segment.speaker}-${segment.id}-${segment.timestamp}`}
                className={cn(
                  'rounded-base border-2 p-3 shadow-brutal-sm transition-all',
                  isUser
                    ? 'border-foreground bg-secondary'
                    : 'border-foreground bg-accent/40',
                  !segment.isFinal && 'opacity-70',
                )}
              >
                <p className="mb-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  {isUser ? 'You' : 'Agent'}
                  {!segment.isFinal && ' · listening…'}
                </p>
                <p className="leading-relaxed">{segment.text}</p>
              </div>
            )
          })
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}

function CallUI({
  session,
  state,
  dispatch,
  toolEvents,
  transcript,
  onToolEvent,
  onTranscriptPreview,
  onAuthoritativeTurn,
}: {
  session: StoredSession
  state: CallState
  dispatch: React.Dispatch<CallAction>
  toolEvents: ToolCallEvent[]
  transcript: TranscriptSegment[]
  onToolEvent: (e: ToolCallEvent) => void
  onTranscriptPreview: (segment: TranscriptSegment) => void
  onAuthoritativeTurn: (role: 'user' | 'assistant', text: string, timestamp: number) => void
}) {
  const room = useRoomContext()
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant()
  const toolLabels = session.agent_config.tool_labels ?? {}

  useEffect(() => {
    const handler = (payload: Uint8Array) => {
      try {
        const event = JSON.parse(new TextDecoder().decode(payload))
        if (event.type === 'tool_call') {
          onToolEvent(event)
          if (event.tool === 'end_conversation' && event.status === 'done') {
            dispatch({ type: 'START_ENDING' })
          }
        } else if (event.type === 'transcript') {
          const turn = event as TranscriptDataEvent
          const ts = Date.parse(turn.timestamp) || Date.now()
          onAuthoritativeTurn(turn.role, turn.text, ts)
        }
      } catch {
        /* ignore malformed payloads */
      }
    }
    room.on(RoomEvent.DataReceived, handler)
    return () => {
      room.off(RoomEvent.DataReceived, handler)
    }
  }, [room, onToolEvent, onAuthoritativeTurn, dispatch])

  useEffect(() => {
    const handler = (
      segments: Array<{
        id: string
        text: string
        isFinal?: boolean
        final?: boolean
        firstReceivedTime?: number
      }>,
      participant?: { isAgent?: boolean },
    ) => {
      for (const seg of segments) {
        const isFinal = seg.isFinal ?? seg.final ?? false
        if (isFinal) continue
        onTranscriptPreview({
          id: seg.id,
          text: seg.text,
          isFinal: false,
          speaker: participant?.isAgent ? 'agent' : 'user',
          timestamp: seg.firstReceivedTime ?? Date.now(),
        })
      }
    }
    room.on(RoomEvent.TranscriptionReceived, handler)
    return () => {
      room.off(RoomEvent.TranscriptionReceived, handler)
    }
  }, [room, onTranscriptPreview])

  const toggleMic = useCallback(() => {
    void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)
  }, [localParticipant, isMicrophoneEnabled])

  const handleEndCall = useCallback(() => dispatch({ type: 'START_ENDING' }), [dispatch])

  const isEnding = state.status === 'ending'
  const connected = state.status === 'connected'

  return (
    <main className="flex h-screen w-full flex-col overflow-hidden lg:flex-row">
      {isEnding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/90">
          <div className="rounded-base border-2 border-foreground bg-card px-8 py-6 font-bold shadow-brutal">
            Finalizing call…
          </div>
        </div>
      )}

      <section className="flex h-[45vh] shrink-0 flex-col border-b-2 border-foreground bg-secondary lg:h-full lg:w-[58%] lg:border-b-0 lg:border-r-2">
        <AvatarVideo
          templateName="Healthcare Front Desk"
          templateIcon="🏥"
          fallback={
            <div className="text-center">
              <div className="mb-3 text-5xl">🏥</div>
              <p className="text-sm font-bold">Healthcare Front Desk</p>
              <p className="mt-1 text-xs font-medium text-muted-foreground">
                {session.avatarProvider.toUpperCase()} · {session.ttsProvider}
              </p>
            </div>
          }
        />
      </section>

      <section className="flex min-h-0 flex-1 flex-col lg:w-[42%]">
        <div className="shrink-0 border-b-2 border-foreground bg-card px-4 py-3">
          <p className="font-mono text-xs font-bold uppercase tracking-widest">
            Live transcript
          </p>
        </div>

        <TranscriptFeed transcript={transcript} />
        <ToolActivityFeed events={toolEvents} toolLabels={toolLabels} />

        <div className="shrink-0 space-y-3 border-t-2 border-foreground bg-card p-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="font-mono font-normal">
              {connected ? 'Live' : state.status}
            </Badge>
            <span className="truncate font-mono opacity-60">
              session {session.sessionId.slice(0, 8)}…
            </span>
          </div>

          <ChatInput disabled={!connected || isEnding} />

          <div className="flex items-center justify-between gap-4">
            <Button
              type="button"
              variant="outline"
              onClick={toggleMic}
              disabled={!connected || isEnding}
              className="gap-2"
            >
              {isMicrophoneEnabled ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
              {isMicrophoneEnabled ? 'Mute' : 'Unmute'}
            </Button>

            <Button
              type="button"
              variant="destructive"
              onClick={handleEndCall}
              disabled={!connected || isEnding}
              className="gap-2"
            >
              <PhoneOff className="h-4 w-4" />
              {isEnding ? 'Ending…' : 'End call'}
            </Button>
          </div>
        </div>
      </section>
    </main>
  )
}

function CallContent() {
  const router = useRouter()
  const [session, setSession] = useState<StoredSession | null>(null)
  const [state, dispatch] = useReducer(callReducer, initialState)
  const [toolEvents, setToolEvents] = useState<ToolCallEvent[]>([])
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([])

  useEffect(() => {
    const stored = loadSession()
    if (!stored) {
      router.replace('/')
      return
    }
    setSession(stored)
  }, [router])

  useEffect(() => {
    if (state.status !== 'ended' || !session) return

    const sessionId = session.sessionId
    let cancelled = false

    ;(async () => {
      try {
        await endSession(sessionId)
      } catch {
        /* still navigate */
      }
      if (!cancelled) {
        clearSession()
        router.push(`/conversations/${sessionId}`)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [state.status, session, router])

  const handleToolEvent = useCallback(
    (e: ToolCallEvent) => setToolEvents((prev) => [...prev, e]),
    [],
  )
  const handleTranscriptPreview = useCallback((segment: TranscriptSegment) => {
    setTranscript((prev) => mergeSttPreview(prev, segment))
  }, [])
  const handleAuthoritativeTurn = useCallback(
    (role: 'user' | 'assistant', text: string, timestamp: number) => {
      setTranscript((prev) => mergeAuthoritativeTurn(prev, role, text, timestamp))
    },
    [],
  )

  if (!session) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        Loading session…
      </div>
    )
  }

  if (state.status === 'failed' || state.error) {
    return (
      <div className="flex h-screen items-center justify-center text-destructive">
        {state.error ?? 'Failed to connect'}
      </div>
    )
  }

  const shouldConnect = state.status !== 'ending'

  return (
    <LiveKitRoom
      token={session.token}
      serverUrl={session.url}
      connect={shouldConnect}
      audio={true}
      video={false}
      options={{ adaptiveStream: false, dynacast: false }}
      onConnected={() => dispatch({ type: 'ROOM_CONNECTED' })}
      onDisconnected={() => dispatch({ type: 'ROOM_DISCONNECTED' })}
    >
      <RoomAudioRenderer />
      <CallUI
        session={session}
        state={state}
        dispatch={dispatch}
        toolEvents={toolEvents}
        transcript={transcript}
        onToolEvent={handleToolEvent}
        onTranscriptPreview={handleTranscriptPreview}
        onAuthoritativeTurn={handleAuthoritativeTurn}
      />
    </LiveKitRoom>
  )
}

export default function CallPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center text-muted-foreground">
          Loading…
        </div>
      }
    >
      <CallContent />
    </Suspense>
  )
}
