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
