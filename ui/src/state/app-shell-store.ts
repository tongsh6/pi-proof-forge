import { create } from "zustand";

interface AppShellState {
  language: "en" | "zh";
  sideNavCollapsed: boolean;
  setLanguage: (lang: "en" | "zh") => void;
  toggleSideNav: () => void;
}

export const useAppShellStore = create<AppShellState>((set) => ({
  language: "zh",
  sideNavCollapsed: false,
  setLanguage: (language) => set({ language }),
  toggleSideNav: () =>
    set((state) => ({ sideNavCollapsed: !state.sideNavCollapsed })),
}));
