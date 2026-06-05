import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import axios from 'axios'

const AuthContext = createContext(null)

const TOKEN_KEY   = 'swiggy_token'
const SESSION_KEY = 'swiggy_session_id'

// Axios instance — injects JWT on every request automatically
export const api = axios.create({ baseURL: '/' })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

export function AuthProvider({ children }) {
  const [user, setUser]         = useState(null)   // { user_id, email, name, onboarding_done }
  const [loading, setLoading]   = useState(true)

  // On mount, verify stored token with /api/auth/me
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) { setLoading(false); return }

    api.get('/api/auth/me')
      .then(r => {
        const p = r.data.profile
        setUser({
          user_id:          r.data.user_id,
          email:            r.data.email,
          name:             p?.name,
          onboarding_done:  r.data.onboarding_done,
        })
      })
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    const { data } = await api.post('/api/auth/login', { email, password })
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setUser({
      user_id:         data.user_id,
      email:           data.email,
      name:            data.name,
      onboarding_done: data.onboarding_done,
    })
    return data
  }, [])

  const register = useCallback(async (email, password, name) => {
    const { data } = await api.post('/api/auth/register', { email, password, name })
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setUser({
      user_id:         data.user_id,
      email:           data.email,
      name:            data.name,
      onboarding_done: false,
    })
    return data
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(SESSION_KEY)
    setUser(null)
  }, [])

  const refreshProfile = useCallback(async () => {
    const r = await api.get('/api/auth/me')
    const p = r.data.profile
    setUser(prev => ({
      ...prev,
      name:            p?.name,
      onboarding_done: r.data.onboarding_done,
    }))
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
