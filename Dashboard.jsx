export default function Dashboard({ user, onLogout }) {
  return (
    <div className="page">
      <div className="card">
        <img
          src={user.picture}
          alt={user.name}
          className="avatar"
          referrerPolicy="no-referrer"
        />
        <h1 className="title">Welcome back, {user.given_name}</h1>
        <p className="subtitle">{user.email}</p>

        <div className="info-row">
          <span className="badge">✓ Verified</span>
          {user.email_verified && <span className="badge success">Email confirmed</span>}
        </div>

        <div className="stat-row">
          <div className="stat-box">
            <span className="stat-label">Watchlist</span>
            <span className="stat-val amber">12 stocks</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Alerts</span>
            <span className="stat-val green">3 active</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Reports</span>
            <span className="stat-val">7 saved</span>
          </div>
        </div>

        <button className="logout-btn" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </div>
  )
}
