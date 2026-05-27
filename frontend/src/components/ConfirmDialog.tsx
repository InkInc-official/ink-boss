interface Props {
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({ title, message, onConfirm, onCancel }: Props) {
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center" style={{ zIndex: 2147483647 }}>
      <div className="bg-[#111118] border border-white/10 rounded-2xl w-80 p-6 space-y-5 shadow-2xl">
        <div className="space-y-1.5">
          <h3 className="text-white font-display text-lg tracking-[0.1em]">{title}</h3>
          <p className="text-sm text-white/45 leading-relaxed">{message}</p>
        </div>
        <div className="flex gap-3">
          <button onClick={onCancel}
            className="flex-1 py-2.5 rounded-xl border border-white/10 text-white/40 hover:text-white/70 hover:bg-white/5 text-sm transition-all">
            キャンセル
          </button>
          <button onClick={onConfirm}
            className="flex-1 py-2.5 rounded-xl border border-white/25 text-white/80 hover:bg-white/10 hover:text-white text-sm transition-all">
            削除する
          </button>
        </div>
      </div>
    </div>
  );
}
