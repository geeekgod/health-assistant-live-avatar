import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Health Assistant',
  description: 'Healthcare front desk voice assistant with live avatar',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  )
}
