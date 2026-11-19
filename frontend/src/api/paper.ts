interface PaperMark {
  session: string
  close: string
  shares: number
  cash: string
  equity: string
  net_pnl: string
}

interface PaperFill {
  signal_session: string
  fill_session: string
  side: 'buy' | 'sell'
  quantity: number
  raw_open: string
  price: string
  fee: string
  slippage_per_share: string
  cash_change: string
  cash_after: string
  realized_pnl: string | null
}

interface PaperSignal {
  session: string
  side: 'buy' | 'sell'
  status: 'filled' | 'pending' | 'skipped'
  reason?: string
}

export interface PaperLedger {
  id: number
  mode: 'fixture' | 'verified_replay'
  symbol: string
  terms: { opening_cash: string; allocation: string; fee: string; slippage_per_share: string }
  summary: PaperMark & { realized_pnl: string }
  fills: PaperFill[]
  signals: PaperSignal[]
  daily: PaperMark[]
}

export async function loadPaperLedgers(signal: AbortSignal): Promise<PaperLedger[]> {
  const response = await fetch('/api/pilot/paper-ledgers', { signal })
  if (!response.ok) throw new Error('Could not load the paper trade ledgers.')
  return response.json()
}
