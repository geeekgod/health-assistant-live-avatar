'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function SummaryRedirectPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter()

  useEffect(() => {
    void params.then((p) => router.replace(`/conversations/${p.id}`))
  }, [params, router])

  return (
    <div className="flex min-h-screen items-center justify-center text-muted-foreground">
      Redirecting…
    </div>
  )
}
