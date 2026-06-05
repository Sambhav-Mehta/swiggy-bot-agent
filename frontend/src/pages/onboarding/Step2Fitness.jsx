import { useState } from 'react'
import { Card, Field, Btn } from './Step1Personal'

const FITNESS_GOALS = [
  { value: 'muscle_gain',  label: '💪 Muscle Gain',    desc: 'High protein, calorie surplus' },
  { value: 'weight_loss',  label: '🔥 Weight Loss',    desc: 'Low cal, high protein, low sugar' },
  { value: 'maintenance',  label: '⚖️ Maintenance',    desc: 'Balanced macros' },
  { value: 'general',      label: '🥗 General Health', desc: 'Clean, nutritious food' },
]
const DIET_TYPES = [
  { value: 'veg',     label: '🌱 Vegetarian' },
  { value: 'non_veg', label: '🍗 Non-Vegetarian' },
  { value: 'both',    label: '🍽️ Both' },
]
const COMMON_RESTRICTIONS = ['No Mushrooms', 'No Onion', 'No Garlic', 'Gluten-Free', 'Dairy-Free']
const CUISINES = ['North Indian', 'South Indian', 'Chinese', 'Italian', 'Mexican', 'Continental']

export default function Step2Fitness({ data, onNext, onBack }) {
  const [form, setForm] = useState({
    fitness_goal:   data.fitness_goal   || 'general',
    diet_type:      data.diet_type      || 'veg',
    restrictions:   data.restrictions   || [],
    cuisine_prefs:  data.cuisine_prefs  || [],
    budget_wkday:   data.budget_wkday   || 500,
    budget_wknd:    data.budget_wknd    || 1500,
    saved_cards:    data.saved_cards    || [],
  })

  const toggle = (field, val) => {
    setForm(p => {
      const arr = p[field] || []
      return { ...p, [field]: arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val] }
    })
  }
  const set = f => e => setForm(p => ({ ...p, [f]: e.target.value }))

  const handleNext = e => { e.preventDefault(); onNext(form) }

  return (
    <Card title="Fitness & Food Profile" subtitle="The bot uses this to filter meals that match your goals.">
      <form onSubmit={handleNext} className="space-y-5">

        {/* Fitness goal */}
        <div>
          <label className="block text-xs text-slate-400 mb-2">Fitness Goal</label>
          <div className="grid grid-cols-2 gap-2">
            {FITNESS_GOALS.map(g => (
              <button key={g.value} type="button"
                onClick={() => setForm(p => ({ ...p, fitness_goal: g.value }))}
                className={`p-2.5 rounded-xl border text-left transition-all
                  ${form.fitness_goal === g.value
                    ? 'border-orange-500 bg-orange-500/10 text-white'
                    : 'border-slate-600 bg-slate-700 text-slate-300 hover:border-slate-500'}`}
              >
                <div className="text-sm font-medium">{g.label}</div>
                <div className="text-xs text-slate-400 mt-0.5">{g.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Diet type */}
        <div>
          <label className="block text-xs text-slate-400 mb-2">Diet Type</label>
          <div className="flex gap-2">
            {DIET_TYPES.map(d => (
              <button key={d.value} type="button"
                onClick={() => setForm(p => ({ ...p, diet_type: d.value }))}
                className={`flex-1 py-2 rounded-xl border text-sm transition-all
                  ${form.diet_type === d.value
                    ? 'border-orange-500 bg-orange-500/10 text-white'
                    : 'border-slate-600 bg-slate-700 text-slate-300'}`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        {/* Restrictions */}
        <div>
          <label className="block text-xs text-slate-400 mb-2">Dietary Restrictions</label>
          <div className="flex flex-wrap gap-2">
            {COMMON_RESTRICTIONS.map(r => (
              <Chip key={r} label={r} active={form.restrictions.includes(r.toLowerCase().replace(' ', '_'))}
                onClick={() => toggle('restrictions', r.toLowerCase().replace(' ', '_'))} />
            ))}
          </div>
        </div>

        {/* Cuisines */}
        <div>
          <label className="block text-xs text-slate-400 mb-2">Cuisine Preferences</label>
          <div className="flex flex-wrap gap-2">
            {CUISINES.map(c => (
              <Chip key={c} label={c} active={form.cuisine_prefs.includes(c.toLowerCase().replace(' ', '_'))}
                onClick={() => toggle('cuisine_prefs', c.toLowerCase().replace(' ', '_'))} />
            ))}
          </div>
        </div>

        {/* Budget */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Weekday Budget (₹/meal)</label>
            <input type="number" value={form.budget_wkday} onChange={set('budget_wkday')} min={50} step={50}
              className="w-full bg-slate-700 border border-slate-600 text-slate-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Weekend Budget (₹/meal)</label>
            <input type="number" value={form.budget_wknd} onChange={set('budget_wknd')} min={50} step={50}
              className="w-full bg-slate-700 border border-slate-600 text-slate-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500" />
          </div>
        </div>

        {/* Saved cards */}
        <div>
          <label className="block text-xs text-slate-400 mb-2">Saved Cards (for deal matching)</label>
          <div className="flex flex-wrap gap-2">
            {['hdfc_swiggy', 'sbi_cashback', 'axis_flipkart', 'icici_amazon'].map(c => (
              <Chip key={c} label={c.replace('_', ' ').toUpperCase()} active={form.saved_cards.includes(c)}
                onClick={() => toggle('saved_cards', c)} />
            ))}
          </div>
        </div>

        <div className="flex gap-3">
          <Btn secondary onClick={onBack}>← Back</Btn>
          <Btn>Next →</Btn>
        </div>
      </form>
    </Card>
  )
}

function Chip({ label, active, onClick }) {
  return (
    <button type="button" onClick={onClick}
      className={`px-3 py-1 rounded-full text-xs border transition-all
        ${active
          ? 'border-orange-500 bg-orange-500/15 text-orange-300'
          : 'border-slate-600 text-slate-400 hover:border-slate-500'}`}
    >
      {label}
    </button>
  )
}
