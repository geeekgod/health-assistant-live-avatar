import type { Participant } from 'livekit-client'

const AVATAR_IDENTITY = 'bey-avatar-agent'

export function isAvatarParticipant(participant: Participant): boolean {
  const identity = participant.identity.toLowerCase()
  const name = (participant.name || '').toLowerCase()
  return (
    identity === AVATAR_IDENTITY ||
    identity.includes('bey') ||
    identity.includes('tavus') ||
    participant.attributes['lk.publish_on_behalf'] != null ||
    name.includes('avatar')
  )
}
