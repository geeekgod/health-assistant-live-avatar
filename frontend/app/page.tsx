'use client'

import Link from 'next/link'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  createSession,
  type AvatarProvider,
  type TtsProvider,
} from '@/lib/api'
import { saveSession } from '@/lib/session'

export default function LobbyPage() {
  const router = useRouter()
  const [avatar, setAvatar] = useState<AvatarProvider>('bey')
  const [tts, setTts] = useState<TtsProvider>('cartesia')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleStart = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await createSession(avatar, tts)
      saveSession({
        sessionId: data.sessionId,
        token: data.token,
        url: data.url,
        agent_config: data.agent_config,
        avatarProvider: avatar,
        ttsProvider: tts,
      })
      router.push('/call')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start session')
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-lg border-border bg-card/80">
        <CardHeader className="text-center">
          <div className="mb-2 text-4xl">🏥</div>
          <CardTitle className="text-2xl">Healthcare Front Desk</CardTitle>
          <CardDescription>
            Voice assistant with live avatar — pick providers and start a demo call
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-3">
            <Label className="text-sm font-medium">Avatar provider</Label>
            <RadioGroup
              value={avatar}
              onValueChange={(v) => setAvatar(v as AvatarProvider)}
              className="grid grid-cols-2 gap-3"
            >
              <Label
                htmlFor="avatar-bey"
                className={`flex cursor-pointer items-center gap-2 rounded-lg border p-3 transition-colors ${
                  avatar === 'bey' ? 'border-primary bg-primary/5' : 'border-border'
                }`}
              >
                <RadioGroupItem value="bey" id="avatar-bey" />
                BEY
              </Label>
              <Label
                htmlFor="avatar-tavus"
                className={`flex cursor-pointer items-center gap-2 rounded-lg border p-3 transition-colors ${
                  avatar === 'tavus' ? 'border-primary bg-primary/5' : 'border-border'
                }`}
              >
                <RadioGroupItem value="tavus" id="avatar-tavus" />
                Tavus
              </Label>
            </RadioGroup>
          </div>

          <div className="space-y-3">
            <Label className="text-sm font-medium">TTS provider</Label>
            <RadioGroup
              value={tts}
              onValueChange={(v) => setTts(v as TtsProvider)}
              className="grid grid-cols-2 gap-3"
            >
              <Label
                htmlFor="tts-cartesia"
                className={`flex cursor-pointer items-center gap-2 rounded-lg border p-3 transition-colors ${
                  tts === 'cartesia' ? 'border-primary bg-primary/5' : 'border-border'
                }`}
              >
                <RadioGroupItem value="cartesia" id="tts-cartesia" />
                Cartesia
              </Label>
              <Label
                htmlFor="tts-gemini"
                className={`flex cursor-pointer items-center gap-2 rounded-lg border p-3 transition-colors ${
                  tts === 'gemini' ? 'border-primary bg-primary/5' : 'border-border'
                }`}
              >
                <RadioGroupItem value="gemini" id="tts-gemini" />
                Gemini
              </Label>
            </RadioGroup>
          </div>

          <Button className="w-full" size="lg" onClick={() => void handleStart()} disabled={loading}>
            {loading ? 'Starting session…' : 'Start call'}
          </Button>

          <p className="text-center text-sm text-muted-foreground">
            <Link href="/conversations" className="text-primary hover:underline">
              View past conversations
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  )
}
