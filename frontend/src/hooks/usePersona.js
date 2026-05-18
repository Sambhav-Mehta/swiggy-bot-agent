import { useState } from 'react'
import { EMPTY_PERSONA } from '../utils/persona'

const STORAGE_KEY = 'swiggy_persona'

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

export function usePersona() {
  const [persona, setPersonaState] = useState(() => load())

  const setPersona = (data) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    setPersonaState(data)
  }

  const clearPersona = () => {
    localStorage.removeItem(STORAGE_KEY)
    setPersonaState(null)
  }

  const hasPersona = !!(persona?.name && persona?.location)

  return { persona, setPersona, clearPersona, hasPersona }
}
