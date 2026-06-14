import { useGoogleLogin } from '@react-oauth/google'
import { useState } from 'react'

export default function LoginPage({ onLogin }) {
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const login = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: { Authorization: `Bearer ${tokenResponse.access_token}` },
        })
        const profile = await res.json()
        onLogin({ ...profile, access_token: tokenResponse.access_token })
      } catch {
        setError('Failed to fetch profile. Please try again.')
      } finally {
        setLoading(false)
      }
    },
    onError: () => {
      setError('Sign-in was cancelled or failed. Please try again.')
      setLoading(false)
    },
  })

  return (
    <div className="page">
      <div className="card">
        <div className="logo-mark">
          <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
            <polyline points="2,18 8,10 13,14 18,6 24,9" stroke="#e8a020" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
            <circle cx="24" cy="9" r="2.5" fill="#1d9e75"/>
          </svg>
        </div>

        <div className="ticker-strip">
          <span className="ticker up">AAPL +1.2%</span>
          <span className="ticker up">NVDA +3.4%</span>
          <span className="ticker dn">TSLA −0.8%</span>
        </div>

        <h1 className="title">Stock Research Agent</h1>
        <p className="subtitle">AI-powered market analysis.<br/>Sign in to access your dashboard.</p>

        <div className="divider" />

        {error && <div className="error-banner">{error}</div>}

        <button
          className="google-btn"
          onClick={() => { setError(null); login() }}
          disabled={loading}
        >
          {loading ? <span className="spinner" /> : <GoogleIcon />}
          <span>{loading ? 'Signing in…' : 'Continue with Google'}</span>
        </button>

        <p className="legal">
          By signing in, you agree to our{' '}
          <a href="#">Terms of Service</a> and{' '}
          <a href="#">Privacy Policy</a>.
        </p>
      </div>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
      <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.909-2.259c-.806.54-1.837.86-3.047.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853"/>
      <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
    </svg>
  )
}
