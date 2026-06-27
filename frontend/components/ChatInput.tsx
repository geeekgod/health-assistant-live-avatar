'use client'

import { useCallback, useState } from 'react'
import { Send } from 'lucide-react'
import { useLocalParticipant } from '@livekit/components-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface ChatInputProps {
  disabled?: boolean
}

export default function ChatInput({ disabled }: ChatInputProps) {
  const { localParticipant } = useLocalParticipant()
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)

  const send = useCallback(async () => {
    const message = text.trim()
    if (!message || sending || disabled) return
    setSending(true)
    try {
      await localParticipant.sendText(message)
      setText('')
    } catch {
      /* ignore send failures */
    } finally {
      setSending(false)
    }
  }, [text, sending, disabled, localParticipant])

  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        void send()
      }}
    >
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type a message…"
        disabled={disabled || sending}
        className="font-mono text-sm"
      />
      <Button type="submit" size="icon" disabled={disabled || sending || !text.trim()}>
        <Send className="h-4 w-4" />
      </Button>
    </form>
  )
}
