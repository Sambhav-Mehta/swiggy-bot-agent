import { useState, useCallback, useRef } from 'react'
import { buildPersonaPayload } from '../utils/persona'

const SESSION_KEY = 'swiggy_session_id'

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

export function useChat(persona) {
  const [messages, setMessages]     = useState([])
  const [isThinking, setIsThinking] = useState(false)
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

    // Add user message immediately
    setMessages(prev => [...prev, { role: 'user', text }])
    setIsThinking(true)
    setCurrentAgent(null)

    // Placeholder for the bot reply (will be streamed into)
    const botId = Date.now()
    setMessages(prev => [...prev, { role: 'bot', text: '', id: botId, streaming: true }])

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message:    text,
          session_id: sessionId.current,
          persona:    buildPersonaPayload(persona),
        }),
      })

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader  = resp.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()   // keep incomplete line

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
  }, [persona, isThinking])

  return { messages, sendMessage, isThinking, currentAgent, resetSession }
}
