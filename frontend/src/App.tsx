import { useEffect, useState } from 'react'
import PaperLedgerPanel from './PaperLedger'
import PortfolioLedger from './PortfolioLedger'
import { loadBacktest, type Backtest, type PortfolioBacktest } from './api/paper'

export default function App() {
  const [report, setReport] = useState<Backtest | PortfolioBacktest | null | undefined>()
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    loadBacktest(controller.signal).then(setReport).catch(() => {
      if (!controller.signal.aborted) setError(true)
    })
    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>Closing Cross</h1>
      {error && <p role="alert">Could not load the historical backtest.</p>}
      {report === undefined && !error && <p role="status">Loading backtest…</p>}
      {report === null && <p>No historical backtest has been run for this environment.</p>}
      {report?.mode === 'portfolio_backtest' && <PortfolioLedger report={report} />}
      {report?.mode === 'backtest' && <PaperLedgerPanel ledger={report} backtest={report} />}
    </main>
  )
}
