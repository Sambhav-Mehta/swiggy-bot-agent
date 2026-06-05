import { useState, useCallback, useRef } from 'react'

const SESSION_KEY = 'swiggy_session_id'
const TOKEN_KEY   = 'swiggy_token'

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

export function useChat() {
  const [messages, setMessages]         = useState([])
  const [isThinking, setIsThinking]     = useState(false)
  const [currentAgent, setCurrentAgent] = useState(null)
  const sessionId = useRef(getSessionId())

  const resetSession = useCallback(() => {
    const newId = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, newId)
    sessionId.current = newId
    setMessages([])
    setIsThinking(false)
    setCurrentAgent(null)
  }, [])

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isThinking) return

    setMessages(prev => [...prev, { role: 'user', text }])
    setIsThinking(true)
    setCurrentAgent(null)

    const botId = Date.now()
    setMessages(prev => [...prev, { role: 'bot', text: '', id: botId, streaming: true }])

    try {
      const token = localStorage.getItem(TOKEN_KEY)
      const resp = await fetch('/api/chat', {
        method:  'POST',
        headers: {
          'Content-Type':  'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        // persona is now loaded server-side from the DB — not sent by the client
        body: JSON.stringify({
          message:    text,
          session_id: sessionId.current,
        }),
      })

      if (resp.status === 401) {
        setMessages(prev => prev.map(m =>
          m.id === botId
            ? { ...m, streaming: false, text: '⚠️ Session expired. Please log in again.' }
            : m
        ))
        return
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader  = resp.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const evt = JSON.parse(line.slice(6))

          if (evt.type === 'thinking') {
            setCurrentAgent(evt.label)
          } else if (evt.type === 'text') {
            setMessages(prev => prev.map(m =>
              m.id === botId ? { ...m, text: m.text + evt.text } : m
            ))
          } else if (evt.type === 'done' || evt.type === 'error') {
            setMessages(prev => prev.map(m =>
              m.id === botId
                ? { ...m, streaming: false, text: evt.type === 'error' ? `⚠️ ${evt.text}` : m.text }
                : m
            ))
          }
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === botId
          ? { ...m, streaming: false, text: `⚠️ Connection error: ${err.message}` }
          : m
      ))
    } finally {
      setIsThinking(false)
      setCurrentAgent(null)
    }
  }, [isThinking])

  return { messages, sendMessage, isThinking, currentAgent, resetSession }
}
