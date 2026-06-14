import { useState } from 'react'
import LoginPage from './LoginPage'
import Dashboard from './Dashboard'

export default function App() {
  const [user, setUser] = useState(null)

  return user
    ? <Dashboard user={user} onLogout={() => setUser(null)} />
    : <LoginPage onLogin={setUser} />
}
