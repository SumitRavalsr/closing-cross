import { useEffect, useState } from 'react'
import PaperLedgerPanel from './PaperLedger'
import { loadPaperLedgers, type PaperLedger } from './api/paper'
import { loadSignals, loadVerifiedScan, type PilotSignal, type VerifiedScan } from './api/signals'

export default function App() {
  const [signals, setSignals] = useState<PilotSignal[] | null>(null)
  const [error, setError] = useState(false)
  const [scan, setScan] = useState<VerifiedScan | null>(null)
  const [scanError, setScanError] = useState(false)
  const [ledgers, setLedgers] = useState<PaperLedger[] | null>(null)
  const [ledgerError, setLedgerError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    loadSignals(controller.signal).then(setSignals).catch(() => {
      if (!controller.signal.aborted) setError(true)
    })
    loadVerifiedScan(controller.signal).then(setScan).catch(() => {
      if (!controller.signal.aborted) setScanError(true)
    })
    loadPaperLedgers(controller.signal).then(setLedgers).catch(() => {
      if (!controller.signal.aborted) setLedgerError(true)
    })
    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>Closing Cross Pilot</h1>
      {scanError && <p role="alert">Could not load the verified NSE scan.</p>}
      {scan && (
        <section aria-labelledby="verified-heading">
          <h2 id="verified-heading">{scan.symbol} · Verified NSE replay</h2>
          <p>{scan.verified_sessions} sessions matched NSE bhavcopy through {scan.session}.</p>
          <table>
            <thead>
              <tr><th scope="col">Session</th><th scope="col">Close</th><th scope="col">SMA 20</th><th scope="col">SMA 50</th><th scope="col">Cross</th></tr>
            </thead>
            <tbody>
              {scan.candles.filter((candle) => candle.cross || candle.session === scan.session).map((candle) => (
                <tr key={candle.session}>
                  <td>{candle.session}</td><td>{candle.close}</td><td>{candle.sma20}</td><td>{candle.sma50}</td>
                  <td>{candle.cross === 'up' ? 'Up' : candle.cross === 'down' ? 'Down' : 'None'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {ledgerError && <p role="alert">Could not load the paper trade ledgers.</p>}
      {ledgers?.length === 0 && <p>No paper trade ledger has been saved yet.</p>}
      {ledgers?.map((ledger) => <PaperLedgerPanel key={ledger.id} ledger={ledger} />)}
      <section aria-labelledby="signals-heading">
        <h2 id="signals-heading">Fixture signals</h2>
        {error && <p role="alert">Could not load pilot signals.</p>}
        {!signals && !error && <p role="status">Loading signals…</p>}
        {signals?.length === 0 && <p>No fixture signals have been loaded.</p>}
        {!!signals?.length && (
          <table>
            <thead>
              <tr><th scope="col">Symbol</th><th scope="col">Session</th><th scope="col">Cross</th></tr>
            </thead>
            <tbody>
              {signals.map(({ symbol, session_number, direction }) => (
                <tr key={`${symbol}-${session_number}`}>
                  <td>{symbol}</td><td>{session_number}</td><td>{direction === 'up' ? 'Up' : 'Down'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  )
}
