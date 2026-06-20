import { create } from 'zustand'
import type { EntityRef } from '../entities/types'
import { useReviewQueueFocus } from './reviewQueueFocusStore'

export type DockDirection = 'left' | 'right' | 'above' | 'below'

export interface DockPlacement {
  direction: DockDirection
  referenceTabId?: string
}

export interface OpenedTab {
  id: string
  ref: EntityRef
  facet?: string
  title: string
  pinned?: boolean
  placement?: DockPlacement
}

interface PanelsState {
  tabs: OpenedTab[]
  activeId: string | null
  openTab: (ref: EntityRef, title: string, facet?: string, placement?: DockPlacement) => string
  /** 后台打开(鼠标中键): 加 tab 但不切焦点 —— 当前视图不动, 像浏览器中键开后台页。 */
  openTabBackground: (ref: EntityRef, title: string, facet?: string, placement?: DockPlacement) => string
  requestDockPlacement: (id: string, placement: DockPlacement) => void
  clearDockPlacement: (id: string) => void
  closeTab: (id: string) => void
  activate: (id: string) => void
  setTabs: (tabs: OpenedTab[], activeId?: string | null) => void
}

const tabId = (ref: EntityRef, facet?: string) =>
  facet ? `${ref.type}:${ref.id}#${facet}` : `${ref.type}:${ref.id}`

export const CONTROLLER_TAB_ID = 'controller:main'

export const CONTROLLER_TAB: OpenedTab = {
  id: CONTROLLER_TAB_ID,
  ref: { type: 'controller', id: 'main' },
  title: '总控',
  pinned: true,
}

// 项目工作板 = 首页(用户 /goal 2026-06-12: "首页也是工作板")。固定页签且开机默认活跃,
// 排在总控左边 — 进驾驶舱第一眼是"我要搞什么内容", 而不是 agent/plan 列表。
export const PROJECT_BOARD_TAB_ID = 'project_board:main'

export const PROJECT_BOARD_TAB: OpenedTab = {
  id: PROJECT_BOARD_TAB_ID,
  ref: { type: 'project_board', id: 'main' },
  title: '项目',
  pinned: true,
}

export function withFixedTabs(tabs: OpenedTab[]): OpenedTab[] {
  const byId = new Map<string, OpenedTab>()
  // 2026-06 重做: 项目工作板 = 默认首页(进来先看项目); 总控降级为另一个固定页签。两个固定的家。
  byId.set(PROJECT_BOARD_TAB_ID, PROJECT_BOARD_TAB)
  byId.set(CONTROLLER_TAB_ID, CONTROLLER_TAB)
  for (const tab of tabs) {
    if (tab.id === PROJECT_BOARD_TAB_ID) {
      byId.set(PROJECT_BOARD_TAB_ID, { ...PROJECT_BOARD_TAB, ...tab, pinned: true })
    } else if (tab.id === CONTROLLER_TAB_ID) {
      byId.set(CONTROLLER_TAB_ID, { ...CONTROLLER_TAB, ...tab, pinned: true })
    } else {
      byId.set(tab.id, tab)
    }
  }
  return Array.from(byId.values())
}

export const usePanels = create<PanelsState>((set, get) => ({
  tabs: withFixedTabs([]),
  activeId: PROJECT_BOARD_TAB_ID,
  openTab: (ref, title, facet, placement) => {
    // 审阅队列是单例 tab: facet(材料 id)不进 tab id, 改走聚焦 store, 避免每个材料开一个新 tab。
    if (ref.type === 'review_queue') {
      if (facet) useReviewQueueFocus.getState().setFocused(facet)
      const id = tabId(ref)
      const existing = get().tabs.find((t) => t.id === id)
      if (existing) {
        set((s) => ({
          tabs: placement ? s.tabs.map((t) => (t.id === id ? { ...t, placement } : t)) : s.tabs,
          activeId: id,
        }))
        return id
      }
      set((s) => ({ tabs: [...s.tabs, { id, ref, title, placement }], activeId: id }))
      return id
    }
    const id = tabId(ref, facet)
    const existing = get().tabs.find((t) => t.id === id)
    if (existing) {
      set((s) => ({
        tabs: placement ? s.tabs.map((t) => (t.id === id ? { ...t, placement } : t)) : s.tabs,
        activeId: id,
      }))
      return id
    }
    set((s) => ({ tabs: [...s.tabs, { id, ref, facet, title, placement }], activeId: id }))
    return id
  },
  openTabBackground: (ref, title, facet, placement) => {
    // 后台打开: 不改 activeId(当前焦点不动)。review_queue 单例同样规则。
    if (ref.type === 'review_queue' && facet) useReviewQueueFocus.getState().setFocused(facet)
    const id = ref.type === 'review_queue' ? tabId(ref) : tabId(ref, facet)
    if (get().tabs.some((t) => t.id === id)) return id // 已开则不动焦点
    const tab: OpenedTab = ref.type === 'review_queue'
      ? { id, ref, title, placement }
      : { id, ref, facet, title, placement }
    set((s) => ({ tabs: [...s.tabs, tab] })) // 注意: 不设 activeId
    return id
  },
  requestDockPlacement: (id, placement) => set((s) => ({
    tabs: s.tabs.map((t) => (t.id === id ? { ...t, placement } : t)),
    activeId: id,
  })),
  clearDockPlacement: (id) => set((s) => ({
    tabs: s.tabs.map((t) => (t.id === id && t.placement ? { ...t, placement: undefined } : t)),
  })),
  closeTab: (id) => set((s) => {
    const idx = s.tabs.findIndex((t) => t.id === id)
    if (idx < 0) return s
    if (s.tabs[idx]?.pinned) return { tabs: withFixedTabs(s.tabs), activeId: s.activeId || CONTROLLER_TAB_ID }
    const next = s.tabs.filter((t) => t.id !== id)
    let active = s.activeId
    if (s.activeId === id) {
      active = next[idx]?.id ?? next[idx - 1]?.id ?? CONTROLLER_TAB_ID
    }
    return { tabs: withFixedTabs(next), activeId: active }
  }),
  activate: (id) => set({ activeId: id }),
  setTabs: (tabs, activeId) => {
    const next = withFixedTabs(tabs)
    const validActive = activeId && next.some((t) => t.id === activeId) ? activeId : next[next.length - 1]?.id
    set({ tabs: next, activeId: validActive || CONTROLLER_TAB_ID })
  },
}))

// ── 页签快照(用户 #3: 插件关闭再打开时提醒是否恢复上次页签) ───────────────────
const TAB_SNAPSHOT_KEY = 'omni.cockpit.tabSnapshot'

/** 记下当前打开的「非固定」页签(总控是 pinned, 不记)。只存可序列化最小字段。 */
export function saveTabSnapshot(tabs: OpenedTab[]): void {
  try {
    const slim = tabs
      .filter((t) => !t.pinned)
      .map((t) => ({ id: t.id, ref: t.ref, facet: t.facet, title: t.title }))
    localStorage.setItem(TAB_SNAPSHOT_KEY, JSON.stringify(slim))
  } catch { /* localStorage 不可用 */ }
}

/** 读上次的页签快照(供"恢复上次页签"提示用)。 */
export function loadTabSnapshot(): OpenedTab[] {
  try {
    const raw = localStorage.getItem(TAB_SNAPSHOT_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return []
    return arr
      .filter((t: any) => t && t.id && t.ref && t.title)
      .map((t: any) => ({ id: t.id, ref: t.ref, facet: t.facet, title: t.title }))
  } catch { return [] }
}
