import { useState } from 'react'
import { api } from '../../contexts/AuthContext'
import { Card, Field, Btn } from './Step1Personal'

export default function Step3Address({ data, onFinish, onBack, saving }) {
  const [form, setForm] = useState({
    label:        'Home',
    full_address: data.full_address || '',
    city:         data.city || '',
    pincode:      '',
    is_default:   true,
  })
  const [error, setError] = useState('')

  const set = f => e => setForm(p => ({ ...p, [f]: e.target.value }))

  const handleFinish = async e => {
    e.preventDefault()
    if (!form.full_address.trim()) { setError('Please enter your delivery address.'); return }
    setError('')

    try {
      // Save address to DB and get back the ID
      const { data: addr } = await api.post('/api/addresses', form)
      onFinish({ default_address_id: addr.swiggy_addr_id || addr.id })
    } catch (err) {
      setError('Could not save address. Please try again.')
    }
  }

  return (
    <Card title="Delivery Address" subtitle="Where should your food arrive? You can add more later.">
      <form onSubmit={handleFinish} className="space-y-4">
        {/* Label selector */}
        <div>
          <label className="block text-xs text-slate-400 mb-2">Address Label</label>
          <div className="flex gap-2">
            {['Home', 'Work', 'Other'].map(l => (
              <button key={l} type="button"
                onClick={() => setForm(p => ({ ...p, label: l }))}
                className={`flex-1 py-2 rounded-xl border text-sm transition-all
                  ${form.label === l
                    ? 'border-orange-500 bg-orange-500/10 text-white'
                    : 'border-slate-600 bg-slate-700 text-slate-300'}`}
              >
                {l === 'Home' ? '🏠' : l === 'Work' ? '🏢' : '📍'} {l}
              </button>
            ))}
          </div>
        </div>

        <Field label="Full Address *" value={form.full_address} onChange={set('full_address')}
          placeholder="Flat / House no., Building, Area" />
        <div className="grid grid-cols-2 gap-3">
          <Field label="City" value={form.city} onChange={set('city')} placeholder="Your city" />
          <Field label="Pincode" value={form.pincode} onChange={set('pincode')} placeholder="000000" />
        </div>

        {error && <p className="text-red-400 text-xs">{error}</p>}

        <p className="text-slate-500 text-xs">
          💡 After completing setup, you can connect your Swiggy account from Settings
          to sync your saved addresses automatically.
        </p>

        <div className="flex gap-3">
          <Btn secondary onClick={onBack}>← Back</Btn>
          <Btn disabled={saving}>{saving ? 'Saving…' : 'Start Chatting 🚀'}</Btn>
        </div>
      </form>
    </Card>
  )
}
