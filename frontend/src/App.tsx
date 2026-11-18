import { useEffect, useState } from 'react'
import { loadSignals, type PilotSignal } from './api/signals'

export default function App() {
  const [signals, setSignals] = useState<PilotSignal[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    loadSignals(controller.signal).then(setSignals).catch(() => {
      if (!controller.signal.aborted) setError(true)
    })
    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>Closing Cross Pilot</h1>
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
