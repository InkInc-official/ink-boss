import { useEffect, useRef, useState } from "react";
import type { Service, Group } from "../types";
import ConfirmDialog from "./ConfirmDialog";

interface Props {
  x: number; y: number;
  service: Service; groups: Group[];
  isHibernated: boolean;
  onClose: () => void;
  onMove: (groupId: string) => void;
  onCopy: (groupId: string) => void;
  onHibernate: () => void;
  onWake: () => void;
  onEdit: () => void;
  onDelete: () => void | Promise<void>;
}

export default function ContextMenu({ x, y, service, groups, isHibernated, onClose, onMove, onCopy, onHibernate, onWake, onEdit, onDelete }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (showConfirm) return;
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose, showConfirm]);

  const openConfirm = () => {
    setShowConfirm(true);
  };

  const handleConfirm = async () => {
    setShowConfirm(false);
    await onDelete();
  };

  const handleCancel = () => {
    setShowConfirm(false);
    onClose();
  };

  const otherGroups = groups.filter((g) => g.id !== service.groupId);
  const itemClass = "w-full text-left px-3.5 py-2 text-sm text-white/60 hover:text-white hover:bg-white/5 flex items-center justify-between transition-colors";

  return (
    <>
      <div ref={ref}
        className="fixed bg-[#111118] border border-white/10 rounded-xl shadow-2xl shadow-black/60 py-1.5 min-w-44"
        style={{ left: x, top: y, zIndex: 2147483647 }}>

        {otherGroups.length > 0 && (
          <div className="relative group/move">
            <button className={itemClass}>
              <span>グループに移動</span>
              <span className="text-white/25 text-xs">›</span>
            </button>
            <div className="absolute left-full top-0 bg-[#111118] border border-white/10 rounded-xl shadow-2xl py-1.5 min-w-36 hidden group-hover/move:block" style={{ zIndex: 2147483647 }}>
              {otherGroups.map((g) => (
                <button key={g.id} onClick={() => onMove(g.id)} className={itemClass}>{g.name}</button>
              ))}
            </div>
          </div>
        )}

        {groups.length > 0 && (
          <div className="relative group/copy">
            <button className={itemClass}>
              <span>グループにコピー</span>
              <span className="text-white/25 text-xs">›</span>
            </button>
            <div className="absolute left-full top-0 bg-[#111118] border border-white/10 rounded-xl shadow-2xl py-1.5 min-w-36 hidden group-hover/copy:block" style={{ zIndex: 2147483647 }}>
              {groups.map((g) => (
                <button key={g.id} onClick={() => onCopy(g.id)} className={itemClass}>{g.name}</button>
              ))}
            </div>
          </div>
        )}

        <div className="h-px bg-white/5 my-1 mx-2" />

        {/* 休止 / 復帰 */}
        {isHibernated ? (
          <button onClick={onWake} className={itemClass}>
            <span>復帰</span>
          </button>
        ) : (
          <button onClick={onHibernate} className={itemClass}>
            <span>休止</span>
          </button>
        )}

        <div className="h-px bg-white/5 my-1 mx-2" />

        <button onClick={onEdit}
          className="w-full text-left px-3.5 py-2 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-colors">
          編集
        </button>

        <button onClick={openConfirm}
          className="w-full text-left px-3.5 py-2 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-colors">
          削除
        </button>
      </div>

      {showConfirm && (
        <ConfirmDialog
          title="サービスを削除"
          message={`「${service.name}」を削除しますか？\nログイン情報も削除されます。`}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </>
  );
}
