import { describe, expect, it } from 'vitest'
import {
  ccProviderToLLMProvider,
  composerSendToWsFrame,
  entityToProject,
  entityToSession,
} from './ccSessionAdapter'
import type { CcSessionEntity } from '../entities/cc_session'

describe('entityToProject / entityToSession', () => {
  const entity: CcSessionEntity = {
    type: 'cc_session',
    kind: 'chat',
    id: 'chat-abc123',
    title: 'My Test',
    cwd: '/workspace/omnicompany',
    alive: true,
    status: 'alive',
    cmd: ['claude_code', '(chat)'],
    startedAt: 1778500000,
    provider: 'codex',
    tags: [],
  }

  it('maps a cc_session entity to an upstream project shell', () => {
    const p = entityToProject(entity)
    expect(p.projectId).toBe('cc_session::/workspace/omnicompany')
    expect(p.displayName).toBe('omnicompany')
    expect(p.fullPath).toBe('/workspace/omnicompany')
    expect(p.sessions?.length).toBe(1)
  })

  it('maps session metadata and provider', () => {
    const s = entityToSession(entity)
    expect(s.id).toBe('chat-abc123')
    expect(s.title).toBe('My Test')
    expect(s.__provider).toBe('codex')
    expect(s.__projectId).toBe('cc_session::/workspace/omnicompany')
  })

  it('maps dashboard providers to upstream UI providers', () => {
    expect(ccProviderToLLMProvider('claude_code')).toBe('claude')
    expect(ccProviderToLLMProvider('codex')).toBe('codex')
    expect(ccProviderToLLMProvider('omni_agent')).toBe('claude')
    expect(ccProviderToLLMProvider(null)).toBe('claude')
    expect(ccProviderToLLMProvider(undefined)).toBe('claude')
  })
})

describe('composerSendToWsFrame control frames', () => {
  it('passes permission mode changes through to the backend', () => {
    expect(JSON.parse(composerSendToWsFrame({
      type: 'session.permission_mode',
      permissionMode: 'bypassPermissions',
    }) || '{}')).toEqual({
      type: 'session.permission_mode',
      permissionMode: 'bypassPermissions',
    })
  })

  it('passes model changes through to the backend', () => {
    expect(JSON.parse(composerSendToWsFrame({
      type: 'session.model',
      model: 'gpt-test-model',
    }) || '{}')).toEqual({
      type: 'session.model',
      model: 'gpt-test-model',
    })
  })

  it('maps upstream command objects to backend user messages', () => {
    expect(JSON.parse(composerSendToWsFrame({
      type: 'codex-command',
      command: 'hello',
      options: { permissionMode: 'bypassPermissions', toolsSettings: { skipPermissions: true } },
    }) || '{}')).toEqual({
      type: 'user.message',
      content: 'hello',
      permissionMode: 'bypassPermissions',
      skipPermissions: true,
    })
  })

  it('maps abort and permission responses', () => {
    expect(JSON.parse(composerSendToWsFrame({ type: 'abort-session' }) || '{}')).toEqual({
      type: 'user.interrupt',
    })
    expect(JSON.parse(composerSendToWsFrame({
      type: 'codex-permission-response',
      requestId: 'req-1',
      allow: true,
      updatedInput: { x: 1 },
      message: 'ok',
      rememberEntry: { scope: 'once' },
    }) || '{}')).toEqual({
      type: 'claude-permission-response',
      requestId: 'req-1',
      allow: true,
      updatedInput: { x: 1 },
      message: 'ok',
      rememberEntry: { scope: 'once' },
    })
  })
})
