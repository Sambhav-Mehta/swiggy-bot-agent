import { useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'

export default function Step1Personal({ data, onNext }) {
  const { user } = useAuth()
  const [form, setForm] = useState({
    name:  data.name  || user?.name || '',
    phone: data.phone || '',
    city:  data.city  || '',
  })
  const [error, setError] = useState('')
  const set = f => e => setForm(p => ({ ...p, [f]: e.target.value }))

  const handleNext = e => {
    e.preventDefault()
    if (!form.name.trim() || !form.city.trim()) { setError('Name and city are required.'); return }
    onNext(form)
  }

  return (
    <Card title="Tell us about yourself" subtitle="We'll personalize your experience.">
      <form onSubmit={handleNext} className="space-y-4">
        <Field label="Full Name *" value={form.name} onChange={set('name')} placeholder="Sambhav Mehta" />
        <Field label="Phone (optional)" value={form.phone} onChange={set('phone')} placeholder="+91 9876543210" type="tel" />
        <Field label="Delivery City *" value={form.city} onChange={set('city')} placeholder="Viman Nagar, Pune" />
        {error && <p className="text-red-400 text-xs">{error}</p>}
        <Btn>Next →</Btn>
      </form>
    </Card>
  )
}

// ── Shared sub-components ────────────────────────────────────────────────────

export function Card({ title, subtitle, children }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 shadow-2xl">
      <h2 className="text-xl font-bold text-white mb-1">{title}</h2>
      {subtitle && <p className="text-slate-400 text-sm mb-6">{subtitle}</p>}
      {children}
    </div>
  )
}

export function Field({ label, value, onChange, placeholder, type = 'text' }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full bg-slate-700 border border-slate-600 text-slate-100 placeholder-slate-500 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
      />
    </div>
  )
}

export function Btn({ children, onClick, disabled, secondary }) {
  return (
    <button
      type={onClick ? 'button' : 'submit'}
      onClick={onClick}
      disabled={disabled}
      className={`w-full font-semibold py-3 rounded-xl transition-all
        ${secondary
          ? 'bg-slate-700 hover:bg-slate-600 text-slate-300'
          : 'bg-orange-500 hover:bg-orange-600 text-white'
        } disabled:opacity-50`}
    >
      {children}
    </button>
  )
}
