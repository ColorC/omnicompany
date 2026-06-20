import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MaterialRegistryPanel from './MaterialRegistryPanel'
import { registerAllEntities } from '../../shell/registerEntities'
import { CONTROLLER_TAB_ID, usePanels, withFixedTabs } from '../../stores/panelsStore'

const payload = {
  generated_at: '2026-06-01T00:00:00Z',
  total: 3,
  returned: 3,
  counts: {
    by_kind: { plan: 1, guard: 1, worker: 1 },
    by_role: { direction: 1, boundary: 1, executor: 1 },
    by_layer: { context: 2, executor: 1 },
    by_status: { active: 1, unknown: 2 },
  },
  filters: {},
  summary: {
    total: 3,
    counts: {},
    highlighted_items: [],
    execution_boundaries: [],
    executors: [],
  },
  items: [
    {
      uri: 'omni://material/docs%2Fplans%2Fdashboard%2F%5B2026-05-31%5Dv2-10%2Fplan.md',
      id: 'docs/plans/dashboard/[2026-05-31]v2-10/plan.md',
      title: 'Roadmap Plan',
      kind: 'plan',
      role: 'direction',
      layer: 'context',
      status: 'active',
      display: '@material:Roadmap',
      source: 'plan_index',
      path: 'docs/plans/dashboard/[2026-05-31]v2-10/plan.md',
      snippet: 'todo=0/1',
      open_ref: { type: 'plan', id: 'dashboard/[2026-05-31]v2-10' },
      entity_uri: 'omni://plan/dashboard%2F%5B2026-05-31%5Dv2-10',
      relations: [{ kind: 'project', id: 'dashboard', label: 'belongs_to_project', uri: 'omni://project/dashboard' }],
      tags: ['dashboard'],
      updated_at: null,
    },
    {
      uri: 'omni://material/docs%2Fstandards%2Froot_guard.md',
      id: 'docs/standards/root_guard.md',
      title: 'Root Guard',
      kind: 'guard',
      role: 'boundary',
      layer: 'context',
      status: null,
      display: '@material:Root Guard',
      source: 'docs',
      path: 'docs/standards/root_guard.md',
      snippet: 'Root guard boundary',
      open_ref: { type: 'note', id: 'standards/root_guard' },
      entity_uri: 'omni://file/standards%2Froot_guard',
      relations: [],
      tags: ['standards'],
      updated_at: null,
    },
    {
      uri: 'omni://material/worker%2Fservices%2Fdemo%2Fworkers%2Fplanner',
      id: 'worker/services/demo/workers/planner',
      title: 'planner',
      kind: 'worker',
      role: 'executor',
      layer: 'executor',
      status: null,
      display: '@material:planner',
      source: 'packages',
      path: 'src/omnicompany/packages/services/demo/workers/planner.py',
      snippet: 'worker',
      open_ref: { type: 'worker', id: 'services/demo/workers/planner' },
      entity_uri: 'omni://worker/services%2Fdemo%2Fworkers%2Fplanner',
      relations: [],
      tags: ['worker'],
      updated_at: null,
    },
  ],
}

describe('MaterialRegistryPanel', () => {
  beforeEach(() => {
    registerAllEntities()
    usePanels.setState({ tabs: withFixedTabs([]), activeId: CONTROLLER_TAB_ID })
    vi.restoreAllMocks()
  })

  it('renders material counts, detail, and opens existing entity tabs', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))

    render(<MaterialRegistryPanel />)

    await waitFor(() => {
      expect(screen.getAllByText('Roadmap Plan').length).toBeGreaterThan(0)
    })
    expect(screen.getByText(/2 条上下文/)).toBeTruthy()
    expect(screen.getByText(/1 个执行者/)).toBeTruthy()
    expect(screen.getByText('belongs_to_project: project/dashboard')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /打开/ }))
    expect(usePanels.getState().tabs.some((tab) => tab.id === 'plan:dashboard/[2026-05-31]v2-10')).toBe(true)
  })

  it('sends role filter queries and shows selected material detail', async () => {
    const urls: string[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      urls.push(String(input))
      return Promise.resolve(new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    })

    render(<MaterialRegistryPanel />)

    await waitFor(() => {
      expect(screen.getByText('Root Guard')).toBeTruthy()
    })
    fireEvent.click(screen.getByText('Root Guard'))
    expect(screen.getByText('Root guard boundary')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('作用'), { target: { value: 'executor' } })
    await waitFor(() => {
      expect(urls.some((url) => url.includes('role=executor'))).toBe(true)
    })
  })
})
