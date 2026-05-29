import { useState, useRef, useEffect } from "react";
import { useAppStore } from "../store";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function InkAide({ open, onClose }: Props) {
  const { activeServiceId, hibernatedIds } = useAppStore();
  const isHibernated = activeServiceId ? hibernatedIds.has(activeServiceId) : false;
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [currentBackend, setCurrentBackend] = useState<string>("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!open) { setIsReady(false); return; }
    // pywebviewのAPI初期化を待ってから取得
    const timer = setTimeout(async () => {
      try {
        const config = await window.pywebview?.api?.get_config?.();
        if (!config) return;
        const llm = config?.llm || {};
        const backend = llm.backend || "ollama";
        if (backend === "claude") {
          setCurrentBackend("Claude");
          if (llm.claudeApiKey) { setIsReady(true); }
        } else if (backend === "gemini") {
          setCurrentBackend("Gemini");
          if (llm.geminiApiKey) { setIsReady(true); }
        } else {
          const model = llm.ollamaModel || "llama3";
          setCurrentBackend(model);
          try {
            const res = await fetch(`${llm.ollamaUrl || "http://localhost:11434"}/api/tags`, { signal: AbortSignal.timeout(2000) });
            if (res.ok) { setIsReady(true); }
          } catch {}
        }
      } catch {}
    }, 500);
    return () => clearTimeout(timer);
  }, [open]);

  const sendMessage = async (prompt: string) => {
    if (!prompt.trim() || loading) return;

    // 吹き出し表示用：__KNOWLEDGE__プレースホルダーを除去して表示
    const displayPrompt = prompt.replace("__KNOWLEDGE__", "").trim();
    setMessages(prev => [...prev, { role: "user" as const, content: displayPrompt }]);
    setInput("");
    setLoading(true);

    try {
      const config = await window.pywebview?.api?.get_config?.();
      const llm = config?.llm || {};
      const knowledge = config?.knowledge || "";
      const backend = llm.backend || "ollama";

      let pageText = "";
      if (activeServiceId && !isHibernated) {
        try {
          const t = await window.pywebview?.api?.get_page_text?.(activeServiceId);
          if (typeof t === "string" && t.trim().length > 10) pageText = t;
        } catch {}
      }

      // __KNOWLEDGE__をナレッジ内容に置換（AIへ送るプロンプト）
      const resolvedPrompt = prompt.includes("__KNOWLEDGE__")
        ? prompt.replace("__KNOWLEDGE__", knowledge ? `私は${knowledge}。\n\n` : "")
        : prompt;
      const fullPrompt = pageText
        ? `ページ内容：\n${pageText.slice(0, 3000)}\n\n${resolvedPrompt}`
        : resolvedPrompt;

      let reply = "";

      if (backend === "claude" && llm.claudeApiKey) {
        const res = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-api-key": llm.claudeApiKey, "anthropic-version": "2023-06-01" },
          body: JSON.stringify({ model: "claude-sonnet-4-20250514", max_tokens: 1000, messages: [{ role: "user", content: fullPrompt }] })
        });
        const data = await res.json();
        reply = data.content?.[0]?.text || "応答できませんでした";
      } else if (backend === "gemini" && llm.geminiApiKey) {
        const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=${llm.geminiApiKey}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ contents: [{ parts: [{ text: fullPrompt }] }] })
        });
        const data = await res.json();
        reply = data.candidates?.[0]?.content?.parts?.[0]?.text || "応答できませんでした";
      } else if (backend === "ollama") {
        const ollamaUrl = llm.ollamaUrl || "http://localhost:11434";
        const model = llm.ollamaModel || "llama3";
        const res = await fetch(`${ollamaUrl}/api/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model, prompt: fullPrompt, stream: false })
        });
        const data = await res.json();
        reply = data.response || "応答できませんでした";
      } else {
        reply = "APIキーが設定されていません。設定画面で入力してください。";
      }

      setMessages(prev => [...prev, { role: "assistant", content: reply }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: "assistant", content: `エラー: ${e}` }]);
    } finally {
      setLoading(false);
    }
  };

  const quickActions = [
    { label: "要約", prompt: "このページの内容を日本語で簡潔に要約してください。" },
    { label: "ポイント", prompt: "このページの重要なポイントを日本語で箇条書きにしてください。" },
    { label: "感想", prompt: "__KNOWLEDGE__このページの内容について、私の立場から見た活用方法や感想を日本語で教えてください。" },
  ];

  if (!open) return null;

  return (
    <div className="w-80 flex flex-col flex-shrink-0 bg-[#0a0a12] border-l border-white/10 overflow-hidden">
      {/* ヘッダー */}
      <div className="flex flex-col px-4 pt-3 pb-2.5 border-b border-white/5 flex-shrink-0 gap-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white/40">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <span className="text-white/45 text-[11px] font-mono tracking-[0.18em] uppercase">Ink Aide</span>
          </div>
          <div className="flex items-center gap-2.5">
            <button onClick={() => { setMessages([]); setLoading(false); }} className="text-white/20 hover:text-white/50 text-[11px] transition-colors">クリア</button>
            <button onClick={onClose} className="text-white/20 hover:text-white/60 transition-colors text-sm leading-none">✕</button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {currentBackend && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full font-mono border text-sky-400/60 border-sky-400/20">
              {currentBackend}
            </span>
          )}
          {isReady && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full font-mono border text-green-400/70 border-green-400/20">
              ✓ Aide OK
            </span>
          )}
        </div>
      </div>

      {/* クイックボタン */}
      <div className="flex gap-1.5 px-3 py-2.5 border-b border-white/5 flex-shrink-0">
        {quickActions.map((a) => (
          <button key={a.label} onClick={() => sendMessage(a.prompt)} disabled={loading}
            className="flex-1 py-1.5 rounded-lg border border-white/10 text-white/35 text-[11px] hover:border-white/20 hover:text-white/65 hover:bg-white/5 transition-all disabled:opacity-30">
            {a.label}
          </button>
        ))}
      </div>

      {/* メッセージエリア */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center py-8">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" className="text-white/15 mb-3">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <p className="text-white/20 text-xs leading-relaxed">クイックボタンか入力欄から<br />AIに質問できます</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[88%] rounded-2xl px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap ${
              msg.role === "user" ? "bg-white/10 text-white/80 rounded-br-sm" : "bg-white/4 border border-white/8 text-white/65 rounded-bl-sm"
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white/4 border border-white/8 rounded-2xl rounded-bl-sm px-3 py-2.5">
              <div className="flex gap-1 items-center">
                <div className="w-1.5 h-1.5 bg-white/25 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-1.5 h-1.5 bg-white/25 rounded-full animate-bounce" style={{ animationDelay: "120ms" }} />
                <div className="w-1.5 h-1.5 bg-white/25 rounded-full animate-bounce" style={{ animationDelay: "240ms" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 入力欄 */}
      <div className="px-3 py-3 border-t border-white/5 flex-shrink-0">
        <div className="relative flex items-center">
          <input type="text" value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
            placeholder="Aideに聞く..." disabled={loading}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 pr-10 text-xs text-white placeholder-white/20 focus:outline-none focus:border-white/20 transition-colors disabled:opacity-50"
          />
          <button onClick={() => sendMessage(input)} disabled={loading || !input.trim()}
            className="absolute right-2.5 text-white/25 hover:text-white/65 transition-colors disabled:opacity-30">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
