import React, { useRef, useState, useEffect } from 'react';
import { useAppStore } from '../store/appStore';
import type { ChatMessage } from '../types';

interface ChatPanelProps {
  onSendMessage: (text: string) => void;
}

const EXAMPLE_PROMPTS = [
  'Create a 90m lattice tower',
  'Add 3 antennas near the top',
  'Run wind analysis at 50 m/s',
  'Make the tower more stable',
  'Generate engineering report',
  'Add a microwave dish at 70m facing north',
  'Increase height to 120m',
  'Change bracing to K-bracing',
];

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  const isSystem = msg.role === 'system';

  if (isSystem) {
    return (
      <div className="text-xs text-gray-500 text-center my-1 px-2">
        {msg.content}
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`max-w-xs md:max-w-sm lg:max-w-md rounded-xl px-4 py-3 text-sm ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-none'
            : 'bg-gray-800 text-gray-100 rounded-bl-none border border-gray-700'
        }`}
      >
        {!isUser && (
          <div className="flex items-center gap-1 mb-1">
            <span className="text-blue-400 text-xs font-semibold">⚙ TOWER-AI</span>
            {msg.tool_called && (
              <span className="text-xs text-gray-500 bg-gray-700 rounded px-1">
                [{msg.tool_called}]
              </span>
            )}
          </div>
        )}
        <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
        <div className="text-xs opacity-40 mt-1 text-right">
          {new Date(msg.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex justify-start mb-3">
      <div className="bg-gray-800 border border-gray-700 rounded-xl rounded-bl-none px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-blue-400 text-xs font-semibold">⚙ TOWER-AI</span>
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ChatPanel({ onSendMessage }: ChatPanelProps) {
  const messages = useAppStore((s) => s.messages);
  const thinking = useAppStore((s) => s.thinking);
  const connected = useAppStore((s) => s.connected);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, thinking]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || !connected) return;
    useAppStore.getState().addMessage({ role: 'user', content: text });
    onSendMessage(text);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-900 border-l border-gray-800">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 bg-gray-950">
        <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
        <span className="text-sm font-semibold text-gray-200">Engineering Copilot</span>
        <span className="text-xs text-gray-500 ml-auto">TOWER-AI</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
        {messages.length === 0 && (
          <div className="text-center text-gray-600 text-sm mt-8">
            <div className="text-4xl mb-3">🗼</div>
            <div className="font-medium text-gray-400 mb-1">Tower Engineering AI</div>
            <div className="text-xs mb-4">Ask me to create towers, run analysis, or manage equipment</div>
            <div className="grid grid-cols-1 gap-2 text-left">
              {EXAMPLE_PROMPTS.slice(0, 4).map((p) => (
                <button
                  key={p}
                  onClick={() => { setInput(p); }}
                  className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg px-3 py-2 text-left transition-colors"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {thinking && <ThinkingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Quick prompts */}
      <div className="px-3 py-2 border-t border-gray-800 flex gap-2 overflow-x-auto">
        {EXAMPLE_PROMPTS.slice(4).map((p) => (
          <button
            key={p}
            onClick={() => setInput(p)}
            className="text-xs whitespace-nowrap bg-gray-800 hover:bg-gray-700 text-gray-400 rounded px-2 py-1 transition-colors flex-shrink-0"
          >
            {p}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="px-3 pb-3">
        <div className="flex gap-2 bg-gray-800 rounded-xl border border-gray-700 focus-within:border-blue-500 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={connected ? 'Ask TOWER-AI anything...' : 'Connecting...'}
            disabled={!connected}
            rows={2}
            className="flex-1 bg-transparent text-gray-100 text-sm px-3 pt-3 pb-2 resize-none outline-none placeholder-gray-600"
          />
          <button
            onClick={handleSend}
            disabled={!connected || !input.trim()}
            className="self-end mb-2 mr-2 px-3 py-2 bg-blue-600 disabled:bg-gray-700 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
