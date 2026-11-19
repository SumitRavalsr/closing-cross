import { useEffect, useState } from 'react'

interface ForwardStatus {
  portfolio: {
    symbol: string
    last_session: string
    next_due_at: string
    cash: string
    shares: number
    pending: { side: string; target_session: string | null } | null
  } | null
  last_attempt: { started_at: string; status: string; detail: string | null } | null
  overdue: boolean
  recent_sessions: {
    session: string
    signal: ForwardSignal | null
    settled_signal: ForwardSignal | null
    fill: { side: string; quantity: number; price: string } | null
    mark: { equity: string; net_pnl: string }
  }[]
}

interface ForwardSignal {
  session: string
  side: string
  status: string
  late: boolean
  reason?: string
}

const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' })
const amount = (value: string) => rupees.format(Number(value))
const ist = (value: string) => `${new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST`

export default function ForwardPilot() {
  const [data, setData] = useState<ForwardStatus | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const response = await fetch('/api/pilot/forward', { signal: controller.signal })
        if (!response.ok) throw new Error('Forward status unavailable')
        setData(await response.json())
        setError(false)
      } catch {
        if (!controller.signal.aborted) setError(true)
      }
    }
    void load()
    const interval = window.setInterval(load, 60_000)
    return () => {
      controller.abort()
      window.clearInterval(interval)
    }
  }, [])

  const portfolio = data?.portfolio
  const attempt = data?.last_attempt
  const sessions = data?.recent_sessions ?? []
  const settled = new Map(sessions.flatMap(({ settled_signal }) => settled_signal ? [[settled_signal.session, settled_signal]] : []))
  return (
    <section aria-labelledby="forward-heading">
      <h2 id="forward-heading">{portfolio && `${portfolio.symbol} · `}Forward paper pilot</h2>
      {error && <p role="alert">Could not load the forward pilot status.</p>}
      {data?.overdue && <p role="alert">A scheduled session is overdue. Check the worker status.</p>}
      {attempt && <p>Last attempt {ist(attempt.started_at)} · {attempt.status}{attempt.detail && ` · ${attempt.detail}`}</p>}
      {data && !portfolio && <p>The forward portfolio has not been initialized.</p>}
      {portfolio && (
        <>
          <p>{sessions.length ? 'Last finalized session' : 'Verified seed session'} {portfolio.last_session} · Next check {ist(portfolio.next_due_at)}</p>
          <p>Cash {amount(portfolio.cash)} · {portfolio.shares} shares held</p>
          {portfolio.pending && <p>Pending {portfolio.pending.side} · {portfolio.pending.target_session ?? 'Waiting for the next calendar opening'}</p>}
          {sessions.length > 0 && (
            <div className="ledger-table" role="region" aria-label="Recent forward sessions" tabIndex={0}>
              <table>
                <thead><tr>{['Session', 'Signal', 'Fill', 'Equity', 'Net P&L'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
                <tbody>{sessions.map(({ session, signal, fill, mark }) => {
                  const outcome = settled.get(session) ?? signal
                  return (
                    <tr key={session}>
                      <td>{session}</td>
                      <td>{outcome ? `${outcome.side} · ${outcome.status}${outcome.late ? ' · late' : ''}` : '—'}</td>
                      <td>{fill ? `${fill.side} ${fill.quantity} at ${amount(fill.price)}` : '—'}</td>
                      <td>{amount(mark.equity)}</td><td>{amount(mark.net_pnl)}</td>
                    </tr>
                  )
                })}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}
