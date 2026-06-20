import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ccApi } from '../../api/ccClient'
import { ccChatApi } from '../../api/ccChatClient'
import { CONTROLLER_TAB_ID, usePanels, withFixedTabs } from '../../stores/panelsStore'
import ThreadMonitorPanel from './ThreadMonitorPanel'

describe('ThreadMonitorPanel', () => {
  beforeEach(() => {
    usePanels.setState({ tabs: withFixedTabs([]), activeId: CONTROLLER_TAB_ID })
    vi.restoreAllMocks()
  })

  it('shows chat and pty sessions and opens them as cc_session tabs', async () => {
    vi.spyOn(ccChatApi, 'list').mockResolvedValue([
      {
        id: 'chat-abc123',
        kind: 'chat',
        provider: 'codex',
        cwd: '/workspace/omnicompany',
        cmd: [],
        cols: 0,
        rows: 0,
        started_at: 1780272000,
        alive: true,
        status: 'alive',
        claude_session_id: null,
        active_plan: 'dashboard/[2026-05-31]v2-09',
        model: 'gpt-5.4-codex',
        last_message: 'working on monitor',
      },
    ])
    vi.spyOn(ccApi, 'list').mockResolvedValue([
      {
        id: 'pty-1234567890',
        cmd: [],
        cwd: '/workspace/omnicompany',
        cols: 120,
        rows: 30,
        started_at: 1780271000,
        alive: false,
        status: 'recoverable',
        active_plan: null,
      },
    ])

    render(<ThreadMonitorPanel />)

    await waitFor(() => {
      expect(screen.getAllByTestId('thread-monitor-row')).toHaveLength(2)
    })
    expect(screen.getByText(/codex/)).toBeTruthy()
    expect(screen.getByText(/recoverable/)).toBeTruthy()

    fireEvent.click(screen.getAllByText('打开')[0])

    const tabs = usePanels.getState().tabs
    expect(tabs.some((t) => t.id === 'cc_session:chat-abc123')).toBe(true)
    expect(usePanels.getState().activeId).toBe('cc_session:chat-abc123')
  })
})
