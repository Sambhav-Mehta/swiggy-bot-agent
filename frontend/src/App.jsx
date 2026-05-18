import { useState } from 'react'
import './index.css'
import PersonaForm from './components/PersonaForm'
import ChatWindow from './components/ChatWindow'
import { usePersona } from './hooks/usePersona'

export default function App() {
  const { persona, setPersona, clearPersona, hasPersona } = usePersona()
  const [editing, setEditing] = useState(false)

  if (!hasPersona || editing) {
    return (
      <PersonaForm
        initialValues={persona}
        onSubmit={(data) => {
          setPersona(data)
          setEditing(false)
        }}
      />
    )
  }

  return (
    <ChatWindow
      persona={persona}
      onEditPersona={() => setEditing(true)}
      onNewChat={() => {}}
    />
  )
}
