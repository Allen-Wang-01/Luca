import { useEffect, useState } from 'react'

type BackendStatus = 'checking' | 'connected' | 'unreachable'

function App() {
  const [status, setStatus] = useState<BackendStatus>('checking')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((data) => setStatus(data.status === 'ok' ? 'connected' : 'unreachable'))
      .catch(() => setStatus('unreachable'))
  }, [])

  return (
    <main>
      <h1>Financial Agent</h1>
      <p>Backend status: {status}</p>
    </main>
  )
}

export default App
