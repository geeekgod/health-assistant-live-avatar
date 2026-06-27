'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Headphones, Pause, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

interface CallRecordingPlayerProps {
  src: string
  className?: string
}

export default function CallRecordingPlayer({ src, className }: CallRecordingPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [duration, setDuration] = useState(0)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setPlaying(false)
    setCurrent(0)
    setDuration(0)
    setReady(false)
  }, [src])

  const togglePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      void audio.play()
    } else {
      audio.pause()
    }
  }, [])

  const seek = useCallback(
    (clientX: number) => {
      const audio = audioRef.current
      const track = trackRef.current
      if (!audio || !track || !duration) return
      const rect = track.getBoundingClientRect()
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
      audio.currentTime = ratio * duration
      setCurrent(audio.currentTime)
    },
    [duration],
  )

  const progress = duration > 0 ? (current / duration) * 100 : 0

  return (
    <div
      className={cn(
        'rounded-base border-2 border-foreground bg-secondary p-4 shadow-brutal-sm',
        className,
      )}
    >
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        className="hidden"
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration
          setDuration(Number.isFinite(d) ? d : 0)
          setReady(true)
        }}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />

      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="default"
          size="icon"
          className="shrink-0"
          onClick={togglePlay}
          disabled={!ready}
          aria-label={playing ? 'Pause recording' : 'Play recording'}
        >
          {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>

        <div className="min-w-0 flex-1 space-y-2">
          <div
            ref={trackRef}
            role="slider"
            tabIndex={0}
            aria-valuemin={0}
            aria-valuemax={duration}
            aria-valuenow={current}
            aria-label="Recording progress"
            className="cursor-pointer rounded-base border-2 border-foreground bg-card p-1 shadow-brutal-sm"
            onClick={(e) => seek(e.clientX)}
            onKeyDown={(e) => {
              const audio = audioRef.current
              if (!audio || !duration) return
              const step = e.shiftKey ? 10 : 5
              if (e.key === 'ArrowRight') {
                e.preventDefault()
                audio.currentTime = Math.min(duration, audio.currentTime + step)
              }
              if (e.key === 'ArrowLeft') {
                e.preventDefault()
                audio.currentTime = Math.max(0, audio.currentTime - step)
              }
            }}
          >
            <div className="relative h-3 overflow-hidden rounded-sm bg-muted">
              <div
                className="absolute inset-y-0 left-0 bg-primary transition-[width] duration-100"
                style={{ width: `${progress}%` }}
              />
              <div
                className="absolute top-1/2 h-4 w-1 -translate-y-1/2 border-2 border-foreground bg-accent"
                style={{ left: `calc(${progress}% - 2px)` }}
              />
            </div>
          </div>

          <div className="flex items-center justify-between font-mono text-xs font-bold">
            <span>{formatDuration(current)}</span>
            <span className="flex items-center gap-1 text-muted-foreground">
              <Headphones className="h-3 w-3" />
              {formatDuration(duration)}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
