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
  fallback?: ReactNode
  templateName?: string
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

export default function AvatarVideo({ fallback, templateName }: AvatarVideoProps) {
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
      setIsSpeaking(speakers.some((s) => isAvatarParticipant(s)))
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
    <div className="relative h-full min-h-0 w-full">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className={`absolute inset-0 z-10 m-auto h-full w-full rounded-base border-2 object-contain transition-all duration-300 ${
          hasVideo ? 'opacity-100' : 'pointer-events-none opacity-0'
        } ${
          hasVideo && isSpeaking
            ? 'border-foreground bg-transparent shadow-brutal'
            : hasVideo
              ? 'border-foreground/40 bg-transparent shadow-none'
              : 'border-foreground bg-secondary'
        }`}
      />

      {!hasVideo ? (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-6 p-6 md:p-10">
          <div
            className={`rounded-base border-2 border-foreground bg-secondary p-10 shadow-brutal transition-colors duration-300 ${
              isSpeaking ? 'bg-accent/30' : ''
            }`}
          >
            {fallback ?? <WaveformFallback isSpeaking={isSpeaking} />}
          </div>
          <p className="max-w-sm text-center text-sm font-bold">{status || 'Voice assistant active'}</p>
        </div>
      ) : null}

      {templateName && (
        <Badge variant="secondary" className="absolute bottom-4 left-4 z-20">
          {templateName}
        </Badge>
      )}
    </div>
  )
}
