export interface Service {
  id: string;
  name: string;
  url: string;
  icon?: string;
  muted: boolean;
  groupId?: string;
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
        add_service: (name: string, url: string, groupId?: string) => Promise<Service>;
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
        reload_service: (id: string) => Promise<void>;
        hibernate_service: (id: string) => Promise<void>;
        wake_service: (id: string) => Promise<void>;
        get_hibernated_ids: () => Promise<string[]>;
      };
    };
  }
}
