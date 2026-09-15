export type ServiceEngine = "qt" | "electron";

export interface Service {
  id: string;
  name: string;
  url: string;
  icon?: string;
  muted: boolean;
  groupId?: string;
  /** 未指定時は "qt"（後方互換） */
  engine?: ServiceEngine;
}

export interface Group {
  id: string;
  name: string;
  collapsed: boolean;
}

export type LLMBackend = "ollama" | "claude" | "gemini";

export interface LLMConfig {
  backend: LLMBackend;
  ollamaUrl: string;
  ollamaModel: string;
  claudeApiKey: string;
  geminiApiKey: string;
}

export interface AppConfig {
  version: string;
  theme: "dark" | "light";
  hibernateMinutes: number;
  llm: LLMConfig;
  services: Service[];
  groups: Group[];
}

declare global {
  interface Window {
    pywebview: {
      api: {
        add_service: (
          name: string,
          url: string,
          groupId?: string,
          engine?: ServiceEngine,
        ) => Promise<Service>;
        update_service: (id: string, updates: Partial<Service>) => Promise<void>;
        remove_service: (id: string) => Promise<void>;
        move_service: (id: string, groupId: string) => Promise<void>;
        copy_service: (id: string, groupId: string) => Promise<Service>;
        add_group: (name: string) => Promise<Group>;
        update_group: (id: string, name: string) => Promise<void>;
        remove_group: (id: string, deleteServices: boolean) => Promise<void>;
        get_config: () => Promise<AppConfig>;
        export_config: () => Promise<string>;
        import_config: (json: string) => Promise<void>;
        update_llm_config: (config: Partial<LLMConfig>) => Promise<void>;
        update_hibernate_minutes: (minutes: number) => Promise<void>;
        show_service: (id: string) => Promise<void>;
        hide_service?: () => Promise<void>;
        reload_service: (id: string) => Promise<void>;
        hibernate_service: (id: string) => Promise<void>;
        wake_service: (id: string) => Promise<void>;
        get_hibernated_ids: () => Promise<string[]>;
        reorder_groups?: (ids: string[]) => Promise<void>;
        reorder_services?: (ids: string[]) => Promise<void>;
        show_context_menu?: (
          id: string,
          name: string,
          x: number,
          y: number,
          isHib: boolean,
          groupsJson: string,
        ) => Promise<void>;
        show_group_context_menu?: (
          id: string,
          name: string,
          x: number,
          y: number,
        ) => Promise<void>;
        show_add_service_dialog?: (groupId?: string) => Promise<void>;
        show_add_group_dialog?: () => Promise<void>;
        show_settings_dialog?: () => Promise<void>;
        close_window?: () => Promise<void>;
        minimize_window?: () => Promise<void>;
        toggle_maximize?: () => Promise<void>;
        update_title?: (title: string) => Promise<void>;
        set_aide_width?: (width: number) => Promise<void>;
        drag_start?: () => Promise<void>;
        drag_end?: () => Promise<void>;
        sync_geometry?: (id: string) => Promise<void>;
        get_page_text?: (id: string) => Promise<string>;
      };
    };
    __inkBossActiveId: string | null;
  }
}

export {};
