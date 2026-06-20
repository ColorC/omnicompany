import React from 'react'
import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EditorArea from './EditorArea'
import { CONTROLLER_TAB_ID, usePanels, withFixedTabs } from '../stores/panelsStore'

const dockMock = vi.hoisted(() => {
  const panels: any[] = []
  const defaultGroup = { id: 'group-main' }
  const api: any = {
    panels,
    addPanel: vi.fn((options: any) => {
      const group = options.position ? { id: `split-${options.id}` } : defaultGroup
      const panel: any = {
        id: options.id,
        group,
        options,
        api: {
          isActive: false,
          close: vi.fn(),
          setActive: vi.fn(() => {
            panel.api.isActive = true
          }),
          moveTo: vi.fn((moveOptions: any) => {
            panel.moveOptions = moveOptions
            panel.group = { id: `moved-${options.id}` }
          }),
        },
      }
      panels.push(panel)
      return panel
    }),
    getPanel: vi.fn((id: string) => panels.find((panel) => panel.id === id)),
    onDidActivePanelChange: vi.fn(),
    onDidRemovePanel: vi.fn(),
    onDidMaximizedGroupChange: vi.fn(),
    hasMaximizedGroup: vi.fn(() => false),
    exitMaximizedGroup: vi.fn(),
  }
  return { api, panels }
})

vi.mock('dockview', async () => {
  const ReactModule = await import('react')
  return {
    DockviewReact: ({ onReady }: { onReady: (event: any) => void }) => {
      ReactModule.useEffect(() => {
        onReady({ api: dockMock.api })
      }, [])
      return ReactModule.createElement('div', { 'data-testid': 'dockview-mock' })
    },
  }
})

describe('EditorArea dock placement', () => {
  beforeEach(() => {
    dockMock.panels.splice(0, dockMock.panels.length)
    vi.clearAllMocks()
    usePanels.setState({ tabs: withFixedTabs([]), activeId: CONTROLLER_TAB_ID })
  })

  it('passes right-side placement to Dockview when adding a new panel', async () => {
    usePanels.getState().openTab(
      { type: 'material', id: 'mat-1' },
      'material 1',
      undefined,
      { direction: 'right', referenceTabId: CONTROLLER_TAB_ID },
    )

    render(<EditorArea />)

    // 固定页签 2 个(项目工作板 + 总控) + material = 3
    await waitFor(() => {
      expect(dockMock.api.addPanel).toHaveBeenCalledTimes(3)
    })
    const materialAdd = dockMock.api.addPanel.mock.calls.find(([options]: any[]) => options.id === 'material:mat-1')?.[0]
    expect(materialAdd.position.referencePanel.id).toBe(CONTROLLER_TAB_ID)
    expect(materialAdd.position.direction).toBe('right')
    await waitFor(() => {
      expect(usePanels.getState().tabs.find((tab) => tab.id === 'material:mat-1')?.placement).toBeUndefined()
    })
  })

  it('moves an existing panel when a split placement is requested later', async () => {
    usePanels.getState().openTab({ type: 'material', id: 'mat-2' }, 'material 2')

    render(<EditorArea />)

    // 固定页签 2 个(项目工作板 + 总控) + material = 3
    await waitFor(() => {
      expect(dockMock.api.addPanel).toHaveBeenCalledTimes(3)
    })
    const materialPanel = dockMock.api.getPanel('material:mat-2')
    expect(materialPanel).toBeTruthy()

    act(() => {
      usePanels.getState().requestDockPlacement('material:mat-2', {
        direction: 'right',
        referenceTabId: CONTROLLER_TAB_ID,
      })
    })

    await waitFor(() => {
      expect(materialPanel.api.moveTo).toHaveBeenCalledWith({
        group: dockMock.api.getPanel(CONTROLLER_TAB_ID).group,
        position: 'right',
      })
    })
    expect(usePanels.getState().tabs.find((tab) => tab.id === 'material:mat-2')?.placement).toBeUndefined()
  })
})
