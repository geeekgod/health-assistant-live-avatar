'use client'

import { type ReactNode, useEffect, useRef, useState } from 'react'
import { useRoomContext } from '@livekit/components-react'
import {
  RemoteTrackPublication,
  RoomEvent,
  Track,
  VideoQuality,
  type Participant,
} from 'livekit-client'
import { Badge } from '@/components/ui/badge'
import { isAvatarParticipant } from '@/lib/livekitParticipants'

interface AvatarVideoProps {
  fallback: ReactNode
  templateName?: string
  templateIcon?: string
}

function WaveformFallback({ isSpeaking }: { isSpeaking: boolean }) {
  return (
    <div className="flex h-24 items-end justify-center gap-1.5">
      {Array.from({ length: 12 }).map((_, i) => (
        <div
          key={i}
          className="w-2 rounded-sm border border-foreground bg-primary"
          style={{
            height: isSpeaking ? `${16 + (i % 4) * 10}px` : '12px',
            animation: isSpeaking
              ? `pulse-bar 0.6s ease-in-out ${i * 0.05}s infinite alternate`
              : undefined,
          }}
        />
      ))}
    </div>
  )
}

export default function AvatarVideo({ fallback, templateName, templateIcon }: AvatarVideoProps) {
  const room = useRoomContext()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [hasVideo, setHasVideo] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [status, setStatus] = useState('Connecting avatar…')

  useEffect(() => {
    if (!room) return

    const attachVideo = (track: Track) => {
      if (track.kind !== Track.Kind.Video || !videoRef.current) return
      track.attach(videoRef.current)
      setHasVideo(true)
      setStatus('')
    }

    const subscribeParticipant = (participant: Participant) => {
      if (!isAvatarParticipant(participant)) return
      participant.trackPublications.forEach((publication) => {
        if (publication instanceof RemoteTrackPublication) {
          publication.setSubscribed(true)
          publication.setVideoQuality(VideoQuality.HIGH)
        }
        if (publication.track?.kind === Track.Kind.Video) {
          attachVideo(publication.track)
        }
      })
    }

    room.remoteParticipants.forEach(subscribeParticipant)

    const onTrackSubscribed = (
      track: Track,
      publication: RemoteTrackPublication,
      participant: Participant,
    ) => {
      if (!isAvatarParticipant(participant)) return
      if (publication instanceof RemoteTrackPublication) {
        publication.setVideoQuality(VideoQuality.HIGH)
      }
      if (track.kind === Track.Kind.Video) attachVideo(track)
    }

    const onActiveSpeakers = (speakers: Participant[]) => {
      const localId = room.localParticipant.identity
      setIsSpeaking(speakers.some((s) => s.identity !== localId))
    }

    const onParticipantConnected = (participant: Participant) => {
      if (isAvatarParticipant(participant)) setStatus('Avatar joining…')
      subscribeParticipant(participant)
    }

    const onTrackPublished = (_pub: unknown, participant: Participant) => {
      if (isAvatarParticipant(participant)) setStatus('Avatar joining…')
      subscribeParticipant(participant)
    }

    room.on(RoomEvent.TrackSubscribed, onTrackSubscribed)
    room.on(RoomEvent.ParticipantConnected, onParticipantConnected)
    room.on(RoomEvent.TrackPublished, onTrackPublished)
    room.on(RoomEvent.ActiveSpeakersChanged, onActiveSpeakers)

    return () => {
      room.off(RoomEvent.TrackSubscribed, onTrackSubscribed)
      room.off(RoomEvent.ParticipantConnected, onParticipantConnected)
      room.off(RoomEvent.TrackPublished, onTrackPublished)
      room.off(RoomEvent.ActiveSpeakersChanged, onActiveSpeakers)
    }
  }, [room])

  return (
    <div className="relative flex h-full w-full items-center justify-center p-6 md:p-10">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className={`relative z-10 max-h-full max-w-full rounded-base border-2 border-foreground bg-card object-contain shadow-brutal transition-opacity duration-500 ${
          hasVideo ? 'opacity-100' : 'pointer-events-none absolute opacity-0'
        }`}
      />

      {!hasVideo ? (
        <div className="flex flex-col items-center justify-center gap-6">
          <div
            className={`rounded-base border-2 border-foreground bg-card p-10 shadow-brutal transition-all duration-300 ${
              isSpeaking ? 'translate-x-[-2px] translate-y-[-2px] bg-accent/30' : ''
            }`}
          >
            {fallback ?? <WaveformFallback isSpeaking={isSpeaking} />}
          </div>
          <p className="max-w-sm text-center text-sm font-bold">{status || 'Voice assistant active'}</p>
        </div>
      ) : (
        <div
          className={`pointer-events-none absolute inset-6 rounded-base border-2 border-foreground transition-all duration-500 md:inset-10 ${
            isSpeaking ? 'opacity-100 shadow-brutal' : 'opacity-40'
          }`}
        />
      )}

      {templateName && (
        <Badge variant="secondary" className="absolute bottom-4 left-4 z-20 gap-1.5">
          {templateIcon && <span>{templateIcon}</span>}
          {templateName}
        </Badge>
      )}
    </div>
  )
}
