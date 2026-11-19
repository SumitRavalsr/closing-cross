interface PaperMark {
  session: string
  close: string
  shares: number
  cash: string
  equity: string
  net_pnl: string
  action?: 'buy' | 'sell' | 'hold_cash' | 'hold_shares'
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
  mode: 'fixture' | 'verified_replay' | 'backtest'
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

export interface Backtest extends PaperLedger {
  mode: 'backtest'
  funded_on: string
  first_session: string
  last_session: string
  source: string
}

export interface PortfolioBacktest {
  id: number
  mode: 'portfolio_backtest'
  funded_on: string
  first_session: string
  last_session: string
  source: string
  watchlist: string[]
  tested: string[]
  excluded: { symbol: string; reason: string }[]
  terms: PaperLedger['terms']
  summary: { cash: string; market_value: string; equity: string; net_pnl: string; realized_pnl: string; unrealized_pnl: string; open_positions: number }
    & Partial<{ return: string; max_drawdown: string; total_fees: string; total_slippage: string }>
  benchmark?: { name: string; source: string; return: string; max_drawdown: string }
  stocks: { symbol: string; shares: number; close: string; market_value: string; cost_basis: string; net_pnl: string }[]
  fills: (PaperFill & { symbol: string })[]
  signals: (PaperSignal & { symbol: string })[]
  daily: { session: string; cash: string; equity: string; net_pnl: string; open_positions: number; fills: string[] }[]
}

export async function loadBacktest(signal: AbortSignal): Promise<Backtest | PortfolioBacktest | null> {
  const response = await fetch('/api/pilot/backtest', { signal })
  if (!response.ok) throw new Error('Could not load the historical backtest.')
  return response.json()
}
