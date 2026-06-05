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

  useEffect(() => {
    Promise.all([
      api.get('/api/profile'),
      api.get('/api/addresses'),
    ]).then(([p, a]) => {
      setProfile(p.data)
      setAddresses(a.data)
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
