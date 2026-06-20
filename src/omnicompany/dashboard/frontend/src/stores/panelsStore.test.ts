import { beforeEach, describe, expect, it } from 'vitest'
import { CONTROLLER_TAB_ID, PROJECT_BOARD_TAB_ID, usePanels, withFixedTabs } from './panelsStore'
import { useReviewQueueFocus } from './reviewQueueFocusStore'

describe('panelsStore fixed controller tab', () => {
  beforeEach(() => {
    usePanels.setState({ tabs: withFixedTabs([]), activeId: PROJECT_BOARD_TAB_ID })
  })

  it('starts with the fixed project board (homepage) + controller tabs', () => {
    const state = usePanels.getState()
    expect(state.tabs.map((t) => t.id)).toEqual([PROJECT_BOARD_TAB_ID, CONTROLLER_TAB_ID])
    expect(state.tabs.every((t) => t.pinned)).toBe(true)
    // 首页 = 项目工作板(用户 /goal 2026-06-12), 开机默认活跃
    expect(state.activeId).toBe(PROJECT_BOARD_TAB_ID)
  })

  it('does not close the fixed controller tab but closes normal tabs', () => {
    const state = usePanels.getState()
    state.openTab({ type: 'cc_session', id: 'chat-1' }, 'chat 1')
    expect(usePanels.getState().tabs.map((t) => t.id)).toContain('cc_session:chat-1')

    usePanels.getState().closeTab(CONTROLLER_TAB_ID)
    expect(usePanels.getState().tabs.map((t) => t.id)).toContain(CONTROLLER_TAB_ID)

    usePanels.getState().closeTab('cc_session:chat-1')
    expect(usePanels.getState().tabs.map((t) => t.id)).not.toContain('cc_session:chat-1')
  })

  it('merges the fixed tabs into restored layouts', () => {
    usePanels.getState().setTabs([
      { id: 'cc_session:chat-2', ref: { type: 'cc_session', id: 'chat-2' }, title: 'chat 2' },
    ], 'cc_session:chat-2')

    const state = usePanels.getState()
    expect(state.tabs.map((t) => t.id)).toEqual([PROJECT_BOARD_TAB_ID, CONTROLLER_TAB_ID, 'cc_session:chat-2'])
    expect(state.activeId).toBe('cc_session:chat-2')
  })

  it('keeps explicit dock placement requests for split monitoring', () => {
    usePanels.getState().openTab(
      { type: 'material', id: 'mat-1' },
      'material 1',
      undefined,
      { direction: 'right', referenceTabId: CONTROLLER_TAB_ID },
    )
    expect(usePanels.getState().tabs.find((t) => t.id === 'material:mat-1')?.placement).toEqual({
      direction: 'right',
      referenceTabId: CONTROLLER_TAB_ID,
    })

    usePanels.getState().openTab(
      { type: 'material', id: 'mat-1' },
      'material 1',
      undefined,
      { direction: 'below', referenceTabId: CONTROLLER_TAB_ID },
    )
    expect(usePanels.getState().tabs.find((t) => t.id === 'material:mat-1')?.placement).toEqual({
      direction: 'below',
      referenceTabId: CONTROLLER_TAB_ID,
    })

    usePanels.getState().clearDockPlacement('material:mat-1')
    expect(usePanels.getState().tabs.find((t) => t.id === 'material:mat-1')?.placement).toBeUndefined()
  })

  it('review_material 是多实例 tab: 每条材料一个页签, 同材料重开只聚焦', () => {
    const { openTab } = usePanels.getState()
    const a = openTab({ type: 'review_material', id: 'mat_a' }, 'A 材料')
    const b = openTab({ type: 'review_material', id: 'mat_b' }, 'B 材料')
    expect(a).toBe('review_material:mat_a')
    expect(b).toBe('review_material:mat_b')
    expect(usePanels.getState().tabs.filter((t) => t.ref.type === 'review_material').length).toBe(2)

    const again = openTab({ type: 'review_material', id: 'mat_a' }, 'A 材料')
    expect(again).toBe(a)
    expect(usePanels.getState().activeId).toBe(a)
    expect(usePanels.getState().tabs.filter((t) => t.ref.type === 'review_material').length).toBe(2)
  })

  it('review_queue 是单例 tab: 不同材料只开一个 tab, 并更新聚焦 id', () => {
    useReviewQueueFocus.setState({ focusedId: null, nonce: 0 })
    const { openTab } = usePanels.getState()
    const id1 = openTab({ type: 'review_queue', id: 'main' }, '审阅队列', 'mat_a')
    const id2 = openTab({ type: 'review_queue', id: 'main' }, '审阅队列', 'mat_b')
    expect(id1).toBe('review_queue:main')
    expect(id2).toBe('review_queue:main')
    const rqTabs = usePanels.getState().tabs.filter((t) => t.ref.type === 'review_queue')
    expect(rqTabs.length).toBe(1)
    expect(useReviewQueueFocus.getState().focusedId).toBe('mat_b')
    expect(useReviewQueueFocus.getState().nonce).toBe(2)
  })
})
