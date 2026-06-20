import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useChatRealtimeHandlers } from './useChatRealtimeHandlers';
import type { SessionStore } from '../../../stores/useSessionStore';

function makeSessionStore(overrides: Partial<SessionStore> = {}): SessionStore {
  return {
    fetchFromServer: vi.fn(),
    fetchMore: vi.fn(),
    refreshFromServer: vi.fn().mockResolvedValue(undefined),
    appendRealtime: vi.fn(),
    appendRealtimeBatch: vi.fn(),
    setStatus: vi.fn(),
    isStale: vi.fn(),
    updateStreaming: vi.fn(),
    finalizeStreaming: vi.fn(),
    clearRealtime: vi.fn(),
    getMessages: vi.fn(() => []),
    getSessionSlot: vi.fn(),
    replaceSessionId: vi.fn(),
    setActiveSession: vi.fn(),
    has: vi.fn(() => false),
    ...overrides,
  } as unknown as SessionStore;
}

function renderRealtimeHook(latestMessage: any, sessionStore = makeSessionStore()) {
  const setIsLoading = vi.fn();
  const setCanAbortSession = vi.fn();
  const setClaudeStatus = vi.fn();
  const setTokenBudget = vi.fn();
  const setPendingPermissionRequests = vi.fn();
  const onSessionNotProcessing = vi.fn();

  renderHook(() => useChatRealtimeHandlers({
    latestMessage,
    provider: 'claude',
    selectedProject: {
      projectId: 'proj',
      displayName: 'proj',
      fullPath: '/workspace/omnicompany',
      path: '/workspace/omnicompany',
      sessions: [],
    },
    selectedSession: {
      id: 'sess_1',
      title: 'test',
      createdAt: new Date(0).toISOString(),
      __provider: 'claude',
      __projectId: 'proj',
    },
    currentSessionId: 'sess_1',
    setCurrentSessionId: vi.fn(),
    setIsLoading,
    setCanAbortSession,
    setClaudeStatus,
    setTokenBudget,
    setPendingPermissionRequests,
    pendingViewSessionRef: { current: null },
    streamBufferRef: { current: '' },
    streamTimerRef: { current: null },
    accumulatedStreamRef: { current: '' },
    onSessionNotProcessing,
    sessionStore,
  }));

  return {
    sessionStore,
    setIsLoading,
    setCanAbortSession,
    setClaudeStatus,
    setTokenBudget,
    setPendingPermissionRequests,
    onSessionNotProcessing,
  };
}

describe('useChatRealtimeHandlers batch handling', () => {
  it('processes status before complete in one ordered batch', () => {
    const state = renderRealtimeHook([
      {
        id: 'status_1',
        sessionId: 'sess_1',
        timestamp: new Date(0).toISOString(),
        provider: 'claude',
        kind: 'status',
        text: 'token_budget',
        tokenBudget: { used: 7, total: 200000 },
      },
      {
        id: 'complete_1',
        sessionId: 'sess_1',
        timestamp: new Date(1).toISOString(),
        provider: 'claude',
        kind: 'complete',
        exitCode: 0,
      },
    ]);

    expect(state.setTokenBudget).toHaveBeenCalledWith({ used: 7, total: 200000 });
    expect(state.setIsLoading).toHaveBeenCalledWith(false);
    expect(state.setCanAbortSession).toHaveBeenCalledWith(false);
    expect(state.onSessionNotProcessing).toHaveBeenCalledWith('sess_1');
    expect(state.sessionStore.appendRealtime).toHaveBeenCalledTimes(2);
    expect(state.sessionStore.refreshFromServer).toHaveBeenCalledWith('sess_1', expect.any(Object));

    const tokenBudgetOrder = state.setTokenBudget.mock.invocationCallOrder[0];
    const loadingClearedOrder = state.setIsLoading.mock.invocationCallOrder[0];
    expect(tokenBudgetOrder).toBeLessThan(loadingClearedOrder);
  });

  it('does not drop stream_end after a stream_delta in the same batch', () => {
    const state = renderRealtimeHook([
      {
        id: 'delta_1',
        sessionId: 'sess_1',
        timestamp: new Date(0).toISOString(),
        provider: 'claude',
        kind: 'stream_delta',
        content: 'hello',
      },
      {
        id: 'end_1',
        sessionId: 'sess_1',
        timestamp: new Date(1).toISOString(),
        provider: 'claude',
        kind: 'stream_end',
      },
    ]);

    expect(state.sessionStore.updateStreaming).toHaveBeenCalledWith('sess_1', 'hello', 'claude');
    expect(state.sessionStore.finalizeStreaming).toHaveBeenCalledWith('sess_1');
  });
});
