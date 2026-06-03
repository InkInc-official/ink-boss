import { useState, useEffect } from "react";
import { useAppStore } from "../store";
import type { LLMBackend } from "../types";

interface Props { onClose: () => void; }

export default function SettingsModal({ onClose }: Props) {
  const { config, updateLLMConfig, updateHibernateMinutes, exportConfig, importConfig } = useAppStore();
  // グループタブを削除: "general" | "llm" | "data" の3タブのみ
  const [tab, setTab]               = useState<"general" | "llm" | "data">("general");
  const [importText, setImportText] = useState("");
  const [knowledge, setKnowledge]   = useState<string>(config.knowledge || "");
  const [ollamaStatus, setOllamaStatus] = useState<string>("");
  // Ollamaから取得したモデル一覧
  const [installedModels, setInstalledModels] = useState<string[]>([]);
  const llm = config.llm;

  const backends: { value: LLMBackend; label: string; desc: string }[] = [
    { value: "ollama", label: "Ollama",      desc: "ローカルLLM・無料・完全オフライン" },
    { value: "claude", label: "Claude API",  desc: "高精度・従量課金・要APIキー" },
    { value: "gemini", label: "Gemini API",  desc: "無料枠あり・取得容易・要APIキー" },
  ];

  const hibernateOptions = [
    { value: 0,  label: "無効"  },
    { value: 5,  label: "5分"   },
    { value: 10, label: "10分"  },
    { value: 15, label: "15分"  },
    { value: 30, label: "30分"  },
    { value: 60, label: "1時間" },
  ];

  // OllamaタブになったときにインストールモデルをAPIから取得
  useEffect(() => {
    if (tab !== "llm" || llm.backend !== "ollama") return;
    const url = llm.ollamaUrl || "http://localhost:11434";
    fetch(`${url}/api/tags`, { signal: AbortSignal.timeout(2000) })
      .then((r) => r.json())
      .then((data) => {
        const names = (data.models || []).map((m: { name: string }) => m.name);
        setInstalledModels(names);
      })
      .catch(() => setInstalledModels([]));
  }, [tab, llm.backend, llm.ollamaUrl]);

  // Ollama pull完了イベントを受け取ってリストを更新
  useEffect(() => {
    const onDone = (e: CustomEvent) => {
      setOllamaStatus(`${e.detail} のダウンロードが完了しました`);
      setInstalledModels((prev) => prev.includes(e.detail) ? prev : [...prev, e.detail]);
    };
    window.addEventListener("ollama-pull-done", onDone as EventListener);
    return () => window.removeEventListener("ollama-pull-done", onDone as EventListener);
  }, []);

  const handleExport = async () => {
    const json = await exportConfig();
    const blob = new Blob([json], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "ink-boss-config.json";
    a.click();
  };

  const handleImport = async () => {
    if (!importText.trim()) return;
    await importConfig(importText);
    setImportText("");
    onClose();
  };

  const inputClass = "w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-white/25 transition-colors font-mono";

  const recommendedModels = [
    { name: "qwen2.5:3b",      desc: "軽量・多言語・推奨" },
    { name: "qwen2.5:7b",      desc: "バランス型" },
    { name: "gemma2:9b",       desc: "高品質・Google製" },
    { name: "llama3.2:latest", desc: "Meta汎用" },
    { name: "mistral:7b",      desc: "高品質・フランス製" },
  ];

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center" style={{ zIndex: 2147483647 }}>
      <div className="bg-[#111118] border border-white/10 rounded-2xl w-[520px] h-[520px] flex flex-col shadow-2xl shadow-black/60 overflow-hidden">

        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 flex-shrink-0">
          <h2 className="font-display text-xl tracking-[0.15em] text-white">設定</h2>
          <button onClick={onClose} className="text-white/30 hover:text-white/70 transition-colors w-6 h-6 flex items-center justify-center rounded-lg hover:bg-white/5 text-lg leading-none">×</button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* サイドナビ: グループタブなし */}
          <nav className="w-36 border-r border-white/5 flex-shrink-0 py-3 space-y-0.5 px-2">
            {(["general", "llm", "data"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`w-full text-left px-3 py-2 rounded-xl text-sm transition-all ${
                  tab === t ? "bg-white/10 text-white border border-white/15" : "text-white/40 hover:text-white/70 hover:bg-white/5"
                }`}>
                {{ general: "一般", llm: "AI / LLM", data: "データ" }[t]}
              </button>
            ))}
          </nav>

          <div className="flex-1 overflow-y-auto p-5 space-y-4">

            {/* ── 一般タブ ── */}
            {tab === "general" && (
              <div className="space-y-5">
                {/* 休止モード */}
                <div className="space-y-2">
                  <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">休止モード</p>
                  <p className="text-xs text-white/30 leading-relaxed">
                    非アクティブなサービスを指定時間後に自動休止してメモリを解放します
                  </p>
                  <div className="grid grid-cols-3 gap-2">
                    {hibernateOptions.map((opt) => (
                      <button key={opt.value}
                        onClick={() => updateHibernateMinutes(opt.value)}
                        className={`py-2 rounded-xl border text-sm transition-all ${
                          config.hibernateMinutes === opt.value
                            ? "border-white/30 bg-white/10 text-white"
                            : "border-white/8 text-white/40 hover:border-white/20 hover:text-white/70"
                        }`}>
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
                {/* コンテキスト */}
                <div className="space-y-2">
                  <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">コンテキスト（自己紹介）</p>
                  <p className="text-xs text-white/30 leading-relaxed">
                    Ink Aideの「感想」ボタンで使用されます。あなたの立場や役割を入力してください。
                  </p>
                  <textarea
                    value={knowledge}
                    onChange={(e) => { if (e.target.value.length <= 200) setKnowledge(e.target.value); }}
                    placeholder="例：ライバー事務所の所長で、精神保健福祉士です。"
                    rows={3}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-xs text-white placeholder-white/20 focus:outline-none focus:border-white/25 transition-colors resize-none"
                  />
                  <div className="flex items-center justify-between">
                    <span className={`text-[10px] font-mono ${knowledge.length >= 200 ? "text-red-400/70" : "text-white/25"}`}>
                      {knowledge.length} / 200
                    </span>
                    <button
                      onClick={async () => { await window.pywebview?.api?.save_knowledge?.(knowledge); }}
                      className="text-[11px] px-3 py-1 rounded-lg border border-white/15 text-white/50 hover:text-white hover:bg-white/5 transition-all"
                    >
                      保存
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* ── AI/LLMタブ ── */}
            {tab === "llm" && (
              <div className="space-y-4">
                {/* バックエンド選択 */}
                <div className="space-y-2">
                  <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">バックエンド</p>
                  {backends.map((b) => (
                    <label key={b.value} className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                      llm.backend === b.value ? "border-white/25 bg-white/5" : "border-white/8 hover:border-white/15"
                    }`}>
                      <input type="radio" name="backend" value={b.value} checked={llm.backend === b.value}
                        onChange={() => updateLLMConfig({ backend: b.value })} className="mt-0.5 accent-white" />
                      <div>
                        <p className="text-sm text-white">{b.label}</p>
                        <p className="text-xs text-white/40 mt-0.5">{b.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>

                {/* Ollama設定 */}
                {llm.backend === "ollama" && (
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">OllamaサーバーURL</label>
                      <input type="text" value={llm.ollamaUrl}
                        onChange={(e) => updateLLMConfig({ ollamaUrl: e.target.value })}
                        className={inputClass} />
                    </div>

                    {/* モデル選択: インストール済みプルダウン優先 */}
                    <div className="space-y-1.5">
                      <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">使用モデル</label>
                      {installedModels.length > 0 ? (
                        <select
                          value={llm.ollamaModel}
                          onChange={(e) => updateLLMConfig({ ollamaModel: e.target.value })}
                          style={{ background: "#1a1a2e", color: "white" }}
                          className="w-full border border-white/10 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-white/25 transition-colors"
                        >
                          {installedModels.map((m) => (
                            <option key={m} value={m} style={{ background: "#1a1a2e" }}>{m}</option>
                          ))}
                        </select>
                      ) : (
                        <input type="text" value={llm.ollamaModel}
                          onChange={(e) => updateLLMConfig({ ollamaModel: e.target.value })}
                          placeholder="llama3（Ollamaが起動していればプルダウンで選択可）"
                          className={inputClass} />
                      )}
                    </div>

                    {/* Ollamaインストール */}
                    <div className="space-y-2">
                      <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">Ollamaセットアップ</p>
                      <button
                        onClick={async () => {
                          setOllamaStatus("ブラウザを開いています...");
                          const result = await window.pywebview?.api?.install_ollama?.();
                          setOllamaStatus(result || "完了");
                        }}
                        className="w-full py-2 rounded-xl border border-white/15 text-white/50 text-sm hover:bg-white/5 hover:text-white transition-all"
                      >
                        Ollamaをインストール
                      </button>
                      {ollamaStatus && (
                        <p className="text-[10px] font-mono text-white/40 px-1">{ollamaStatus}</p>
                      )}
                    </div>

                    {/* おすすめモデル */}
                    <div className="space-y-2">
                      <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">おすすめモデル</p>
                      {recommendedModels.map((m) => {
                        const owned = installedModels.some((im) => im.startsWith(m.name.split(":")[0]));
                        return (
                          <div key={m.name} className="flex items-center justify-between px-3 py-2 bg-white/3 rounded-xl border border-white/8">
                            <div>
                              <p className="text-xs font-mono text-white/70">{m.name}</p>
                              <p className="text-[10px] text-white/30">{m.desc}</p>
                            </div>
                            {owned ? (
                              <span className="text-[11px] px-2.5 py-1 rounded-lg border border-green-400/20 text-green-400/60 flex-shrink-0">
                                所持
                              </span>
                            ) : (
                              <button
                                onClick={async () => {
                                  updateLLMConfig({ ollamaModel: m.name });
                                  setOllamaStatus(`${m.name} をDL中...`);
                                  const result = await window.pywebview?.api?.pull_ollama_model?.(m.name);
                                  setOllamaStatus(result || `${m.name} DL開始`);
                                }}
                                className="text-[11px] px-2.5 py-1 rounded-lg border border-white/15 text-white/40 hover:text-white hover:bg-white/5 transition-all flex-shrink-0"
                              >
                                使う
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Claude APIキー */}
                {llm.backend === "claude" && (
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">Claude APIキー</label>
                    <input type="password" value={llm.claudeApiKey}
                      onChange={(e) => updateLLMConfig({ claudeApiKey: e.target.value })}
                      placeholder="sk-ant-..." className={inputClass} />
                  </div>
                )}

                {/* Gemini APIキー */}
                {llm.backend === "gemini" && (
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">Gemini APIキー</label>
                    <input type="password" value={llm.geminiApiKey}
                      onChange={(e) => updateLLMConfig({ geminiApiKey: e.target.value })}
                      placeholder="AIza..." className={inputClass} />
                  </div>
                )}
              </div>
            )}

            {/* ── データタブ ── */}
            {tab === "data" && (
              <div className="space-y-4">
                <button onClick={handleExport}
                  className="w-full py-2.5 rounded-xl border border-white/15 text-white/60 text-sm hover:bg-white/5 hover:text-white transition-all">
                  設定をエクスポート（JSON）
                </button>
                <div className="space-y-2">
                  <p className="text-[11px] font-mono uppercase tracking-[0.15em] text-white/35">設定をインポート</p>
                  <textarea value={importText} onChange={(e) => setImportText(e.target.value)}
                    placeholder="JSONを貼り付け..." rows={5}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3.5 py-2 text-xs font-mono text-white placeholder-white/20 focus:outline-none focus:border-white/25 resize-none transition-colors" />
                  <button onClick={handleImport} disabled={!importText.trim()}
                    className="w-full py-2.5 rounded-xl border border-white/15 text-white/60 text-sm hover:bg-white/5 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                    インポート
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
