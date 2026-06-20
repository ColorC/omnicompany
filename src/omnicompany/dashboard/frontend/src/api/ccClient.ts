/**
 * Claude Code wrapper REST + WS client.
 * Backend: src/omnicompany/dashboard/cc_wrapper/api.py
 */

const BASE = '/api/cc'

export interface CcSessionMeta {
  id: string
  cmd: string[]
  cwd: string
  cols: number
  rows: number
  started_at: number
  alive: boolean
  subscribers?: number
  buffered_chunks?: number
  status?: 'alive' | 'recoverable'
  claude_session_id?: string | null
  active_plan?: string | null
  ended_at?: number | null
  exit_reason?: string | null
}

export interface SessionsList {
  items: CcSessionMeta[]      // alive
  alive_count: number
  recoverable: CcSessionMeta[]
  recoverable_count: number
}

export interface CreateSessionBody {
  cmd?: string[]
  cwd?: string
  cols?: number
  rows?: number
  safe_mode?: boolean
}

export interface ModifiedFile {
  path: string
  count: number
  last_ts: string
  last_tool: string
}
export interface BashWrite {
  path: string
  snippet: string
  ts: string
}
export interface ResolvedContextItem {
  path: string
  abs_path?: string
  category?: string
  source?: string
  reason?: string
  exists?: boolean
  dashboard_target?: { type: 'note' | 'plan'; id: string } | null
  vscode_uri?: string
}
export interface ResolvedContextBundle {
  plan_id?: string | null
  project?: string | null
  paths?: string[]
  explicit_kinds?: string[]
  inferred_kinds?: Record<string, string | null>
  topic?: string
  contexts: ResolvedContextItem[]
  total: number
  missing: ResolvedContextItem[]
  missing_total: number
  resolved_at?: number
  summary?: string
  error?: string
}
export interface SessionContext {
  session_id: string
  kind?: 'cc' | 'native'
  context: {
    active_plan?: string | null
    plan_meta?: Record<string, any>
    project_meta?: Record<string, any>  // project.md frontmatter (立于 plan 之上)
    cwd?: string | null
    provider?: string | null
    claude_session_id?: string | null
    started_at?: number | null
    ended_at?: number | null
    agent_state?: string
    user_context?: { work_type?: string; standards?: string[]; notes?: string }
    resolved_context?: ResolvedContextBundle
  }
  modified_files: ModifiedFile[]
  bash_writes: BashWrite[]
  added_workers: string[]
  added_materials: string[]
  event_count: number
}

export const ccApi = {
  async health(): Promise<{ status: string; claude_cli_found: boolean; session_count: number }> {
    const r = await fetch(`${BASE}/health`)
    if (!r.ok) throw new Error(`cc/health: ${r.status}`)
    return r.json()
  },

  async list(): Promise<CcSessionMeta[]> {
    // Returns BOTH alive + recoverable, fused into one list with status fields.
    const r = await fetch(`${BASE}/sessions?include_recoverable=true`)
    if (!r.ok) throw new Error(`cc/sessions list: ${r.status}`)
    const d = await r.json() as SessionsList
    const alive = (d.items || []).map(m => ({ ...m, status: 'alive' as const }))
    const rec = (d.recoverable || []).map(m => ({ ...m, status: 'recoverable' as const }))
    return [...alive, ...rec]
  },

  async create(body?: CreateSessionBody): Promise<CcSessionMeta> {
    const r = await fetch(`${BASE}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }))
      throw new Error(err.detail || `cc/sessions create: ${r.status}`)
    }
    return r.json()
  },

  async resume(recoverableId: string): Promise<CcSessionMeta> {
    const r = await fetch(`${BASE}/sessions/${recoverableId}/resume`, { method: 'POST' })
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }))
      throw new Error(err.detail || `cc/sessions resume: ${r.status}`)
    }
    return r.json()
  },

  async kill(id: string): Promise<void> {
    const r = await fetch(`${BASE}/sessions/${id}`, { method: 'DELETE' })
    if (!r.ok) throw new Error(`cc/sessions delete: ${r.status}`)
  },

  async context(id: string): Promise<SessionContext> {
    const r = await fetch(`${BASE}/sessions/${id}/context`)
    if (!r.ok) throw new Error(`cc/sessions context: ${r.status}`)
    return r.json()
  },

  // (REMOVED 2026-05-02 round 4) patchContext — work_type / standards 改走 plan.md frontmatter

  /**
   * Switch (or unbind) the active_plan for a cc_session.
   * plan_id=null 解绑. effective='next_user_turn' (alive) | 'immediate' (recoverable).
   */
  async patchActivePlan(sid: string, planId: string | null): Promise<{
    session_id: string
    active_plan: string | null
    alive: boolean
    effective: 'next_user_turn' | 'immediate'
    note: string
  }> {
    const r = await fetch(`${BASE}/sessions/${sid}/active_plan`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_id: planId }),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }))
      throw new Error(err.detail || `patchActivePlan: ${r.status}`)
    }
    return r.json()
  },

  /** Build the WS URL for a session. Caller wraps in `new WebSocket(...)`. */
  wsUrl(id: string): string {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${proto}://${window.location.host}${BASE}/sessions/${id}/ws`
  },

  // ── settings install / status (mirrors `omni cc` CLI exactly) ──
  async installStatus(scope: 'project' | 'user' = 'project'): Promise<{
    settings_path: string
    installed: boolean
    mcp_command?: string | null
    hook_events?: string[]
  }> {
    const r = await fetch(`${BASE}/install/status?scope=${scope}`)
    if (!r.ok) throw new Error(`status: ${r.status}`)
    return r.json()
  },
  async install(scope: 'project' | 'user' = 'project'): Promise<any> {
    const r = await fetch(`${BASE}/install?scope=${scope}`, { method: 'POST' })
    if (!r.ok) throw new Error(`install: ${r.status}`)
    return r.json()
  },
  async uninstall(scope: 'project' | 'user' = 'project'): Promise<any> {
    const r = await fetch(`${BASE}/install?scope=${scope}`, { method: 'DELETE' })
    if (!r.ok) throw new Error(`uninstall: ${r.status}`)
    return r.json()
  },
}
