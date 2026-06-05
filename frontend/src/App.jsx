import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import LoginPage      from './pages/LoginPage'
import RegisterPage   from './pages/RegisterPage'
import OnboardingFlow from './pages/onboarding/OnboardingFlow'
import ChatPage       from './components/ChatWindow'   // existing component, promoted to page
import SettingsPage   from './pages/SettingsPage'

// ── Protected route wrapper ──────────────────────────────────────────────────
function Protected({ children, requireOnboarding = true }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace />
  if (requireOnboarding && !user.onboarding_done) return <Navigate to="/onboarding" replace />
  return children
}

// ── Root redirect ────────────────────────────────────────────────────────────
function Root() {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace />
  if (!user.onboarding_done) return <Navigate to="/onboarding" replace />
  return <Navigate to="/chat" replace />
}

function Spinner() {
  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

// ── App shell ────────────────────────────────────────────────────────────────
function AppRoutes() {
  return (
    <Routes>
      <Route path="/"           element={<Root />} />
      <Route path="/login"      element={<LoginPage />} />
      <Route path="/register"   element={<RegisterPage />} />

      {/* Onboarding: authed but does NOT require onboarding_done */}
      <Route path="/onboarding/*" element={
        <Protected requireOnboarding={false}>
          <OnboardingFlow />
        </Protected>
      } />

      <Route path="/chat" element={
        <Protected>
          <ChatPage />
        </Protected>
      } />

      <Route path="/settings" element={
        <Protected>
          <SettingsPage />
        </Protected>
      } />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
