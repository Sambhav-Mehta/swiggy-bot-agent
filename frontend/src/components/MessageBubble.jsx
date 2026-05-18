import ReactMarkdown from 'react-markdown'

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end mb-3">
        <div className="max-w-[75%] bg-orange-500 text-white px-4 py-2.5 rounded-2xl rounded-br-sm text-sm leading-relaxed">
          {message.text}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start mb-3">
      <div className="flex gap-2.5 max-w-[85%]">
        {/* Bot avatar */}
        <div className="w-7 h-7 rounded-full bg-orange-500 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">
          🍔
        </div>

        <div
          className={`bg-slate-800 border border-slate-700 px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed bot-md${message.streaming ? ' cursor' : ''}`}
        >
          {message.text
            ? <ReactMarkdown>{message.text}</ReactMarkdown>
            : <span className="text-slate-500 italic text-xs">Thinking…</span>
          }
        </div>
      </div>
    </div>
  )
}
