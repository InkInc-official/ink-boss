import { useState, useEffect } from "react";
import { useAppStore } from "../store";
import type { Service } from "../types";
import ConfirmDialog from "./ConfirmDialog";
import inkBossIcon from "../assets/icon.png";

import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
  DragOverEvent,
  DragStartEvent,
  DragOverlay,
  UniqueIdentifier,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

// ── SortableServiceItem ───────────────────────────────────
interface SortableServiceItemProps {
  service: Service;
  expanded: boolean;
  isActive: boolean;
  isHibernated: boolean;
  isWaking: boolean;
  groups: { id: string; name: string }[];
  onServiceClick: (service: Service) => void;
  onServiceDoubleClick: (service: Service) => void;
}

function SortableServiceItem({
  service, expanded, isActive, isHibernated, isWaking,
  groups, onServiceClick, onServiceDoubleClick,
}: SortableServiceItemProps) {
  const {
    attributes, listeners, setNodeRef,
    transform, transition, isDragging,
  } = useSortable({ id: service.id, data: { type: "service", service } });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.3 : 1,
  };

  const getFavicon = (url: string) => {
    try { const u = new URL(url); return `https://www.google.com/s2/favicons?domain=${u.hostname}&sz=32`; }
    catch { return null; }
  };
  const favicon = service.icon || getFavicon(service.url);

  return (
    <button
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => { if (!isDragging) onServiceClick(service); }}
      onDoubleClick={() => onServiceDoubleClick(service)}
      onContextMenu={(e) => {
        e.preventDefault();
        const otherGroups = groups.filter((g) => g.id !== service.groupId);
        const groupsJson  = JSON.stringify(otherGroups.map((g) => ({ id: g.id, name: g.name })));
        window.pywebview?.api?.show_context_menu(
          service.id, service.name, e.clientX, e.clientY, isHibernated, groupsJson
        );
      }}
      className={[
        "group relative flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl transition-all duration-150 select-none",
        isHibernated ? "cursor-not-allowed opacity-40" : "cursor-grab",
        isActive ? "bg-white/10 border border-white/15" : "hover:bg-white/5 border border-transparent",
      ].join(" ")}
      title={!expanded ? (isHibernated ? `${service.name}（ダブルクリックで復帰）` : service.name) : undefined}
    >
      {isActive && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-5 bg-white/60 rounded-r-full" />}
      <div className="flex-shrink-0 w-7 h-7 rounded-lg overflow-hidden flex items-center justify-center bg-white/5 relative">
        {favicon
          ? <img src={favicon} alt="" className="w-5 h-5 object-contain" style={{ filter: "grayscale(100%) brightness(1.2)" }} />
          : <span className="text-white/50 text-xs font-bold">{service.name[0]?.toUpperCase()}</span>}
        {isHibernated && !isWaking && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg">
            <span className="text-white/70 text-[10px]">Z</span>
          </div>
        )}
        {isWaking && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg">
            <div className="w-3 h-3 border border-white/40 border-t-white/80 rounded-full animate-spin" />
          </div>
        )}
      </div>
      {expanded && (
        <span className={`text-sm truncate transition-colors ${isActive ? "text-white font-medium" : "text-white/50 group-hover:text-white/80"}`}>
          {service.name}
          {isHibernated && !isWaking && <span className="ml-1 text-[10px] text-white/30">休止</span>}
        </span>
      )}
    </button>
  );
}

// ── SortableGroupHeader ───────────────────────────────────
function SortableGroupHeader({
  group, expanded, onToggle, isDragOver,
}: {
  group: { id: string; name: string; collapsed?: boolean };
  expanded: boolean;
  onToggle: () => void;
  isDragOver?: boolean;
}) {
  const {
    attributes, listeners, setNodeRef,
    transform, transition, isDragging,
  } = useSortable({ id: `group:${group.id}`, data: { type: "group", group } });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.3 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={[
        "flex items-center gap-1.5 px-2 py-1 mb-0.5 select-none rounded-lg transition-colors",
        isDragOver ? "bg-white/10 border border-white/20" : "",
      ].join(" ")}
      onContextMenu={(e) => {
        e.preventDefault();
        window.pywebview?.api?.show_group_context_menu?.(group.id, group.name, e.clientX, e.clientY);
      }}
    >
      <button
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        className="text-white/20 hover:text-white/50 transition-colors text-[10px] w-3 h-3 flex items-center justify-center flex-shrink-0"
      >
        {group.collapsed ? "▶" : "▼"}
      </button>
      {expanded && (
        <span
          {...attributes}
          {...listeners}
          className="flex-1 text-[10px] font-mono uppercase tracking-[0.15em] text-white/25 truncate cursor-grab"
        >
          {group.name}
        </span>
      )}
    </div>
  );
}

// ── DragOverlay用 サービスプレビュー ─────────────────────
function ServiceDragPreview({ service, expanded }: { service: Service; expanded: boolean }) {
  const getFavicon = (url: string) => {
    try { const u = new URL(url); return `https://www.google.com/s2/favicons?domain=${u.hostname}&sz=32`; }
    catch { return null; }
  };
  const favicon = service.icon || getFavicon(service.url);
  return (
    <div className="flex items-center gap-2.5 px-2.5 py-2 rounded-xl bg-white/15 border border-white/20 shadow-2xl backdrop-blur-sm select-none">
      <div className="flex-shrink-0 w-7 h-7 rounded-lg overflow-hidden flex items-center justify-center bg-white/10">
        {favicon
          ? <img src={favicon} alt="" className="w-5 h-5 object-contain" style={{ filter: "grayscale(100%) brightness(1.2)" }} />
          : <span className="text-white/50 text-xs font-bold">{service.name[0]?.toUpperCase()}</span>}
      </div>
      {expanded && <span className="text-sm text-white/80 font-medium">{service.name}</span>}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────
export default function Sidebar() {
  const {
    services, groups, activeServiceId, hibernatedIds, wakingIds,
    setActiveService, toggleGroupCollapsed,
    removeService, removeGroup, setHibernated, setWaking,
  } = useAppStore();

  const [expanded, setExpanded]             = useState(true);
  const [confirmDeleteGroupId, setConfirmDeleteGroupId] = useState<string | null>(null);
  const [activeId, setActiveId]             = useState<UniqueIdentifier | null>(null);
  const [overGroupId, setOverGroupId]       = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  useEffect(() => {
    const onHibernated  = (e: CustomEvent) => setHibernated(e.detail, true);
    const onWoke        = (e: CustomEvent) => setHibernated(e.detail, false);
    const onRemoved     = (e: CustomEvent) => useAppStore.getState()._removeServiceFromStore(e.detail);
    const onRenamed     = (e: CustomEvent) => {
      const { id, name } = e.detail;
      useAppStore.setState((s) => ({ services: s.services.map((sv) => sv.id === id ? { ...sv, name } : sv) }));
    };
    const onAdded = (e: CustomEvent) => {
      const svc = e.detail;
      useAppStore.setState((s) => ({
        services: [...s.services, svc],
        hibernatedIds: new Set([...s.hibernatedIds, svc.id]),
      }));
    };
    const onGroupAdded   = (e: CustomEvent) => useAppStore.setState((s) => ({ groups: [...s.groups, e.detail] }));
    const onGroupRemoved = (e: CustomEvent) => useAppStore.setState((s) => ({
      groups: s.groups.filter((g) => g.id !== e.detail),
      services: s.services.map((sv) => sv.groupId === e.detail ? { ...sv, groupId: undefined } : sv),
    }));
    const onHibChanged   = (e: CustomEvent) => useAppStore.setState((s) => ({ config: { ...s.config, hibernateMinutes: e.detail } }));
    const onGroupRenamed = (e: CustomEvent) => {
      const { id, name } = e.detail;
      useAppStore.setState((s) => ({ groups: s.groups.map((g) => g.id === id ? { ...g, name } : g) }));
    };
    window.addEventListener("service-hibernated", onHibernated   as EventListener);
    window.addEventListener("service-woke",        onWoke         as EventListener);
    window.addEventListener("service-removed",     onRemoved      as EventListener);
    window.addEventListener("service-renamed",     onRenamed      as EventListener);
    window.addEventListener("service-added",       onAdded        as EventListener);
    window.addEventListener("group-added",         onGroupAdded   as EventListener);
    window.addEventListener("group-removed",       onGroupRemoved as EventListener);
    window.addEventListener("hibernate-changed",   onHibChanged   as EventListener);
    window.addEventListener("group-renamed",       onGroupRenamed as EventListener);
    return () => {
      window.removeEventListener("service-hibernated", onHibernated   as EventListener);
      window.removeEventListener("service-woke",        onWoke         as EventListener);
      window.removeEventListener("service-removed",     onRemoved      as EventListener);
      window.removeEventListener("service-renamed",     onRenamed      as EventListener);
      window.removeEventListener("service-added",       onAdded        as EventListener);
      window.removeEventListener("group-added",         onGroupAdded   as EventListener);
      window.removeEventListener("group-removed",       onGroupRemoved as EventListener);
      window.removeEventListener("hibernate-changed",   onHibChanged   as EventListener);
      window.removeEventListener("group-renamed",       onGroupRenamed as EventListener);
    };
  }, [setHibernated, removeService]);

  const handleServiceClick = async (service: Service) => {
    // dblclickでもclickが発火するため、休止中はclickを無視（dblclickのみ処理）
    if (hibernatedIds.has(service.id)) return;
    if (wakingIds.has(service.id)) return;
    // すでにアクティブなら再クリックしても何もしない
    if (activeServiceId === service.id) return;
    setActiveService(service.id);
    await window.pywebview?.api?.show_service(service.id);
  };

  const handleServiceDoubleClick = async (service: Service) => {
    if (wakingIds.has(service.id)) return;
    // 休止中のみdblclickで復帰
    if (hibernatedIds.has(service.id)) {
      setWaking(service.id, true);
      setActiveService(service.id);
      await window.pywebview?.api?.show_service(service.id);
    }
    // 非休止中はclickで処理済みのため何もしない
  };

  // ── DnD ハンドラー ────────────────────────────────────
  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id);
  };

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      setOverGroupId(null);
      return;
    }

    const activeData = active.data.current;
    const overData   = over.data.current;

    if (!activeData || activeData.type !== "service") {
      setOverGroupId(null);
      return;
    }

    const activeService = activeData.service as Service;

    // ── ケース①: サービス → 別サービスの上 ──────────────
    if (overData?.type === "service") {
      setOverGroupId(null);
      const overService = overData.service as Service;
      const newGroupId  = overService.groupId;

      useAppStore.setState((s) => {
        const list = [...s.services];
        const srcIdx = list.findIndex((sv) => sv.id === activeService.id);
        const tgtIdx = list.findIndex((sv) => sv.id === overService.id);
        if (srcIdx === -1 || tgtIdx === -1 || srcIdx === tgtIdx) return {};

        // 1. srcを取り出してgroupIdを書き換え
        const moving = { ...list[srcIdx], groupId: newGroupId };
        // 2. srcを除いたリストを作る
        const without = list.filter((_, i) => i !== srcIdx);
        // 3. tgtの現在位置を再計算（srcを除いた後の位置）
        const newTgt = without.findIndex((sv) => sv.id === overService.id);
        // 4. tgtの位置に挿入
        without.splice(newTgt, 0, moving);
        return { services: without };
      });
      return;
    }

    // ── ケース②: サービス → グループヘッダーの上 ─────────
    if (overData?.type === "group") {
      const targetGroupId = overData.group.id as string;
      setOverGroupId(targetGroupId);
      if (activeService.groupId === targetGroupId) return;

      useAppStore.setState((s) => {
        const list = [...s.services];
        const srcIdx = list.findIndex((sv) => sv.id === activeService.id);
        if (srcIdx === -1) return {};

        const moving = { ...list[srcIdx], groupId: targetGroupId };
        const without = list.filter((_, i) => i !== srcIdx);
        const firstInGroup = without.findIndex((sv) => sv.groupId === targetGroupId);
        if (firstInGroup !== -1) {
          without.splice(firstInGroup, 0, moving);
        } else {
          without.push(moving);
        }
        return { services: without };
      });
      return;
    }

    // ── ケース③: サービス → グループなし領域（ungrouped SortableContext）──
    // over.id がサービスIDでもグループIDでもない = ungrouped領域のプレースホルダー
    // over.id === "ungrouped-droppable" のような専用IDを使う場合はここに追加可能
    // 現状は overData がない場合もグループ解除として扱う
    if (!overData) {
      if (activeService.groupId === undefined || activeService.groupId === null) return;
      useAppStore.setState((s) => {
        const list   = [...s.services];
        const srcIdx = list.findIndex((sv) => sv.id === activeService.id);
        if (srcIdx === -1) return {};
        const updated = [...list];
        updated[srcIdx] = { ...updated[srcIdx], groupId: undefined };
        return { services: updated };
      });
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    setOverGroupId(null);

    if (!over || active.id === over.id) return;

    const activeData = active.data.current;
    const overData   = over.data.current;

    // ── グループヘッダーの並び替え ──────────────────────
    if (activeData?.type === "group" && overData?.type === "group") {
      useAppStore.setState((s) => {
        const gs   = [...s.groups];
        const from = gs.findIndex((g) => g.id === activeData.group.id);
        const to   = gs.findIndex((g) => g.id === overData.group.id);
        if (from === -1 || to === -1) return {};
        return { groups: arrayMove(gs, from, to) };
      });
      await window.pywebview?.api?.reorder_groups?.(
        useAppStore.getState().groups.map((g) => g.id)
      );
      return;
    }

    // ── サービスの確定保存（1フレーム待ってDragOverのsetStateが確定してから保存）──
    if (activeData?.type === "service") {
      // DragOverのsetStateが反映されるまで1フレーム待つ
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      const currentServices = useAppStore.getState().services;
      const movedService = currentServices.find((sv: Service) => sv.id === active.id);
      if (movedService) {
        await window.pywebview?.api?.update_service?.(movedService.id, {
          groupId: movedService.groupId ?? null,
        });
        await window.pywebview?.api?.save_service_order?.(
          currentServices.map((sv: Service) => sv.id)
        );
      }
    }
  };

  // ドラッグ中のサービスを取得（DragOverlay用）
  const activeService = activeId
    ? services.find((s) => s.id === activeId)
    : null;

  const ungrouped = services.filter((s) => !s.groupId);
  const confirmDeleteGroup = groups.find((g) => g.id === confirmDeleteGroupId);

  // グループ並び替え用ID（group:xxx形式）
  const groupSortableIds = groups.map((g) => `group:${g.id}`);

  // ── IMPORTANT: DndContext を最外層（<> 直下）に置く ──────
  // DragOverlay は DndContext の子でなければならないが、
  // <aside> の外（DOM的にポータル）に描画される。
  const [sidebarIconError, setSidebarIconError] = useState(false);

  // DndContext を <aside> の外に出すことで：
  //   1. DragOverlay が aside の clip/overflow に切り取られない
  //   2. React #185エラー（ポータルのツリー不整合）を回避
  //   3. グループをまたぐ DragOver イベントが正常に伝播する
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <aside className={`flex flex-col h-full transition-all duration-200 bg-[#0a0a12] border-r border-white/5 ${expanded ? "w-52" : "w-[52px]"}`}>
        {/* ヘッダー */}
        <div className="flex items-center h-14 px-3 border-b border-white/5 cursor-pointer flex-shrink-0 gap-3" onClick={() => setExpanded(!expanded)}>
          <div className="flex-shrink-0 w-7 h-7 flex items-center justify-center overflow-hidden">
            {sidebarIconError ? (
              <span className="text-white/40 font-display text-xs tracking-wider">IB</span>
            ) : (
              <img src={inkBossIcon} alt="IB" className="w-7 h-7 object-cover rounded-lg"
                style={{ filter: "grayscale(100%) brightness(1.4)" }}
                onError={() => setSidebarIconError(true)} />
            )}
          </div>
          {expanded && <span className="text-white font-display text-lg tracking-[0.2em] leading-none">INK BOSS</span>}
        </div>

        {/* サービス一覧 */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-1.5 py-3 space-y-0.5 scrollbar-thin">
          {/* グループ（ヘッダー＋サービス） */}
          <SortableContext items={groupSortableIds} strategy={verticalListSortingStrategy}>
            {groups.map((group) => {
              const groupServices = services.filter((s) => s.groupId === group.id);
              return (
                <div key={group.id}>
                  <SortableGroupHeader
                    group={group}
                    expanded={expanded}
                    onToggle={() => toggleGroupCollapsed(group.id)}
                    isDragOver={overGroupId === group.id}
                  />
                  {/* グループ内サービス */}
                  {!group.collapsed && (
                    <SortableContext
                      items={groupServices.map((s) => s.id)}
                      strategy={verticalListSortingStrategy}
                    >
                      <div className="pl-2">
                        {groupServices.map((s) => (
                          <SortableServiceItem
                            key={s.id}
                            service={s}
                            expanded={expanded}
                            isActive={activeServiceId === s.id}
                            isHibernated={hibernatedIds.has(s.id)}
                            isWaking={wakingIds.has(s.id)}
                            groups={groups}
                            onServiceClick={handleServiceClick}
                            onServiceDoubleClick={handleServiceDoubleClick}
                          />
                        ))}
                      </div>
                    </SortableContext>
                  )}
                </div>
              );
            })}
          </SortableContext>

          {/* グループなしサービス */}
          <SortableContext items={ungrouped.map((s) => s.id)} strategy={verticalListSortingStrategy}>
            {ungrouped.map((s) => (
              <SortableServiceItem
                key={s.id}
                service={s}
                expanded={expanded}
                isActive={activeServiceId === s.id}
                isHibernated={hibernatedIds.has(s.id)}
                isWaking={wakingIds.has(s.id)}
                groups={groups}
                onServiceClick={handleServiceClick}
                onServiceDoubleClick={handleServiceDoubleClick}
              />
            ))}
          </SortableContext>
        </nav>

        <div className="h-px bg-white/5 mx-3" />

        {/* ボトムメニュー: 下から「設定」「グループ追加」「サービス追加」 */}
        <div className="flex-shrink-0 px-1.5 py-2 space-y-0.5">
          {/* サービス追加（一番上） */}
          <button onClick={() => window.pywebview?.api?.show_add_service_dialog()}
            className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl text-white/40 hover:text-white/80 hover:bg-white/5 transition-all"
            title={!expanded ? "サービスを追加" : undefined}>
            <span className="flex-shrink-0 w-7 h-7 flex items-center justify-center text-lg leading-none font-light">+</span>
            {expanded && <span className="text-sm">サービス追加</span>}
          </button>
          {/* グループ追加（真ん中） */}
          <button onClick={() => window.pywebview?.api?.show_add_group_dialog()}
            className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl text-white/40 hover:text-white/80 hover:bg-white/5 transition-all"
            title={!expanded ? "グループを追加" : undefined}>
            <span className="flex-shrink-0 w-7 h-7 flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3H8a2 2 0 0 0-2 2v2h12V5a2 2 0 0 0-2-2z"/><line x1="12" y1="12" x2="12" y2="17"/><line x1="9.5" y1="14.5" x2="14.5" y2="14.5"/>
              </svg>
            </span>
            {expanded && <span className="text-sm">グループ追加</span>}
          </button>
          {/* 設定（一番下） */}
          <button onClick={() => window.pywebview?.api?.show_settings_dialog()}
            className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-xl text-white/40 hover:text-white/80 hover:bg-white/5 transition-all"
            title={!expanded ? "設定" : undefined}>
            <span className="flex-shrink-0 w-7 h-7 flex items-center justify-center">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </span>
            {expanded && <span className="text-sm">設定</span>}
          </button>
        </div>
      </aside>

      {/* DragOverlay: DndContext内・asideの外でポータルとして描画 */}
      <DragOverlay dropAnimation={null}>
        {activeService ? (
          <ServiceDragPreview service={activeService} expanded={expanded} />
        ) : null}
      </DragOverlay>

      {confirmDeleteGroupId && confirmDeleteGroup && (
        <ConfirmDialog
          title="グループを削除"
          message={`「${confirmDeleteGroup.name}」を削除しますか？\nサービスはグループ解除されます。`}
          onConfirm={() => {
            removeGroup(confirmDeleteGroupId, false);
            window.pywebview?.api?.remove_group?.(confirmDeleteGroupId);
            setConfirmDeleteGroupId(null);
          }}
          onCancel={() => setConfirmDeleteGroupId(null)}
        />
      )}
    </DndContext>
  );
}
