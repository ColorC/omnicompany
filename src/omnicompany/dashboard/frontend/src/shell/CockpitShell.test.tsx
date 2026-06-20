import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CockpitShell from './CockpitShell'
import { CONTROLLER_TAB_ID, usePanels, withFixedTabs } from '../stores/panelsStore'
import { reviewstageApi } from '../api/reviewstageClient'

vi.mock('./EditorArea', () => ({
  default: () => <div data-testid="mock-editor-area">Dockview work surface</div>,
}))

vi.mock('./BottomPanel', () => ({
  default: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="mock-bottom-panel">
      <button type="button" onClick={onClose}>close</button>
    </div>
  ),
}))

vi.mock('./useBossSightObservability', () => ({
  useBossSightObservability: vi.fn(),
}))

const briefing = {
  generated_at: '2026-06-03T00:00:00Z',
  severity: 'attention',
  headline: 'Pilot needs review',
  all_green: false,
  summary: {
    plans_total: 4,
    plans_active: 1,
    plans_done: 2,
    review_total: 3,
    review_pending: 2,
    mandatory_unaccepted: 1,
    pushed_unread: 1,
    subagents_total: 3,
    subagents_running: 1,
    subagents_blocked: 1,
  },
  review: {
    available: true,
    total: 3,
    by_status: { delivered: 1, todo_open: 1 },
    by_tier: { mandatory: 1 },
    mandatory_unaccepted: 1,
    pushed_unread: 1,
    recent: [{
      id: 'plan-review',
      title: 'Plan review material',
      kind: 'markdown',
      tier: 'important',
      status: 'pending',
      source_plan_id: 'v2-11',
      source_subagent_id: null,
      pushed_to_user: false,
      updated_at: '2026-06-03T00:00:00Z',
    }, {
      id: 'agent-review',
      title: 'Agent review material',
      kind: 'markdown',
      tier: 'mandatory',
      status: 'pending',
      source_plan_id: null,
      source_subagent_id: 'agent-a',
      pushed_to_user: false,
      updated_at: '2026-06-03T00:00:00Z',
    }],
  },
  plans: {
    total: 4,
    active: [{
      plan_id: 'v2-11',
      title: 'web cockpit endpoint',
      status: 'in_progress',
      open_ref: { type: 'plan', id: 'v2-11', facet: 'summary' },
    }],
  },
  subagents: {
    total: 3,
    running: [{ id: 'agent-a' }],
    blocked: [{ id: 'agent-b' }],
  },
  next_actions: [],
  secretary: {
    title: 'Needs attention',
    body: 'There is work pending.',
  },
}

const ctxSummary = {
  status: 'blocked',
  headline: '1 critical item requires attention',
  summary: {
    status: 'blocked',
    headline: '1 critical item requires attention',
    unresolved_count: 2,
    critical_count: 1,
    comment_unresolved_count: 1,
    comment_todo_done_count: 1,
    blocked_agent_count: 1,
    action_failed_count: 1,
    action_succeeded_count: 3,
  },
  unresolved: [{
    id: 'mandatory_material_unaccepted',
    title: 'Mandatory material is unaccepted',
    priority: 'critical',
    reason: 'mandatory_material_unaccepted',
    kind: 'review',
    open_ref: { type: 'material', id: 'attention-mat' },
  }],
  comment_feedback: {
    by_status: { delivered: 1, read: 1, todo_open: 1, todo_done: 1 },
    unresolved_count: 1,
    todo_done_count: 1,
    unresolved: [],
    recent_resolved: [],
  },
  action_history: {
    recent: [],
    failed_count: 1,
    succeeded_count: 3,
    last_failed: {
      id: 'action-1',
      kind: 'open_review',
      actor: 'controller',
      target: {},
      note: 'open review',
      status: 'failed',
      result: {},
      error: 'missing route',
      created_at: '2026-06-03T00:00:00Z',
    },
  },
  blocked_agents: [{ id: 'agent-b', status: 'blocked' }],
}

function mockBossSightFetch() {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === '/api/boss-sight/briefing') {
      return Promise.resolve(new Response(JSON.stringify(briefing), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }
    if (url === '/api/boss-sight/workflow-summary') {
      return Promise.resolve(new Response(JSON.stringify({
        generated_at: '2026-06-03T00:00:00Z',
        status: 'blocked',
        headline: ctxSummary.headline,
        summary: ctxSummary.summary,
        unresolved: {
          count: 2,
          critical_count: 1,
          attention_count: 1,
          by_reason: { mandatory_material_unaccepted: 1 },
          by_kind: { review: 1 },
          items: ctxSummary.unresolved,
        },
        comment_feedback: { ...ctxSummary.comment_feedback, total: 4 },
        blocked_agents: ctxSummary.blocked_agents,
        action_history: { ...ctxSummary.action_history, count: 4, by_status: { failed: 1 }, by_kind: { open_review: 1 } },
        ctx_summary: ctxSummary,
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }
    if (url.startsWith('/api/boss-sight/material-registry')) {
      return Promise.resolve(new Response(JSON.stringify({
        generated_at: '2026-06-03T00:00:00Z',
        items: [{
          uri: 'omni://material/search-mat',
          id: 'search-mat',
          title: 'Boundary guard material',
          kind: 'guard',
          role: 'boundary',
          layer: 'context',
          status: 'active',
          display: 'Boundary guard material',
          source: 'test',
          snippet: 'search result',
          open_ref: { type: 'material', id: 'search-mat' },
          relations: [],
          tags: ['guard'],
        }],
        total: 1,
        returned: 1,
        counts: { by_kind: {}, by_role: {}, by_layer: {}, by_status: {} },
        filters: {},
        summary: { total: 1, counts: {}, highlighted_items: [], execution_boundaries: [], executors: [] },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }
    if (url === '/api/projects') {
      // 侧栏项目面板 + 首页项目工作板共用的唯一权威注册表 (core/projects_registry)
      return Promise.resolve(new Response(JSON.stringify({
        projects: [], groups_order: ['gameplay_system', 'omnicompany', 'indie-game', 'other'], group_labels: {},
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    }
    if (url === '/api/boss-sight/captures') {
      // 2026-06-03: 提交 = 保存到文件(POST), 进场拉计数(GET)。不再建审阅材料。
      const method = String(init?.method || 'GET').toUpperCase()
      if (method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        return Promise.resolve(new Response(JSON.stringify({
          saved_path: `E:/ws/data/boss_sight/captures/pending/x_${body.capture_kind}.md`,
          pending_count: 1,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      }
      return Promise.resolve(new Response(JSON.stringify({ pending_count: 0, items: [] }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }))
    }
    return Promise.resolve(new Response(JSON.stringify({ recorded: true, skipped: false }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
  })
}

// 提交=保存到文件: 过滤对 /api/boss-sight/captures 的 POST(save), 排除进场的 GET(list)。
function captureBodies(): any[] {
  return ((globalThis.fetch as any).mock.calls as any[])
    .filter((call) => String(call[0]) === '/api/boss-sight/captures'
      && String(call[1]?.method || 'GET').toUpperCase() === 'POST')
    .map((call) => JSON.parse(String(call[1]?.body || '{}')))
}

describe('CockpitShell', () => {
  beforeEach(() => {
    usePanels.setState({ tabs: withFixedTabs([]), activeId: CONTROLLER_TAB_ID })
    window.localStorage.clear()
    delete (window as any).__OMNI_CODEX_DEBUG_HANDOFF__
    // R4: 壳挂载即订阅审阅 WS 流(urgent 角标 + 推送 toast); 单测里不真连。
    vi.spyOn(reviewstageApi, 'openStream').mockReturnValue(() => {})
    mockBossSightFetch()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the v2-11 cockpit shell with workflow summary data', async () => {
    render(<CockpitShell />)

    expect(screen.getByTestId('cockpit-shell')).toBeTruthy()
    expect(screen.getByTestId('cockpit-topbar')).toBeTruthy()
    expect(screen.getByTestId('cockpit-work-spine')).toBeTruthy()
    expect(screen.getByTestId('mock-editor-area')).toBeTruthy()

    await waitFor(() => {
      expect(screen.getByTestId('cockpit-status').textContent).toContain('blocked')
    })
    // 右侧检视面板已删除(与控制台+通知重复); 工作流细节走通知铃 + 控制台。
  })

  it('submits full page snapshots to the review queue', async () => {
    render(<CockpitShell />)

    await waitFor(() => {
      expect(screen.getByTestId('cockpit-status').textContent).toContain('blocked')
    })

    fireEvent.click(screen.getByTestId('cockpit-page-snapshot'))
    expect(screen.getByTestId('cockpit-capture-modal')).toBeTruthy()
    fireEvent.change(screen.getByTestId('cockpit-capture-comment'), { target: { value: 'capture this whole page' } })
    fireEvent.click(screen.getByTestId('cockpit-capture-submit'))

    await waitFor(() => {
      expect(captureBodies().length).toBe(1)
    })
    const body = captureBodies()[0]
    expect(body.capture_kind).toBe('page_snapshot')
    expect(body.comment).toBe('capture this whole page')
    expect(body.text_snapshot).toContain('总控')
    // 2026-06-03: 提交=保存到文件, 不再建审阅材料、不跳审阅队列。
    expect(usePanels.getState().activeId).not.toContain('review_queue')
  })

  it('saves a selected element comment to a capture file (not review)', async () => {
    render(<CockpitShell />)

    await waitFor(() => {
      expect(screen.getByTestId('cockpit-status').textContent).toContain('blocked')
    })

    fireEvent.click(screen.getByTestId('cockpit-element-comment'))
    expect(screen.getByTestId('cockpit-capture-banner').textContent).toContain('点击要评论的元素')
    fireEvent.click(screen.getByTestId('mock-editor-area'))
    expect(screen.getByTestId('cockpit-capture-target').textContent).toContain('mock-editor-area')
    fireEvent.change(screen.getByTestId('cockpit-capture-comment'), { target: { value: 'this area is unclear' } })
    fireEvent.click(screen.getByTestId('cockpit-capture-submit'))

    await waitFor(() => {
      expect(captureBodies().length).toBe(1)
    })
    const body = captureBodies()[0]
    expect(body.capture_kind).toBe('element_comment')
    expect(body.target.selector).toBe('[data-testid="mock-editor-area"]')
    expect(body.comment).toBe('this area is unclear')
    expect(usePanels.getState().activeId).not.toContain('review_queue')
  })

  it('keeps material registry and active plan entry points wired to the work surface', async () => {
    render(<CockpitShell />)

    await waitFor(() => {
      expect(screen.getByTestId('cockpit-status').textContent).toContain('blocked')
    })

    fireEvent.click(screen.getByTestId('cockpit-nav-materials'))
    expect(usePanels.getState().activeId).toBe('material_registry:main')

    fireEvent.click(screen.getByTestId('cockpit-nav-review'))
    expect(usePanels.getState().activeId).toBe('review_queue:main')

    fireEvent.click(screen.getByTestId('cockpit-nav-plan'))
    expect(usePanels.getState().activeId).toBe('plan:v2-11#summary')
  })

  // (已删除)"关联审阅材料"链接随右侧检视面板一并移除; 关联材料改由控制台/本对话材料卡呈现。

  it('opens material registry search results in the work surface', async () => {
    render(<CockpitShell />)

    await waitFor(() => {
      expect(screen.getByTestId('cockpit-status').textContent).toContain('blocked')
    })

    fireEvent.focus(screen.getByTestId('cockpit-global-search'))
    fireEvent.change(screen.getByTestId('cockpit-global-search'), { target: { value: 'boundary' } })

    await waitFor(() => {
      expect(screen.getByText('Boundary guard material')).toBeTruthy()
    })
    fireEvent.click(screen.getByTestId('cockpit-search-result-0'))

    expect(usePanels.getState().activeId).toBe('material:search-mat')
  })

  it('opens search results to the right side when explicitly requested', async () => {
    render(<CockpitShell />)

    await waitFor(() => {
      expect(screen.getByTestId('cockpit-status').textContent).toContain('blocked')
    })

    fireEvent.focus(screen.getByTestId('cockpit-global-search'))
    fireEvent.change(screen.getByTestId('cockpit-global-search'), { target: { value: 'boundary' } })

    await waitFor(() => {
      expect(screen.getByText('Boundary guard material')).toBeTruthy()
    })
    fireEvent.click(screen.getByTestId('cockpit-search-split-0'))

    const materialTab = usePanels.getState().tabs.find((t) => t.id === 'material:search-mat')
    expect(usePanels.getState().activeId).toBe('material:search-mat')
    expect(materialTab?.placement).toEqual({
      direction: 'right',
      referenceTabId: CONTROLLER_TAB_ID,
    })
  })

  it('opens notification refs in the work surface', async () => {
    render(<CockpitShell />)

    await waitFor(() => {
      expect(screen.getByTestId('cockpit-status').textContent).toContain('blocked')
    })

    fireEvent.click(screen.getByTestId('cockpit-notifications-toggle'))
    expect(screen.getByTestId('cockpit-notification-panel')).toBeTruthy()
    fireEvent.click(screen.getByTestId('cockpit-notification-item-0'))
    expect(usePanels.getState().activeId).toBe('material:attention-mat')
    // (右侧检视面板的 cockpit-attention-item 已随面板删除; attention 仍可经通知铃进入。)
  })
})
