export interface PilotSignal {
  symbol: string
  session_number: number
  direction: 'up' | 'down'
}

export async function loadSignals(signal: AbortSignal): Promise<PilotSignal[]> {
  const response = await fetch('/api/pilot/signals', { signal })
  if (!response.ok) throw new Error('Could not load pilot signals.')
  return response.json()
}

export interface VerifiedCandle {
  session: string
  close: string
  sma20: string | null
  sma50: string | null
  cross: 'up' | 'down' | null
}

export interface VerifiedScan {
  symbol: string
  session: string
  verified_sessions: number
  candles: VerifiedCandle[]
}

export async function loadVerifiedScan(signal: AbortSignal): Promise<VerifiedScan | null> {
  const response = await fetch('/api/pilot/verified-scan', { signal })
  if (!response.ok) throw new Error('Could not load the verified scan.')
  return response.json()
}
