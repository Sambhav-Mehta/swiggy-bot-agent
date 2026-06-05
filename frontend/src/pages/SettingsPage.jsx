import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth, api } from '../contexts/AuthContext'

export default function SettingsPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [profile, setProfile] = useState(null)
  const [addresses, setAddresses] = useState([])
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [swiggy, setSwiggy] = useState({ connected: false })

  useEffect(() => {
    Promise.all([
      api.get('/api/profile'),
      api.get('/api/addresses'),
      api.get('/api/swiggy/status'),
    ]).then(([p, a, s]) => {
      setProfile(p.data)
      setAddresses(a.data)
      setSwiggy(s.data)
    }).catch(() => {})
  }, [])

  const handleLogout = () => { logout(); navigate('/login', { replace: true }) }

  const saveProfile = async () => {
    setSaving(true)
    try {
      await api.put('/api/profile', profile)
      setMsg('Profile saved!')
      setTimeout(() => setMsg(''), 2000)
    } catch { setMsg('Save failed.') }
    finally { setSaving(false) }
  }

  const set = f => e => setProfile(p => ({ ...p, [f]: e.target.value }))

  if (!profile) return <Loading />

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-slate-800 border-b border-slate-700">
        <button onClick={() => navigate('/chat')} className="text-slate-400 hover:text-white text-sm">← Back to Chat</button>
        <span className="font-semibold text-sm">Settings</span>
        <button onClick={handleLogout} className="text-red-400 hover:text-red-300 text-sm">Logout</button>
      </div>

      <div className="max-w-lg mx-auto p-4 space-y-6 pb-16">

        {/* Profile */}
        <Section title="Your Profile">
          <Label>Name</Label>
          <Input value={profile.name || ''} onChange={set('name')} placeholder="Your name" />
          <Label>City</Label>
          <Input value={profile.city || ''} onChange={set('city')} placeholder="Delivery city" />
          <Label>Fitness Goal</Label>
          <select value={profile.fitness_goal || 'general'} onChange={set('fitness_goal')}
            className="w-full bg-slate-700 border border-slate-600 text-slate-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500">
            <option value="muscle_gain">Muscle Gain</option>
            <option value="weight_loss">Weight Loss</option>
            <option value="maintenance">Maintenance</option>
            <option value="general">General Health</option>
          </select>
          <Label>Diet Type</Label>
          <select value={profile.diet_type || 'veg'} onChange={set('diet_type')}
            className="w-full bg-slate-700 border border-slate-600 text-slate-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500">
            <option value="veg">Vegetarian</option>
            <option value="non_veg">Non-Vegetarian</option>
            <option value="both">Both</option>
          </select>

          {msg && <p className={`text-xs ${msg.includes('failed') ? 'text-red-400' : 'text-green-400'}`}>{msg}</p>}

          <button onClick={saveProfile} disabled={saving}
            className="w-full bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl text-sm transition-all">
            {saving ? 'Saving…' : 'Save Profile'}
          </button>
        </Section>

        {/* Addresses */}
        <Section title="Delivery Addresses">
          {addresses.length === 0
            ? <p className="text-slate-500 text-sm">No addresses saved yet.</p>
            : addresses.map(a => (
              <div key={a.id} className="flex items-center justify-between bg-slate-700 rounded-xl px-4 py-3">
                <div>
                  <span className="text-xs text-orange-400 font-medium">{a.label}</span>
                  <p className="text-sm text-slate-200 mt-0.5">{a.full_address}</p>
                  {a.is_default && <span className="text-xs text-slate-400">Default</span>}
                </div>
              </div>
            ))
          }
          <button onClick={() => navigate('/onboarding')}
            className="w-full bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm font-medium py-2.5 rounded-xl transition-all mt-2">
            + Add Address
          </button>
        </Section>

        {/* Swiggy connection */}
        <SwiggySection swiggy={swiggy} setSwiggy={setSwiggy} />

        {/* Account */}
        <Section title="Account">
          <p className="text-sm text-slate-400">{user?.email}</p>
          <button onClick={handleLogout}
            className="w-full bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 text-sm font-medium py-2.5 rounded-xl transition-all mt-2">
            Sign Out
          </button>
        </Section>
      </div>
    </div>
  )
}

function SwiggySection({ swiggy, setSwiggy }) {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ session_token: '', mcp_server_url: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const connect = async () => {
    setErr(''); setBusy(true)
    try {
      const { data } = await api.post('/api/swiggy/connect', form)
      setSwiggy({ connected: true, mcp_server_url: form.mcp_server_url })
      setShowForm(false)
      setForm({ session_token: '', mcp_server_url: '' })
    } catch (e) {
      setErr(e.response?.data?.detail || 'Connection failed.')
    } finally { setBusy(false) }
  }

  const disconnect = async () => {
    setBusy(true)
    try {
      await api.delete('/api/swiggy/disconnect')
      setSwiggy({ connected: false })
    } catch {} finally { setBusy(false) }
  }

  return (
    <Section title="Swiggy Account">
      {swiggy.connected ? (
        <>
          <div className="flex items-center gap-2 text-sm text-green-400">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            Connected — orders use your own Swiggy account
          </div>
          <button onClick={disconnect} disabled={busy}
            className="w-full bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm font-medium py-2.5 rounded-xl transition-all mt-2">
            {busy ? 'Disconnecting…' : 'Disconnect'}
          </button>
        </>
      ) : (
        <>
          <p className="text-sm text-slate-400">
            Not connected. The bot uses a shared demo account.
            Connect your own Swiggy to order from your account.
          </p>

          {!showForm ? (
            <button onClick={() => setShowForm(true)}
              className="w-full bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold py-2.5 rounded-xl transition-all mt-2">
              Connect My Swiggy
            </button>
          ) : (
            <div className="space-y-3 mt-2">
              <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3 text-xs text-slate-400 leading-relaxed">
                <strong className="text-slate-300">How to get these:</strong>
                <ol className="list-decimal ml-4 mt-1 space-y-1">
                  <li>Open <span className="text-orange-400">claude.ai</span> → Settings → Connectors</li>
                  <li>Connect <strong>Swiggy Food</strong> if not already</li>
                  <li>Copy your MCP server URL and access token</li>
                </ol>
              </div>
              <Label>Swiggy MCP Server URL</Label>
              <Input value={form.mcp_server_url}
                onChange={e => setForm(f => ({ ...f, mcp_server_url: e.target.value }))}
                placeholder="https://mcp-proxy.anthropic.com/v1/mcp/mcpsrv_..." />
              <Label>Access Token</Label>
              <Input value={form.session_token}
                onChange={e => setForm(f => ({ ...f, session_token: e.target.value }))}
                placeholder="sk-ant-oat01-..." />

              {err && <p className="text-red-400 text-xs">{err}</p>}

              <div className="flex gap-2">
                <button onClick={connect} disabled={busy || !form.session_token || !form.mcp_server_url}
                  className="flex-1 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white text-sm font-semibold py-2.5 rounded-xl transition-all">
                  {busy ? 'Verifying…' : 'Verify & Connect'}
                </button>
                <button onClick={() => { setShowForm(false); setErr('') }}
                  className="px-4 bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm rounded-xl transition-all">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </Section>
  )
}

function Section({ title, children }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5 space-y-3">
      <h3 className="text-sm font-semibold text-slate-300 mb-1">{title}</h3>
      {children}
    </div>
  )
}
function Label({ children }) { return <label className="block text-xs text-slate-400 mt-1">{children}</label> }
function Input({ value, onChange, placeholder }) {
  return <input value={value} onChange={onChange} placeholder={placeholder}
    className="w-full bg-slate-700 border border-slate-600 text-slate-100 placeholder-slate-500 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
}
function Loading() {
  return <div className="min-h-screen bg-slate-900 flex items-center justify-center text-slate-400">Loading…</div>
}
