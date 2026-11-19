import type { PortfolioBacktest } from './api/paper'

const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })
const money = (value: string) => rupees.format(Number(value))
const percent = new Intl.NumberFormat('en-IN', { style: 'percent', maximumFractionDigits: 2 })
const skipReason: Record<string, string> = {
  insufficient_cash: 'Shared cash could not cover one share and the fee',
  zero_shares: 'Company limit could not cover one share and the fee',
  already_long: 'A position was already open',
  flat_position: 'No shares were held',
  nonpositive_fill_price: 'The adjusted price was zero or below',
  insufficient_cash_for_exit_fee: 'Cash and proceeds did not cover the exit fee',
}

export default function PortfolioLedger({ report }: { report: PortfolioBacktest }) {
  const { summary, terms, fills, stocks, excluded, tested, watchlist, daily, signals, benchmark } = report
  const unfilled = signals.filter((signal) => signal.status !== 'filled')
  const strategyReturn = percent.format(summary.return === undefined
    ? Number(summary.net_pnl) / Number(terms.opening_cash)
    : Number(summary.return))

  return (
    <section aria-labelledby="portfolio-heading">
      <h2 id="portfolio-heading">Portfolio backtest</h2>
      <p>{tested.length} of {watchlist.length} companies tested · {report.first_session} to {report.last_session}</p>
      <p>{report.source} · 20/50 SMA crossover · Next-session open fills</p>
      <dl className="ledger-summary">
        <div><dt>Starting cash</dt><dd>{money(terms.opening_cash)}</dd></div>
        <div><dt>Available cash</dt><dd>{money(summary.cash)}</dd></div>
        <div><dt>Portfolio value</dt><dd>{money(summary.equity)}</dd></div>
        <div><dt>Net P&amp;L after modeled costs</dt><dd>{money(summary.net_pnl)}</dd></div>
        <div><dt>Realized P&amp;L</dt><dd>{money(summary.realized_pnl)}</dd></div>
        <div><dt>Open P&amp;L</dt><dd>{money(summary.unrealized_pnl)}</dd></div>
        {!benchmark && <div><dt>Return</dt><dd>{strategyReturn}</dd></div>}
        <div><dt>Open positions</dt><dd>{summary.open_positions}</dd></div>
      </dl>
      <p>{money(terms.allocation)} entry limit per company · {money(terms.fee)} per fill · {money(terms.slippage_per_share)} slippage per share</p>
      {summary.total_fees !== undefined && summary.total_slippage !== undefined &&
        <p>{money(summary.total_fees)} in fees and {money(summary.total_slippage)} in slippage included in net P&amp;L.</p>}
      {benchmark && summary.max_drawdown !== undefined && (
        <>
          <h3>Performance comparison</h3>
          <table>
            <thead><tr><th scope="col">Series</th><th scope="col">Return</th><th scope="col">Max drawdown</th></tr></thead>
            <tbody>
              <tr><th scope="row">Strategy after modeled costs</th><td>{strategyReturn}</td>
                <td>{percent.format(Number(summary.max_drawdown))}</td></tr>
              <tr><th scope="row">{benchmark.name}</th><td>{percent.format(Number(benchmark.return))}</td>
                <td>{percent.format(Number(benchmark.max_drawdown))}</td></tr>
            </tbody>
          </table>
          <p>Drawdown is the largest peak-to-trough decline at daily closes. The index uses closing prices and excludes dividends.</p>
        </>
      )}
      <h3>Companies</h3>
      <div className="ledger-table" tabIndex={0} role="region" aria-label="Company positions and P&L">
        <table>
          <thead><tr>{['Company', 'Position', 'Shares', 'Last close', 'Market value', 'Net P&L'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
          <tbody>{stocks.map((stock) => (
            <tr key={stock.symbol}><th scope="row">{stock.symbol}</th><td>{stock.shares ? 'Hold shares' : 'Flat'}</td>
              <td>{stock.shares}</td><td>{money(stock.close)}</td><td>{money(stock.market_value)}</td><td>{money(stock.net_pnl)}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <details open>
        <summary>Trade log ({fills.length})</summary>
        {fills.length === 0 ? <p>No fills during this window.</p> : (
          <div className="ledger-table" tabIndex={0} role="region" aria-label="Portfolio trades">
            <table>
              <thead><tr>{['Company', 'Action', 'Signal', 'Fill', 'Shares', 'Fill price', 'Fee', 'Cash after'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
              <tbody>{fills.map((fill) => (
                <tr key={`${fill.symbol}-${fill.fill_session}`}><th scope="row">{fill.symbol}</th>
                  <td>{fill.side === 'buy' ? 'Buy' : 'Sell'}</td><td>{fill.signal_session}</td><td>{fill.fill_session}</td>
                  <td>{fill.quantity}</td><td>{money(fill.price)}</td><td>{money(fill.fee)}</td><td>{money(fill.cash_after)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </details>
      <details>
        <summary>Daily portfolio value</summary>
        <div className="ledger-table" tabIndex={0} role="region" aria-label="Daily portfolio value">
          <table>
            <thead><tr>{['Session', 'Cash', 'Equity', 'Net P&L', 'Open positions'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
            <tbody>{daily.map((day) => (
              <tr key={day.session}><th scope="row">{day.session}</th><td>{money(day.cash)}</td><td>{money(day.equity)}</td>
                <td>{money(day.net_pnl)}</td><td>{day.open_positions}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </details>
      {unfilled.length > 0 && <details>
        <summary>Pending and skipped signals ({unfilled.length})</summary>
        <ul>{unfilled.map((signal) => <li key={`${signal.symbol}-${signal.session}`}>{signal.session} · {signal.symbol} · {signal.side} · {signal.status === 'pending' ? 'Next open falls outside the backtest' : skipReason[signal.reason ?? ''] ?? 'Skipped'}</li>)}</ul>
      </details>}
      {excluded.length > 0 && <details open>
        <summary>Companies excluded from calculation ({excluded.length})</summary>
        <ul>{excluded.map(({ symbol, reason }) => <li key={symbol}>{reason.includes(symbol) ? reason : `${symbol} · ${reason}`}</li>)}</ul>
      </details>}
    </section>
  )
}
