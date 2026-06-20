/**
 * BOSS SIGHT 块 4 审阅台前端 API 客户端 — 配套
 * src/omnicompany/dashboard/boss_sight/reviewstage/routes.py
 *
 * 端点 mounted at /api/boss-sight/reviewstage.
 * WS at /api/boss-sight/reviewstage/stream (cc_proxy 透传).
 */

const BASE = '/api/boss-sight/reviewstage'

export type MaterialKind = 'image' | 'markdown' | 'html' | 'key_question' | 'custom_web_template'
export type MaterialTier = 'mandatory' | 'important' | 'processual' | 'ignored'
export type MaterialStatus = 'pending' | 'accepted' | 'rejected' | 'blocked'
export type AnnotationKind = 'ai' | 'user'
export type CommentFeedbackStatus = 'delivered' | 'read' | 'to_todo' | 'todo_done'

export interface Annotation {
  id: string
  kind: AnnotationKind
  content: string
  target: Record<string, unknown>
  created_at: string
  author: string
}

export interface Comment {
  id: string
  content: string
  author: string
  target: Record<string, unknown>
  created_at: string
  feedback_status: CommentFeedbackStatus
  feedback_history: Record<string, unknown>[]
}

export interface Material {
  id: string
  kind: MaterialKind
  tier: MaterialTier
  title: string
  status: MaterialStatus
  source_subagent_id: string | null
  source_plan_id: string | null
  file_relpath: string | null
  inline_content: string | null
  annotations: Annotation[]
  comments: Comment[]
  annotations_allowed: boolean
  created_at: string
  updated_at: string
  history: Record<string, unknown>[]
  pushed_to_user: boolean
  pushed_reason: string | null
  pushed_at: string | null
  archived?: boolean
  extra: Record<string, unknown>
}

export interface MaterialStats {
  total: number
  by_status: Record<string, number>
  by_tier: Record<string, number>
  mandatory_unaccepted: number
  pushed_unread: number
}

export type ReviewCaptureKind = 'element_comment' | 'page_snapshot' | 'debug_start'

export interface ReviewCaptureBody {
  capture_kind: ReviewCaptureKind
  title?: string
  comment?: string
  author?: string
  url?: string
  route?: string
  active_tab?: Record<string, unknown>
  target?: Record<string, unknown>
  page?: Record<string, unknown>
  text_snapshot?: string
  dom_snapshot?: string
  debug_allowed?: boolean
}

export type StreamEvent =
  | { event_type: 'snapshot'; items: Material[] }
  | { event_type: 'created' | 'updated' | 'verdict_changed' | 'comment_added' | 'annotation_added' | 'pushed' | 'deleted'; material: Material }
  | { event_type: 'active_material'; material_id: string }
  | { event_type: 'ping' }

async function jsonOrThrow<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = ''
    try { detail = (await r.json()).detail || '' } catch { /* */ }
    throw new Error(`${r.status} ${r.statusText} ${detail}`)
  }
  return r.json() as Promise<T>
}

export const reviewstageApi = {
  list: async (filter: {
    status?: MaterialStatus; tier?: MaterialTier; plan_id?: string; pushed_only?: boolean
    include_archived?: boolean; archived_only?: boolean
  } = {}): Promise<{ count: number; items: Material[] }> => {
    const q = new URLSearchParams()
    if (filter.status) q.set('status', filter.status)
    if (filter.tier) q.set('tier', filter.tier)
    if (filter.plan_id) q.set('plan_id', filter.plan_id)
    if (filter.pushed_only) q.set('pushed_only', 'true')
    if (filter.include_archived) q.set('include_archived', 'true')
    if (filter.archived_only) q.set('archived_only', 'true')
    const r = await fetch(`${BASE}?${q.toString()}`)
    return jsonOrThrow(r)
  },

  /** 软归档/还原一条材料(不删文件)。 */
  setArchived: async (id: string, archived = true): Promise<Material> => {
    const r = await fetch(`${BASE}/${id}/archive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archived, by: 'user' }),
    })
    return jsonOrThrow(r)
  },

  stats: async (): Promise<MaterialStats> => {
    const r = await fetch(`${BASE}/_stats`)
    return jsonOrThrow(r)
  },

  get: async (id: string): Promise<Material> => {
    const r = await fetch(`${BASE}/${id}`)
    return jsonOrThrow(r)
  },

  setVerdict: async (id: string, verdict: MaterialStatus, reason = ''): Promise<Material> => {
    const r = await fetch(`${BASE}/${id}/verdict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verdict, by: 'user', reason }),
    })
    return jsonOrThrow(r)
  },

  addComment: async (id: string, content: string, target?: Record<string, unknown>): Promise<Comment> => {
    const r = await fetch(`${BASE}/${id}/comment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, author: 'user', target }),
    })
    return jsonOrThrow(r)
  },

  // 评论文件(每材料一个 markdown): 读 / 追加。不进 Comment 数组、不唤起总控(用户 2026-06-13)。
  getCommentsFile: async (id: string, title?: string): Promise<{ content: string; path: string; abs_path: string; exists: boolean }> => {
    const q = title ? `?title=${encodeURIComponent(title)}` : ''
    const r = await fetch(`${BASE}/${id}/comments-file${q}`)
    return jsonOrThrow(r)
  },

  appendCommentsFile: async (id: string, content: string, anchor?: string, title?: string): Promise<{ content: string; path: string; abs_path: string }> => {
    const r = await fetch(`${BASE}/${id}/comments-file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, author: 'user', anchor, title }),
    })
    return jsonOrThrow(r)
  },

  // 整文件替换(就地编辑/删除某条评论后存回)。
  writeCommentsFile: async (id: string, content: string): Promise<{ content: string; path: string; abs_path: string }> => {
    const r = await fetch(`${BASE}/${id}/comments-file`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    })
    return jsonOrThrow(r)
  },

  // 跨表面"激活材料"广播(三区化): 队列/材料页签选中某材料 → POST 这里 → 后端在审阅 WS 流上
  // 回广播 active_material 事件, 别的 webview(评论次级侧栏等)收到后切到该材料。单表面也无妨(本地已先生效)。
  setActiveMaterial: async (id: string): Promise<void> => {
    await fetch(`${BASE}/active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ material_id: id }),
    }).catch(() => { /* 后端老版本/无端点: 静默, 本地联动仍生效 */ })
  },

  setCommentFeedback: async (
    id: string,
    commentId: string,
    status: CommentFeedbackStatus,
    note = '',
  ): Promise<Comment> => {
    const r = await fetch(`${BASE}/${id}/comments/${commentId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, by: 'user', note }),
    })
    return jsonOrThrow(r)
  },

  addAnnotation: async (id: string, content: string, target?: Record<string, unknown>): Promise<Annotation> => {
    const r = await fetch(`${BASE}/${id}/annotation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, kind: 'user', author: 'user', target }),
    })
    return jsonOrThrow(r)
  },

  setTier: async (id: string, new_tier: MaterialTier): Promise<Material> => {
    const r = await fetch(`${BASE}/${id}/tier`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_tier, by: 'user' }),
    })
    return jsonOrThrow(r)
  },

  batchVerdict: async (ids: string[], verdict: MaterialStatus, reason = ''): Promise<{
    ok: boolean; changed_count: number; changed_ids: string[]; not_found: string[]; skipped: Array<Record<string, string>>
  }> => {
    const r = await fetch(`${BASE}/batch_verdict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, verdict, by: 'user', reason }),
    })
    return jsonOrThrow(r)
  },

  batchTier: async (ids: string[], new_tier: MaterialTier): Promise<{
    ok: boolean; changed_count: number; changed_ids: string[]; not_found: string[]; skipped: Array<Record<string, string>>
  }> => {
    const r = await fetch(`${BASE}/batch_tier`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, new_tier, by: 'user' }),
    })
    return jsonOrThrow(r)
  },

  batchDelete: async (ids: string[], includePending = false): Promise<{
    ok: boolean; deleted_count: number; deleted_ids: string[]; skipped_pending: number; not_found: string[]
  }> => {
    const r = await fetch(`${BASE}/batch_delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, include_pending: includePending }),
    })
    return jsonOrThrow(r)
  },

  remove: async (id: string): Promise<void> => {
    const r = await fetch(`${BASE}/${id}`, { method: 'DELETE' })
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  },

  /** 返回 inline_content 或文件内容 (image: binary blob URL; markdown/html/json: text). */
  capture: async (body: ReviewCaptureBody): Promise<Material> => {
    const r = await fetch(`${BASE}/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return jsonOrThrow(r)
  },

  /** #3f 把聊天里出现的文件路径变成审阅材料。严格匹配→matched+material; 否则→matched:false+candidates。 */
  fromPath: async (path: string, title?: string): Promise<{
    matched: boolean
    material?: Material
    candidates?: Array<{ path: string; rel: string; name: string }>
    query?: string
  }> => {
    const r = await fetch(`${BASE}/from_path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, title }),
    })
    return jsonOrThrow(r)
  },

  fileUrl: (id: string): string => `${BASE}/${id}/file`,

  /** 实时 WS 流. 返回 close fn. */
  openStream: (onEvent: (e: StreamEvent) => void, onError?: (e: Event) => void): () => void => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}${BASE}/stream`
    const ws = new WebSocket(url)
    let closed = false
    ws.onmessage = (ev) => {
      try {
        const parsed = JSON.parse(ev.data) as StreamEvent
        onEvent(parsed)
      } catch { /* ignore malformed */ }
    }
    ws.onerror = (ev) => onError?.(ev)
    ws.onclose = () => { closed = true }
    return () => { if (!closed) try { ws.close() } catch { /* */ } }
  },
}
