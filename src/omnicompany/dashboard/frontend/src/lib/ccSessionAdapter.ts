/**
 * Adapter between cc_session entities and the upstream-style ChatInterface.
 *
 * The live chat path now receives NormalizedMessage wire frames directly from
 * ccdaemon/chat.py. This file only keeps entity shape adaptation and composer
 * control-frame translation.
 */

import type { Project, ProjectSession, LLMProvider } from '../types/app'
import type { CcSessionEntity } from '../entities/cc_session'

export function entityToProject(entity: CcSessionEntity): Project {
  const cwdLast = entity.cwd.split(/[\\/]/).filter(Boolean).slice(-1)[0] || entity.cwd
  return {
    projectId: `cc_session::${entity.cwd}`,
    displayName: cwdLast,
    fullPath: entity.cwd,
    path: entity.cwd,
    sessions: [entityToSession(entity)],
  }
}

export function entityToSession(entity: CcSessionEntity): ProjectSession {
  return {
    id: entity.id,
    title: entity.title || entity.id.slice(-6),
    name: entity.title || undefined,
    createdAt: new Date(entity.startedAt * 1000).toISOString(),
    __provider: ccProviderToLLMProvider(entity.provider),
    __projectId: `cc_session::${entity.cwd}`,
  }
}

export function ccProviderToLLMProvider(provider?: string | null): LLMProvider {
  if (provider === 'codex') return 'codex'
  return 'claude'
}

/**
 * ChatComposer emits upstream-style control objects. ccdaemon websocket accepts
 * compact backend frames, so the shell adapter translates the few frames that
 * are still wrapper-owned.
 */
export function composerSendToWsFrame(message: unknown): string | null {
  if (typeof message === 'string') return message
  const m = message as any
  if (m && typeof m === 'object') {
    if (m.type === 'session.permission_mode') {
      return JSON.stringify({
        type: 'session.permission_mode',
        permissionMode: m.permissionMode,
      })
    }
    if (m.type === 'session.model') {
      return JSON.stringify({
        type: 'session.model',
        model: m.model,
      })
    }
    if (typeof m.type === 'string' && m.type.endsWith('-command') && m.command) {
      const opts = (m.options || {}) as any
      return JSON.stringify({
        type: 'user.message',
        content: String(m.command),
        permissionMode: opts.permissionMode,
        skipPermissions: opts.toolsSettings?.skipPermissions,
      })
    }
    if (m.type === 'abort-session') {
      return JSON.stringify({ type: 'user.interrupt' })
    }
    if (typeof m.type === 'string' && m.type.includes('permission-response')) {
      return JSON.stringify({
        type: 'claude-permission-response',
        requestId: m.requestId,
        allow: Boolean(m.allow),
        updatedInput: m.updatedInput,
        message: m.message,
        rememberEntry: m.rememberEntry,
      })
    }
    return null
  }
  return JSON.stringify(message)
}
