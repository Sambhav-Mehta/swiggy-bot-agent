import { useState } from 'react'
import { EMPTY_PERSONA } from '../utils/persona'

export default function PersonaForm({ onSubmit, initialValues }) {
  const [form, setForm] = useState(() => ({ ...EMPTY_PERSONA, ...(initialValues || {}) }))
  const [error, setError] = useState('')

  const set = (field) => (e) => setForm(prev => ({ ...prev, [field]: e.target.value }))

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.location.trim()) {
      setError('Name and location are required.')
      return
    }
    setError('')
    onSubmit(form)
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-slate-800 border border-slate-700 rounded-2xl p-8 shadow-2xl">

        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-4xl mb-3">🍔</div>
          <h1 className="text-2xl font-bold text-white">Swiggy Bot</h1>
          <p className="text-slate-400 text-sm mt-1">
            Your AI-powered food ordering assistant. Set up your profile to get started.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Required fields */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Your Name *" value={form.name} onChange={set('name')} placeholder="e.g. Aarav Sharma" />
            <Field label="Delivery City *" value={form.location} onChange={set('location')} placeholder="e.g. Pune" />
          </div>

          <Field label="Dietary Goals" value={form.diet_goals} onChange={set('diet_goals')} placeholder="High-protein, low-sugar" />
          <Field label="Restrictions / Allergies" value={form.restrictions} onChange={set('restrictions')} placeholder="No mushrooms, vegetarian only" />
          <Field label="Cuisine Preferences" value={form.preferences} onChange={set('preferences')} placeholder="Spicy North Indian, loves paneer" />

          <div className="grid grid-cols-2 gap-3">
            <Field label="Weekday Budget" value={form.budget_wkday} onChange={set('budget_wkday')} placeholder="Under ₹500/meal" />
            <Field label="Weekend Budget" value={form.budget_wknd} onChange={set('budget_wknd')} placeholder="Up to ₹1500+" />
          </div>

          {error && <p className="text-red-400 text-xs">{error}</p>}

          <button
            type="submit"
            className="w-full bg-orange-500 hover:bg-orange-600 active:scale-[0.98] text-white font-semibold py-3 rounded-xl transition-all mt-2"
          >
            Start Chatting →
          </button>
        </form>
      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full bg-slate-700 border border-slate-600 text-slate-100 placeholder-slate-500 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
      />
    </div>
  )
}
