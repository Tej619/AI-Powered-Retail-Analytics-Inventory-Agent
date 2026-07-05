import { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import { chatWithAgent } from '../api/services';

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hello! I am your Retail AI Agent. I can check inventory, generate forecasts, analyze trends, and extract data from pasted reports. How can I help you today?' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      const res = await chatWithAgent(userMessage, 'frontend-user-1');
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: res.data.response,
        tools: res.data.tools_used 
      }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error connecting to the AI agent. Ensure the backend is running.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-0px)] p-4 md:p-8">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white">AI Agent Interface</h2>
        <p className="text-gray-500 mt-1">Ask anything about your inventory, sales, or forecasts.</p>
      </div>

      <div className="flex-1 overflow-y-auto bg-gray-900 border border-gray-800 rounded-xl p-4 mb-4 chat-scroll space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
                <Bot size={18} />
              </div>
            )}
            <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-200'
            }`}>
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.tools && msg.tools.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-700 text-xs text-gray-400">
                  Tools used: {msg.tools.join(', ')}
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center flex-shrink-0">
                <User size={18} />
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
              <Loader2 size={18} className="animate-spin" />
            </div>
            <div className="bg-gray-800 rounded-2xl px-4 py-3 text-sm text-gray-400 animate-pulse">
              Agent is thinking and querying data...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-3 bg-gray-900 border border-gray-800 rounded-xl p-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="e.g. 'Which items need reordering?' or 'Generate a 30-day forecast for PROD-1000'"
          className="flex-1 bg-transparent outline-none text-white placeholder-gray-500 px-2"
          disabled={isLoading}
        />
        <button
          onClick={handleSend}
          disabled={isLoading}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white p-2.5 rounded-lg transition-colors"
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
}