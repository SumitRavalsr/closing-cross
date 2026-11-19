import type { PaperLedger } from './api/paper'

const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })
const amount = (value: string) => rupees.format(Number(value))
const reasons: Record<string, string> = {
  already_long: 'A position was already open',
  flat_position: 'There was no open position to sell',
  insufficient_cash: 'Insufficient cash for one share and the fee',
  zero_shares: 'The allocation could not cover one share and the fee',
  nonpositive_fill_price: 'Slippage reduced the fill price to zero or below',
  insufficient_cash_for_exit_fee: 'The exit fee exceeded available cash and sale proceeds',
}

export default function PaperLedgerPanel({ ledger }: { ledger: PaperLedger }) {
  const { daily, fills, id, mode, signals, summary, symbol, terms } = ledger
  const heading = `paper-ledger-${id}`
  const sessionLabel = (session: string) => mode === 'fixture' ? `Session ${session}` : session

  return (
    <section aria-labelledby={heading}>
      <h2 id={heading}>{mode === 'fixture' ? 'Fixture' : symbol} · Paper trade ledger</h2>
      <p>Hypothetical historical replay through {sessionLabel(summary.session)}.</p>
      <dl className="ledger-summary">
        <div><dt>Opening cash</dt><dd>{amount(terms.opening_cash)}</dd></div>
        <div><dt>Cash</dt><dd>{amount(summary.cash)}</dd></div>
        <div><dt>Equity</dt><dd>{amount(summary.equity)}</dd></div>
        <div><dt>Net P&amp;L</dt><dd>{amount(summary.net_pnl)}</dd></div>
        <div><dt>Realized P&amp;L</dt><dd>{amount(summary.realized_pnl)}</dd></div>
        <div><dt>Shares held</dt><dd>{summary.shares}</dd></div>
      </dl>
      <p>Allocation {amount(terms.allocation)} · Fee {amount(terms.fee)} per fill · Slippage {amount(terms.slippage_per_share)} per share</p>
      {fills.length ? (
        <div className="ledger-table" tabIndex={0} role="region" aria-label="Hypothetical fills">
          <table>
            <thead>
              <tr>{['Side', 'Signal', 'Fill', 'Shares', 'Raw open', 'Fill price', 'Fee', 'Slippage/share', 'Cash change', 'Cash after', 'Trade P&L'].map((label) => (
                <th key={label} scope="col">{label}</th>
              ))}</tr>
            </thead>
            <tbody>
              {fills.map((fill) => (
                <tr key={fill.signal_session}>
                  <td>{fill.side === 'buy' ? 'Buy' : 'Sell'}</td>
                  <td>{sessionLabel(fill.signal_session)}</td><td>{sessionLabel(fill.fill_session)}</td>
                  <td>{fill.quantity}</td><td>{amount(fill.raw_open)}</td><td>{amount(fill.price)}</td>
                  <td>{amount(fill.fee)}</td><td>{amount(fill.slippage_per_share)}</td>
                  <td>{amount(fill.cash_change)}</td><td>{amount(fill.cash_after)}</td>
                  <td>{fill.realized_pnl === null ? '—' : amount(fill.realized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p>No hypothetical fills in this replay.</p>}
      {signals.filter(({ status }) => status !== 'filled').map((signal) => (
        <p key={signal.session}>
          {sessionLabel(signal.session)} · {signal.side === 'buy' ? 'Buy' : 'Sell'} ·{' '}
          {signal.status === 'pending' ? 'Waiting for the next verified session' : reasons[signal.reason ?? ''] ?? 'Skipped'}
        </p>
      ))}
      <details>
        <summary>Daily cash and equity</summary>
        <div className="ledger-table" tabIndex={0} role="region" aria-label="Daily cash and equity">
          <table>
            <thead><tr><th scope="col">Session</th><th scope="col">Close</th><th scope="col">Shares</th><th scope="col">Cash</th><th scope="col">Equity</th></tr></thead>
            <tbody>
              {daily.map((day) => (
                <tr key={day.session}>
                  <td>{sessionLabel(day.session)}</td><td>{amount(day.close)}</td><td>{day.shares}</td>
                  <td>{amount(day.cash)}</td><td>{amount(day.equity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}
