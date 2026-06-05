import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth, api } from '../../contexts/AuthContext'
import Step1Personal from './Step1Personal'
import Step2Fitness  from './Step2Fitness'
import Step3Address  from './Step3Address'

const STEPS = ['Personal', 'Fitness Profile', 'Delivery Address']

export default function OnboardingFlow() {
  const { refreshProfile } = useAuth()
  const navigate = useNavigate()
  const [step, setStep]   = useState(0)
  const [data, setData]   = useState({})   // accumulates across steps
  const [saving, setSaving] = useState(false)

  const next  = patch => setData(p => ({ ...p, ...patch })) || setStep(s => s + 1)
  const back  = () => setStep(s => s - 1)

  const finish = async patch => {
    const final = { ...data, ...patch, onboarding_done: true }
    setSaving(true)
    try {
      await api.put('/api/profile', final)
      await refreshProfile()
      navigate('/chat', { replace: true })
    } catch (err) {
      console.error('Onboarding save failed', err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center p-4">
      {/* Progress bar */}
      <div className="w-full max-w-lg mb-6">
        <div className="flex items-center gap-2 mb-2">
          {STEPS.map((label, i) => (
            <div key={i} className="flex items-center flex-1">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0
                ${i <= step ? 'bg-orange-500 text-white' : 'bg-slate-700 text-slate-400'}`}>
                {i < step ? '✓' : i + 1}
              </div>
              {i < STEPS.length - 1 && (
                <div className={`h-0.5 flex-1 mx-1 ${i < step ? 'bg-orange-500' : 'bg-slate-700'}`} />
              )}
            </div>
          ))}
        </div>
        <p className="text-slate-400 text-xs text-center">
          Step {step + 1} of {STEPS.length} — {STEPS[step]}
        </p>
      </div>

      {/* Step content */}
      <div className="w-full max-w-lg">
        {step === 0 && <Step1Personal data={data} onNext={next} />}
        {step === 1 && <Step2Fitness  data={data} onNext={next} onBack={back} />}
        {step === 2 && <Step3Address  data={data} onFinish={finish} onBack={back} saving={saving} />}
      </div>
    </div>
  )
}
