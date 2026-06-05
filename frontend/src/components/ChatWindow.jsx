import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MessageBubble from './MessageBubble'
import { useChat } from '../hooks/useChat'
import { useAuth } from '../contexts/AuthContext'

export default function ChatWindow() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { messages, sendMessage, isThinking, currentAgent, resetSession } = useChat()
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)

  // Auto-scroll to the latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentAgent])

  const handleSend = () => {
    const text = input.trim()
    if (!text || isThinking) return
    setInput('')
    sendMessage(text)
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleNewChat = () => resetSession()

  return (
    <div className="flex flex-col h-screen bg-slate-900">
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 bg-slate-800 border-b border-slate-700 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xl">🍔</span>
          <div>
            <div className="text-white font-semibold text-sm leading-tight">Swiggy Bot</div>
            <div className="text-slate-400 text-xs">{user?.name || 'Guest'}</div>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate('/settings')}
            className="text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-slate-700 transition-colors"
          >
            Settings
          </button>
          <button
            onClick={handleNewChat}
            className="text-xs text-orange-400 hover:text-orange-300 px-3 py-1.5 rounded-lg hover:bg-slate-700 transition-colors"
          >
            New Chat
          </button>
        </div>
      </div>

      {/* ── Messages ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 chat-scroll">
        {messages.length === 0 && (
          <div className="text-center mt-16 text-slate-500">
            <div className="text-4xl mb-3">🎤</div>
            <p className="text-sm font-medium text-slate-400">Seedhe Maut Vibe Active</p>
            <p className="text-xs mt-1">Ask me to find food, apply deals, and build your cart.</p>
            <div className="mt-4 flex flex-wrap gap-2 justify-center">
              {[
                'Find high-protein veg meal under ₹300',
                'What are the best rated restaurants near me?',
                'I want Paneer Tikka — find best deal',
              ].map(s => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  className="text-xs bg-slate-800 border border-slate-700 text-slate-300 px-3 py-1.5 rounded-full hover:border-orange-500 hover:text-orange-400 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => <MessageBubble key={i} message={msg} />)}

        {/* Thinking indicator */}
        {isThinking && currentAgent && (
          <div className="flex items-center gap-2 mb-3 text-xs text-slate-400">
            <div className="flex gap-1">
              {[0,1,2].map(i => <div key={i} className="dot w-1.5 h-1.5 bg-orange-400 rounded-full" />)}
            </div>
            <span>{currentAgent}</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Input bar ──────────────────────────────────────────── */}
      <div className="px-4 py-3 bg-slate-800 border-t border-slate-700 flex-shrink-0">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Type a message… (Enter to send)"
            rows={1}
            disabled={isThinking}
            className="flex-1 bg-slate-700 border border-slate-600 text-slate-100 placeholder-slate-500 rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent disabled:opacity-50 leading-relaxed"
            style={{ maxHeight: '120px', overflowY: 'auto' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isThinking}
            className="bg-orange-500 hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl px-4 py-2.5 text-sm font-medium transition-colors flex-shrink-0"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
