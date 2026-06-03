import { create } from "zustand";
import type { Service, Group, AppConfig, LLMConfig } from "../types";

const defaultConfig: AppConfig = {
  version: "2.0.0",
  theme: "dark",
  hibernateMinutes: 10,
  llm: {
    backend: "ollama",
    ollamaUrl: "http://localhost:11434",
    ollamaModel: "llama3",
    claudeApiKey: "",
    geminiApiKey: "",
  },
  services: [],
  groups: [],
};

interface AppStore {
  services: Service[];
  groups: Group[];
  activeServiceId: string | null;
  hibernatedIds: Set<string>;
  wakingIds: Set<string>;
  config: AppConfig;
  loaded: boolean;

  loadConfig: () => Promise<void>;
  setActiveService: (id: string | null) => void;
  setHibernated: (id: string, val: boolean) => void;
  setWaking: (id: string, val: boolean) => void;

  addService: (name: string, url: string, groupId?: string) => Promise<void>;
  updateService: (id: string, updates: Partial<Service>) => Promise<void>;
  removeService: (id: string) => Promise<void>;
  _removeServiceFromStore: (id: string) => void;
  moveService: (id: string, groupId: string) => Promise<void>;
  copyService: (id: string, groupId: string) => Promise<void>;
  hibernateService: (id: string) => Promise<void>;
  wakeService: (id: string) => Promise<void>;

  addGroup: (name: string) => Promise<void>;
  updateGroup: (id: string, name: string) => Promise<void>;
  removeGroup: (id: string, deleteServices: boolean) => Promise<void>;
  toggleGroupCollapsed: (id: string) => void;

  updateLLMConfig: (config: Partial<LLMConfig>) => Promise<void>;
  updateHibernateMinutes: (minutes: number) => Promise<void>;
  exportConfig: () => Promise<string>;
  importConfig: (json: string) => Promise<void>;
}

const api = () => window.pywebview?.api;

export const useAppStore = create<AppStore>((set, get) => ({
  services: [],
  groups: [],
  activeServiceId: null,
  hibernatedIds: new Set(),
  wakingIds: new Set(),
  config: defaultConfig,
  loaded: false,

  loadConfig: async () => {
    try {
      const config = await api().get_config();
      const hibernatedIds = await api().get_hibernated_ids();
      // 既存config.jsonのグループがcollapsed:falseのままの場合に備え
      // 起動時は全グループをcollapsed:trueに統一する
      const groups: Group[] = (config.groups ?? []).map((g: Group) => ({ ...g, collapsed: true }));
      set({
        services: config.services ?? [],
        groups,
        hibernatedIds: new Set(hibernatedIds),
        config: { ...defaultConfig, ...config },
        loaded: true,
      });
    } catch {
      set({ loaded: true });
    }
  },

  setActiveService: (id) => set({ activeServiceId: id }),
  setHibernated: (id, val) => set((s) => {
    const next = new Set(s.hibernatedIds);
    val ? next.add(id) : next.delete(id);
    return { hibernatedIds: next };
  }),
  setWaking: (id, val) => set((s) => {
    const next = new Set(s.wakingIds);
    val ? next.add(id) : next.delete(id);
    return { wakingIds: next };
  }),

  addService: async (name, url, groupId) => {
    const service = await api().add_service(name, url, groupId);
    set((s) => ({
      services: [...s.services, service],
      hibernatedIds: new Set([...s.hibernatedIds, service.id]),
    }));
  },

  updateService: async (id, updates) => {
    await api().update_service(id, updates);
    set((s) => ({ services: s.services.map((sv) => sv.id === id ? { ...sv, ...updates } : sv) }));
  },

  removeService: async (id) => {
    // Windows: api.remove_serviceがservice-removedイベントを発火 → このメソッドは呼ばれない
    // Linux/store直接: APIを呼んでからstoreを更新
    await api().remove_service(id);
    set((s) => ({
      services: s.services.filter((sv) => sv.id !== id),
      activeServiceId: s.activeServiceId === id ? null : s.activeServiceId,
    }));
  },

  // store内部のみ更新（APIを呼ばない）。service-removedイベント受信時に使う
  _removeServiceFromStore: (id: string) => {
    set((s) => ({
      services: s.services.filter((sv) => sv.id !== id),
      activeServiceId: s.activeServiceId === id ? null : s.activeServiceId,
    }));
  },

  moveService: async (id, groupId) => {
    await api().move_service(id, groupId);
    set((s) => ({ services: s.services.map((sv) => sv.id === id ? { ...sv, groupId } : sv) }));
  },

  copyService: async (id, groupId) => {
    const newService = await api().copy_service(id, groupId);
    set((s) => ({
      services: [...s.services, newService],
      hibernatedIds: new Set([...s.hibernatedIds, newService.id]),
    }));
  },

  hibernateService: async (id) => {
    await api().hibernate_service(id);
    set((s) => {
      const next = new Set(s.hibernatedIds);
      next.add(id);
      return {
        hibernatedIds: next,
        activeServiceId: s.activeServiceId === id ? null : s.activeServiceId,
      };
    });
  },

  wakeService: async (id) => {
    get().setWaking(id, true);
    await api().wake_service(id);
    set((s) => {
      const next = new Set(s.hibernatedIds);
      next.delete(id);
      const waking = new Set(s.wakingIds);
      waking.delete(id);
      return { hibernatedIds: next, wakingIds: waking };
    });
  },

  addGroup: async (name) => {
    const group = await api().add_group(name);
    set((s) => ({ groups: [...s.groups, group] }));
  },

  updateGroup: async (id, name) => {
    await api().update_group(id, name);
    set((s) => ({ groups: s.groups.map((g) => g.id === id ? { ...g, name } : g) }));
  },

  removeGroup: async (id, deleteServices) => {
    await api().remove_group(id, deleteServices);
    set((s) => ({
      groups: s.groups.filter((g) => g.id !== id),
      services: deleteServices
        ? s.services.filter((sv) => sv.groupId !== id)
        : s.services.map((sv) => sv.groupId === id ? { ...sv, groupId: undefined } : sv),
    }));
  },

  toggleGroupCollapsed: (id) => {
    // setで更新してから新しい値を取得
    set((s) => ({ groups: s.groups.map((g) => g.id === id ? { ...g, collapsed: !g.collapsed } : g) }));
    const newCollapsed = get().groups.find((g) => g.id === id)?.collapsed ?? false;
    api()?.update_group_collapsed?.(id, newCollapsed);
  },

  updateLLMConfig: async (llmUpdates) => {
    await api().update_llm_config(llmUpdates);
    set((s) => ({ config: { ...s.config, llm: { ...s.config.llm, ...llmUpdates } } }));
  },

  updateHibernateMinutes: async (minutes) => {
    await api().update_hibernate_minutes(minutes);
    set((s) => ({ config: { ...s.config, hibernateMinutes: minutes } }));
  },

  exportConfig: async () => await api().export_config(),

  importConfig: async (json) => {
    await api().import_config(json);
    await get().loadConfig();
  },
}));
