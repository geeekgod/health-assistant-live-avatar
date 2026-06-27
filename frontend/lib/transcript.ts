export interface TranscriptSegment {
  id: string
  text: string
  isFinal: boolean
  speaker: 'agent' | 'user'
  timestamp: number
  source?: 'stt' | 'agent'
}

export function mergeSttPreview(
  prev: TranscriptSegment[],
  segment: Omit<TranscriptSegment, 'source'>,
): TranscriptSegment[] {
  if (segment.isFinal) return prev

  const incoming: TranscriptSegment = { ...segment, source: 'stt' }
  const byId = prev.findIndex(
    (row) => row.id === incoming.id && row.speaker === incoming.speaker,
  )
  if (byId >= 0) {
    const updated = [...prev]
    updated[byId] = { ...updated[byId], text: incoming.text, isFinal: false }
    return updated
  }

  const last = prev[prev.length - 1]
  if (last && last.speaker === incoming.speaker && last.source === 'stt' && !last.isFinal) {
    const updated = [...prev]
    updated[prev.length - 1] = {
      ...last,
      text: incoming.text,
      id: incoming.id,
      isFinal: false,
    }
    return updated
  }

  return [...prev, incoming]
}

export function mergeAuthoritativeTurn(
  prev: TranscriptSegment[],
  role: 'user' | 'assistant',
  text: string,
  timestamp: number,
): TranscriptSegment[] {
  const speaker = role === 'assistant' ? 'agent' : 'user'
  const trimmed = text.trim()
  if (!trimmed) return prev

  const last = prev[prev.length - 1]
  if (last && last.speaker === speaker && last.text === trimmed && last.source === 'agent') {
    return prev
  }

  const turn: TranscriptSegment = {
    id: `turn-${timestamp}`,
    text: trimmed,
    isFinal: true,
    speaker,
    timestamp,
    source: 'agent',
  }

  if (last && last.speaker === speaker && last.source === 'stt') {
    return [...prev.slice(0, -1), turn]
  }

  return [...prev, turn]
}
