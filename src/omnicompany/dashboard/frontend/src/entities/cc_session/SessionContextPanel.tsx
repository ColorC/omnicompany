/**
 * Unified Session Context Panel — cc_session 跟 native session 共用 (S16 round 2 + S6 round 4).
 *
 * 三段折叠结构 (per user round 21 b 原话: "这部分统计界面请保持结构性"):
 *   1. 上下文  : active plan + plan_meta (work_type / standards / project / 退出条件) + cwd + agent state
 *   2. 修改记录: files edited + bash redirects (从 trace events 聚合)
 *   3. 新增产出: new worker / material files
 *
 * 数据源 by kind:
 *   - 'cc'    : ccApi.context(id)         → /api/cc/sessions/{id}/context
 *   - 'native': ideApi.context(traceId)   → /api/v2/ide/trace/{id}/context
 *
 * 两端 schema 完全对齐 (UnifiedSessionContext = ccClient.SessionContext = ideClient.SessionContext).
 *
 * Auto-refreshes every 5s while alive.
 */

import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ccApi, type ResolvedContextItem, type SessionContext as CcContext } from '../../api/ccClient'
import { ideApi, type SessionContext as IdeContext } from '../../api/ideClient'
import { usePanels } from '../../stores/panelsStore'
import { colors, fonts, fontSize, radius, spacing } from '../../shell/tokens'
import NotesForTarget from '../authored/NotesForTarget'

type UnifiedContext = CcContext | IdeContext

interface Props {
  sessionId: string
  alive: boolean  // poll faster when alive; static if dead
  kind?: 'cc' | 'native'  // 默认 cc (向后兼容 round 27 caller)
}

const S: Record<string, any> = {
  root: {
    width: 360, borderLeft: `1px solid ${colors.border}`,
    background: colors.bgPanel, color: colors.text, fontFamily: fonts.ui, fontSize: fontSize.body,
    overflow: 'auto', flexShrink: 0, height: '100%', letterSpacing: '-0.13px',
  },
  section: { borderBottom: `1px solid ${colors.border}` },
  sectionHeader: (open: boolean): React.CSSProperties => ({
    padding: `${spacing.sm}px ${spacing.md}px`, cursor: 'pointer', userSelect: 'none' as const,
    color: open ? colors.accent : colors.textMuted,
    fontSize: fontSize.body, fontWeight: 600 as const, textTransform: 'uppercase' as const,
    background: colors.bg, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    letterSpacing: '-0.11px',
  }),
  sectionBody: { padding: `${spacing.sm}px ${spacing.md}px` },
  kv: { display: 'flex', gap: spacing.sm, marginBottom: spacing.sm, alignItems: 'baseline' as const },
  k: { color: colors.textMuted, minWidth: 80, fontSize: fontSize.body, flexShrink: 0 },
  v: { color: colors.text, wordBreak: 'break-all' as const, fontSize: fontSize.body },
  vClickable: {
    color: colors.accent, cursor: 'pointer', textDecoration: 'underline dotted',
    wordBreak: 'break-all' as const, fontSize: fontSize.body,
  },
  empty: { color: colors.textMuted, fontSize: fontSize.caption },
  hint: { color: colors.textFaint, fontSize: fontSize.caption, lineHeight: 1.5 },
  fileRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
    padding: `${spacing.xs}px 0`, borderBottom: `1px solid ${colors.bgCard}`, gap: spacing.sm, fontSize: fontSize.body,
  },
  fileName: { color: colors.accent, cursor: 'pointer', overflow: 'hidden' as const, textOverflow: 'ellipsis' as const, whiteSpace: 'nowrap' as const, flex: 1, fontSize: fontSize.body },
  fileCount: { color: colors.textFaint, fontSize: fontSize.caption, flexShrink: 0 },
  contextRow: {
    padding: `${spacing.xs}px 0`, borderBottom: `1px solid ${colors.bgCard}`,
    display: 'grid', gridTemplateColumns: '1fr auto', gap: spacing.sm, alignItems: 'start',
  },
  contextPath: {
    color: colors.accent, cursor: 'pointer', overflow: 'hidden' as const,
    textOverflow: 'ellipsis' as const, whiteSpace: 'nowrap' as const,
    fontSize: fontSize.body, fontFamily: fonts.mono,
  },
  contextMeta: { color: colors.textFaint, fontSize: fontSize.caption, marginTop: 2, lineHeight: 1.4 },
  contextOpen: {
    background: colors.bgCard, color: colors.textMuted, border: `1px solid ${colors.border}`,
    borderRadius: radius.default, cursor: 'pointer', fontSize: fontSize.caption,
    padding: '2px 6px', fontFamily: fonts.ui,
  },
  badge: (color: string): React.CSSProperties => ({
    display: 'inline-block', padding: '2px 8px', borderRadius: radius.badges, fontSize: fontSize.caption,
    background: colors.bgCard, color, marginLeft: 4,
  }),
  refresh: {
    background: 'transparent', border: 'none', color: colors.textMuted,
    cursor: 'pointer', fontSize: fontSize.title, padding: 0,
  },
}

/** Strip leading repo prefix to keep file paths skimmable.
 *  兼容仓库改名 (omnicompany → omnicompany 2026-05-08): 匹配任一目录名 */
function shortPath(p: string): string {
  const m = p.match(/[\\/]omni(?:factory|company)[\\/](.+)$/)
  return m ? m[1].replace(/\\/g, '/') : p
}

function postToOmniHost(message: Record<string, unknown>): boolean {
  const payload = { __omnichat: true, ...message }
  let posted = false
  try {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(payload, '*')
      posted = true
    }
  } catch { /* browser fallback */ }
  try {
    if (window.top && window.top !== window && window.top !== window.parent) {
      window.top.postMessage(payload, '*')
      posted = true
    }
  } catch { /* browser fallback */ }
  return posted
}

function providerLabel(provider: string | null | undefined, kind: 'cc' | 'native'): string {
  if (kind === 'native') return 'Native Agent'
  if (provider === 'codex') return 'Codex'
  if (provider === 'omni_agent') return 'OmniAgent'
  if (provider === 'claude_code') return 'Claude Code'
  if (provider === 'chat') return 'OmniChat'
  return 'OmniChat'
}

function workerNoteId(filePath: string): string | null {
  // packages/<x>/<y>/workers/<name>.py is the worker source — there's no direct note,
  // but we can still surface the path. Returning null = sidebar will show plain text.
  // Future: register worker entity by absolute file_path lookup.
  return null
}

function pathToNoteId(filePath: string): string | null {
  // docs/foo/bar.md → foo/bar
  const m = filePath.match(/[\\/]docs[\\/](.+)\.md$/i)
  if (!m) return null
  return m[1].replace(/\\/g, '/')
}

const Section: React.FC<{ title: string; count?: number; children: React.ReactNode; defaultOpen?: boolean; testId?: string }> =
  ({ title, count, children, defaultOpen = true, testId }) => {
    const [open, setOpen] = useState(defaultOpen)
    return (
      <div style={S.section} data-ctx-section={testId}>
        <div style={S.sectionHeader(open)} onClick={() => setOpen(!open)}>
          <span>{open ? '▾' : '▸'} {title}{typeof count === 'number' && ` · ${count}`}</span>
        </div>
        {open && <div style={S.sectionBody}>{children}</div>}
      </div>
    )
  }


// ─── PlanPicker · 切 plan 按钮 + 下拉 (CC-PLAN-SESSION-CONTEXT 段三-2) ─────
//
// 点 "切" 展开下拉 → 列 /api/plans 非 archived plan, 按 date desc → 选中调
// ccApi.patchActivePlan → 后端写元数据 + 标记 active_plan_changed_ts → alive
// session 下条 turn UserPromptSubmit hook 重注入 plan_meta (b 方案).

interface PlanPickerProps {
  sessionId: string
  currentPlanId: string | null
  alive: boolean
  onChange: () => void
}

const _planListCache: { items: any[]; ts: number } = { items: [], ts: 0 }

const PlanPicker: React.FC<PlanPickerProps> = ({ sessionId, currentPlanId, alive, onChange }) => {
  const [open, setOpen] = useState(false)
  const [plans, setPlans] = useState<any[]>(_planListCache.items)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null) // plan_id being switched to
  const [toast, setToast] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  // Portal 渲下拉避免父级 overflow:auto 裁剪 — 用 fixed 定位锚到按钮
  const btnRef = useRef<HTMLButtonElement | null>(null)
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null)
  useEffect(() => {
    if (!open) { setAnchorRect(null); return }
    const update = () => { if (btnRef.current) setAnchorRect(btnRef.current.getBoundingClientRect()) }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [open])

  const loadPlans = async () => {
    if (Date.now() - _planListCache.ts < 30_000 && _planListCache.items.length > 0) {
      setPlans(_planListCache.items)
      return
    }
    setLoading(true); setError(null)
    try {
      const r = await fetch('/api/plans')
      if (!r.ok) throw new Error(`${r.status}`)
      const d = await r.json() as { items: any[] }
      const items = (d.items || []).filter((p) => !p.archived && p.has_plan_md)
      // sort by date desc (matches CLI omni plan list default)
      items.sort((a, b) => (b.date || '').localeCompare(a.date || ''))
      _planListCache.items = items; _planListCache.ts = Date.now()
      setPlans(items)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const onToggle = () => {
    const next = !open
    setOpen(next); setError(null); setToast(null); setFilter('')
    if (next) loadPlans()
  }

  const onSwitch = async (planId: string | null) => {
    setBusy(planId || '__unbind__'); setError(null)
    try {
      const res = await ccApi.patchActivePlan(sessionId, planId)
      onChange()
      const verb = planId ? '切到' : '解绑'
      const when = res.alive ? '下条 turn 自动注入' : '已生效'
      setToast(`${verb} ${planId ? planId.split('/').pop() : '(无)'} · ${when}`)
      setOpen(false)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  const filtered = plans.filter((p) => {
    if (!filter) return true
    const q = filter.toLowerCase()
    return p.id.toLowerCase().includes(q) || (p.topic || '').toLowerCase().includes(q)
  })

  return (
    <span style={{ display: 'inline-block', marginLeft: 8, position: 'relative' }}>
      <button
        ref={btnRef}
        onClick={onToggle}
        data-plan-picker-toggle
        title={alive ? '切 plan (下条 turn 自动注入新 plan_meta)' : '切 plan (立即生效)'}
        style={{
          padding: '2px 10px', fontSize: fontSize.body, fontFamily: fonts.ui,
          background: open ? colors.bgCard : colors.bgOverlay,
          color: colors.accent,
          border: `1px solid ${colors.border}`, borderRadius: radius.default, cursor: 'pointer',
        }}
      >
        切{open ? ' ▴' : ' ▾'}
      </button>
      {toast && (
        <div data-plan-picker-toast style={{
          position: 'absolute', top: '100%', left: 0, marginTop: 4, zIndex: 10,
          padding: '4px 8px', background: '#0a1a0a', color: colors.success,
          border: `1px solid ${colors.border}`, borderRadius: radius.default, fontSize: fontSize.body, whiteSpace: 'nowrap' as const,
          maxWidth: 320,
        }}>
          ✓ {toast}
        </div>
      )}
      {open && anchorRect && createPortal(
        <div data-plan-picker-dropdown style={{
          position: 'fixed',
          // 锚到按钮下方右对齐, 不被父级 overflow 裁
          top: Math.min(anchorRect.bottom + 4, window.innerHeight - 420),
          right: Math.max(8, window.innerWidth - anchorRect.right),
          zIndex: 10000,
          minWidth: 340, maxWidth: 440, maxHeight: 420, overflow: 'auto',
          background: colors.bgPanel, border: `1px solid ${colors.border}`, borderRadius: radius.default,
          padding: spacing.sm, boxShadow: 'rgba(8,9,10,0.6) 0px 4px 32px 0px',
          fontFamily: fonts.ui,
        }}>
          <input
            type="text" placeholder="过滤 plan id / topic..."
            value={filter} onChange={(e) => setFilter(e.target.value)}
            autoFocus
            style={{
              width: '100%', padding: '6px 10px', marginBottom: spacing.xs, boxSizing: 'border-box' as const,
              background: colors.bgCard, color: colors.text, border: `1px solid ${colors.border}`,
              borderRadius: radius.default, fontSize: fontSize.body, fontFamily: fonts.ui,
            }}
          />
          {error && <div style={{ color: colors.warning, fontSize: fontSize.body, padding: spacing.xs }}>err: {error}</div>}
          {loading && <div style={{ color: colors.textMuted, fontSize: fontSize.body, padding: spacing.xs }}>loading…</div>}
          {currentPlanId && (
            <button
              onClick={() => onSwitch(null)} disabled={busy !== null}
              data-plan-picker-unbind
              style={{
                width: '100%', textAlign: 'left' as const, padding: '6px 10px', marginBottom: spacing.xs,
                background: '#1a0a0a', color: colors.warning, border: `1px solid ${colors.border}`,
                borderRadius: radius.default, cursor: 'pointer', fontSize: fontSize.body, fontFamily: fonts.ui,
              }}
            >
              {busy === '__unbind__' ? '⟳' : '⊘'} 解绑 (active_plan = null)
            </button>
          )}
          {filtered.length === 0 && !loading && (
            <div style={{ color: colors.textMuted, fontSize: fontSize.body, padding: spacing.xs }}>(无可选 plan)</div>
          )}
          {(() => {
            // 按 category 分组
            const groups: Record<string, typeof filtered> = {}
            for (const p of filtered) {
              const cat = p.category || '(未分类)'
              ;(groups[cat] ||= []).push(p)
            }
            const sortedCats = Object.keys(groups).sort()
            return sortedCats.map((cat) => (
              <div key={cat} style={{ marginBottom: 4 }}>
                <div style={{
                  padding: `${spacing.xs}px ${spacing.sm}px`, fontSize: fontSize.caption, color: colors.violet, fontWeight: 600,
                  borderBottom: `1px solid ${colors.border}`, marginBottom: 2,
                  position: 'sticky' as const, top: 0, background: colors.bgPanel, zIndex: 1,
                }}>
                  {cat}
                </div>
                {groups[cat].map((p) => {
                  const isCurrent = p.id === currentPlanId
                  return (
                    <button
                      key={p.id}
                      onClick={() => !isCurrent && onSwitch(p.id)}
                      disabled={isCurrent || busy !== null}
                      data-plan-picker-option={p.id}
                      title={p.id}
                      style={{
                        display: 'block', width: '100%', textAlign: 'left' as const,
                        padding: `${spacing.xs}px ${spacing.sm}px ${spacing.xs}px ${spacing.md}px`, marginBottom: 1,
                        background: isCurrent ? colors.bgCard : 'transparent',
                        color: isCurrent ? colors.accent : colors.text,
                        border: '1px solid', borderColor: isCurrent ? colors.border : 'transparent',
                        borderRadius: radius.default, cursor: isCurrent ? 'default' : 'pointer',
                        fontSize: fontSize.body, fontFamily: fonts.ui,
                        overflow: 'hidden' as const, textOverflow: 'ellipsis' as const, whiteSpace: 'nowrap' as const,
                      }}
                    >
                      {busy === p.id ? '⟳ ' : ''}
                      {isCurrent && '● '}
                      <span style={{ color: colors.textFaint }}>{p.date}</span>{' '}
                      <span style={{ fontWeight: isCurrent ? 600 as const : 400 as const }}>{p.topic}</span>
                      {p.meta?.work_type && (
                        <span style={{ marginLeft: 6, color: colors.violet, fontSize: fontSize.caption }}>· {p.meta.work_type}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            ))
          })()}
          <div style={{ marginTop: spacing.xs, padding: spacing.xs, color: colors.textFaint, fontSize: fontSize.caption, borderTop: `1px solid ${colors.border}` }}>
            {alive
              ? 'alive 进程: 切完后下条 turn 自动注入 (b 方案, 不破缓存)'
              : '已结束 session: 立即写入 (resume 时生效)'}
          </div>
        </div>,
        document.body
      )}
    </span>
  )
}

export default function SessionContextPanel({ sessionId, alive, kind = 'cc' }: Props) {
  const [ctx, setCtx] = useState<UnifiedContext | null>(null)
  const [error, setError] = useState<string | null>(null)
  const openTab = usePanels((s) => s.openTab)

  const reload = React.useCallback(() => {
    const fetcher = kind === 'native'
      ? ideApi.context(sessionId)
      : ccApi.context(sessionId)
    fetcher.then(setCtx).catch((e) => setError(String(e)))
  }, [sessionId, kind])

  useEffect(() => {
    setCtx(null); setError(null)
    reload()
  }, [sessionId, reload])

  // Poll while alive (5s); pause when session dead
  useEffect(() => {
    if (!alive) return
    const id = window.setInterval(reload, 5000)
    return () => window.clearInterval(id)
  }, [alive, reload])

  if (error) return <div style={{ ...S.root, padding: spacing.lg, color: '#ef5350' }}>{error}</div>
  if (!ctx) return <div style={{ ...S.root, padding: spacing.lg, color: colors.textFaint }}>loading…</div>

  const c = ctx.context
  // 上下文真信息源 = plan.md frontmatter (plan-level) + project.md frontmatter (project-level)
  const planMeta: Record<string, any> = (c as any).plan_meta || {}
  const projectMeta: Record<string, any> = (c as any).project_meta || {}
  const userCtx = c.user_context || {}
  const resolvedContext = (c as any).resolved_context
  const workType = planMeta.work_type || userCtx.work_type
  const standards: string[] = planMeta.standards || userCtx.standards || []
  const project: string | undefined = planMeta.project
  const exitCriteria: string[] = planMeta.exit_criteria || []
  const projectVision: string[] = projectMeta.vision || []
  const projectExitCriteria: string[] = projectMeta.exit_criteria || []
  const agentState = (c as any).agent_state || (kind === 'cc' ? 'cc-session' : 'native-session')
  const provider = (c as any).provider as string | null | undefined
  const providerName = providerLabel(provider, kind)

  const openPlan = () => {
    if (c.active_plan) openTab({ type: 'plan', id: c.active_plan }, c.active_plan.split('/').pop() || c.active_plan)
  }
  const openNoteIfMd = (filePath: string) => {
    const id = pathToNoteId(filePath)
    if (id) openTab({ type: 'note', id }, id.split('/').pop() || id)
  }
  const openContextTarget = (item: ResolvedContextItem) => {
    const target = item.dashboard_target
    if (target?.type === 'plan') {
      openTab({ type: 'plan', id: target.id }, target.id.split('/').pop() || target.id)
      return
    }
    if (target?.type === 'note') {
      openTab({ type: 'note', id: target.id }, target.id.split('/').pop() || target.id)
      return
    }
    const path = item.abs_path || item.path
    if (postToOmniHost({ type: 'open-file', path })) return
    if (item.vscode_uri) {
      window.open(item.vscode_uri, '_blank', 'noopener,noreferrer')
    }
  }
  const openContextInVscode = (item: ResolvedContextItem) => {
    const path = item.abs_path || item.path
    if (postToOmniHost({ type: 'open-file', path })) return
    if (item.vscode_uri) {
      window.open(item.vscode_uri, '_blank', 'noopener,noreferrer')
    }
  }

  return (
    <div style={S.root} data-session-context-panel data-session-id={sessionId} data-session-kind={kind}>
      <div style={{ ...S.sectionHeader(true), borderBottom: `1px solid ${colors.border}`, justifyContent: 'space-between' }}>
        <span>会话上下文 · {providerName}</span>
        <button style={S.refresh} title="刷新" onClick={reload}>↻</button>
      </div>

      {/* ── 上下文 ─────────────────────────────────────────── */}
      <Section title="上下文" testId="context">
        <div style={S.kv}>
          <span style={S.k}>state</span>
          <span style={S.v}>{agentState}</span>
        </div>
        <div style={S.kv}>
          <span style={S.k}>active plan</span>
          <span style={S.v}>
            {c.active_plan
              ? <span style={S.vClickable} data-ctx-active-plan onClick={openPlan}>{c.active_plan}</span>
              : <span style={S.empty}>(未关联)</span>}
            {kind === 'cc' && (
              <PlanPicker
                sessionId={sessionId}
                currentPlanId={c.active_plan || null}
                alive={alive}
                onChange={() => reload()}
              />
            )}
          </span>
        </div>
        <div style={S.kv}>
          <span style={S.k}>cwd</span>
          <span style={S.v} data-ctx-cwd title={c.cwd || ''}>{c.cwd ? shortPath(c.cwd) : '?'}</span>
        </div>
        {c.claude_session_id && (
          <div style={S.kv}>
            <span style={S.k}>claude id</span>
            <span style={S.v} title={c.claude_session_id}>{c.claude_session_id.slice(0, 12)}…</span>
          </div>
        )}
        {project && (
          <div style={S.kv}>
            <span style={S.k}>project</span>
            <span style={S.v}>{project}</span>
          </div>
        )}
        <div style={S.kv}>
          <span style={S.k}>work type</span>
          <span style={S.v}>{workType || <span style={S.empty}>(plan 未设)</span>}</span>
        </div>
        <div style={S.kv}>
          <span style={S.k}>standards</span>
          <span style={S.v}>
            {standards.length > 0
              ? standards.map((s, i) => <span key={i} style={S.badge('#9575cd')}>{s}</span>)
              : <span style={S.empty}>(plan 未列)</span>}
          </span>
        </div>
        {exitCriteria.length > 0 && (
          <div style={S.kv}>
            <span style={S.k}>退出条件</span>
            <span style={S.v}>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {exitCriteria.map((e, i) => <li key={i} style={{ fontSize: 14 }}>{e}</li>)}
              </ul>
            </span>
          </div>
        )}
        {/* native 专有: model / turn / token 用量 */}
        {kind === 'native' && (ctx as any).stats && (
          <>
            <div style={S.kv}>
              <span style={S.k}>model</span>
              <span style={S.v}>{(ctx as any).stats.model || <span style={S.empty}>(未跑)</span>}</span>
            </div>
            <div style={S.kv}>
              <span style={S.k}>turn</span>
              <span style={S.v}>{(ctx as any).stats.turn_count}</span>
            </div>
            <div style={S.kv}>
              <span style={S.k}>tokens</span>
              <span style={S.v}>
                {(ctx as any).stats.total_tokens.toLocaleString()}
                <span style={{ color: colors.textFaint, fontSize: 14, marginLeft: 6 }}>
                  ({(ctx as any).stats.input_tokens.toLocaleString()} in / {(ctx as any).stats.output_tokens.toLocaleString()} out)
                </span>
              </span>
            </div>
          </>
        )}
        <div style={{ ...S.hint, marginTop: 8 }}>
          字段值来自 plan.md 顶部 frontmatter (work_type / standards / project / exit_criteria) — 编辑 plan.md 即改值, 无私有 user_context
        </div>
      </Section>

      {/* ── 札记 (针对本会话的评论/草稿, 中心 store 回显) ──────────── */}
      <Section title="札记" defaultOpen={false} testId="authored">
        <NotesForTarget
          kind="llm_session"
          id={sessionId}
          title={(c.active_plan && c.active_plan.split('/').pop()) || sessionId.slice(0, 12)}
        />
      </Section>

      {/* ── 渐进上下文注入包 ─────────────────────────────────── */}
      {resolvedContext && (
        <Section
          title="注入上下文"
          count={resolvedContext.total || 0}
          defaultOpen={true}
          testId="progressive-context"
        >
          <div style={S.kv}>
            <span style={S.k}>resolver</span>
            <span style={S.v}>
              omni context resolve
              {resolvedContext.missing_total ? (
                <span style={S.badge(colors.warning)}>missing {resolvedContext.missing_total}</span>
              ) : (
                <span style={S.badge(colors.success)}>ok</span>
              )}
            </span>
          </div>
          {resolvedContext.error && (
            <div style={{ color: colors.warning, fontSize: fontSize.caption, marginBottom: spacing.sm }}>
              {resolvedContext.error}
            </div>
          )}
          {(resolvedContext.contexts || []).slice(0, 80).map((item: ResolvedContextItem) => (
            <div key={`${item.path}:${item.source}:${item.reason}`} style={S.contextRow} data-ctx-context-path={item.path}>
              <div style={{ minWidth: 0 }}>
                <div
                  style={S.contextPath}
                  title={`${item.path}\n${item.reason || ''}`}
                  onClick={() => openContextTarget(item)}
                >
                  {item.path}
                </div>
                <div style={S.contextMeta}>
                  {item.category || 'context'} · {item.source || 'resolver'}
                  {item.reason ? ` · ${item.reason}` : ''}
                </div>
              </div>
              <button
                type="button"
                style={S.contextOpen}
                title="在 VS Code / 宿主编辑器中打开"
                onClick={() => openContextInVscode(item)}
                data-ctx-open-vscode
              >
                VS
              </button>
            </div>
          ))}
          {(resolvedContext.contexts || []).length > 80 && (
            <div style={S.empty}>+{resolvedContext.contexts.length - 80} more …</div>
          )}
          <div style={{ ...S.hint, marginTop: 8 }}>
            点击 markdown/plan 路径会在网页内打开；VS 按钮会走 VS Code host bridge，浏览器环境 fallback 到 vscode://file 链接。
          </div>
        </Section>
      )}

      {/* ── project 上下文 (立于 plan 之上, 含 vision + 退出条件) ─────── */}
      {(projectVision.length > 0 || projectExitCriteria.length > 0) && (
        <Section title={`Project · ${project || '?'}`} testId="project">
          {projectVision.length > 0 && (
            <div style={S.kv}>
              <span style={S.k}>vision</span>
              <span style={S.v}>
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {projectVision.map((v, i) => <li key={i} style={{ fontSize: 14 }}>{v}</li>)}
                </ul>
              </span>
            </div>
          )}
          {projectExitCriteria.length > 0 && (
            <div style={S.kv}>
              <span style={S.k}>退出条件 (project)</span>
              <span style={S.v}>
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {projectExitCriteria.map((e, i) => <li key={i} style={{ fontSize: 14 }}>{e}</li>)}
                </ul>
              </span>
            </div>
          )}
          <div style={{ ...S.hint, marginTop: 8 }}>
            来自 docs/plans/{project ? `${planMeta.project ? '<category>/' + project : project}` : '?'}/project.md frontmatter — 立于 plan 之上, 跨 plan 共享 vision + 退出条件
          </div>
        </Section>
      )}

      {/* ── 修改记录 ───────────────────────────────────────── */}
      <Section
        title="修改记录"
        count={ctx.modified_files.length}
        defaultOpen={ctx.modified_files.length > 0}
        testId="modified"
      >
        {ctx.modified_files.length === 0
          ? <span style={S.empty}>本会话未修改任何文件</span>
          : ctx.modified_files.slice(0, 50).map((f) => {
              const md = pathToNoteId(f.path)
              return (
                <div key={f.path} style={S.fileRow} data-ctx-modified={f.path}>
                  <span
                    style={md ? S.fileName : { ...S.fileName, color: colors.text, cursor: 'default' }}
                    title={`${f.path}\n${f.last_tool} · last ${f.last_ts}`}
                    onClick={() => openNoteIfMd(f.path)}
                  >
                    {shortPath(f.path)}
                  </span>
                  <span style={S.fileCount}>×{f.count}</span>
                </div>
              )
            })
        }
        {ctx.modified_files.length > 50 && (
          <div style={S.empty}>+{ctx.modified_files.length - 50} more …</div>
        )}
        {ctx.bash_writes.length > 0 && (
          <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px dashed #1a1a1a' }}>
            <div style={{ ...S.empty, marginBottom: 4 }}>bash 写入 ({ctx.bash_writes.length})</div>
            {ctx.bash_writes.slice(0, 10).map((b, i) => (
              <div key={i} style={S.fileRow} data-ctx-bash-write>
                <span style={{ color: '#ffb74d', fontSize: 14 }} title={b.snippet}>{shortPath(b.path)}</span>
                <span style={S.fileCount}>{b.ts.slice(11, 19)}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* ── 新增产出 (worker/material) ──────────────────────── */}
      <Section
        title="新增产出"
        count={ctx.added_workers.length + ctx.added_materials.length}
        defaultOpen={(ctx.added_workers.length + ctx.added_materials.length) > 0}
        testId="added"
      >
        {ctx.added_workers.length === 0 && ctx.added_materials.length === 0 && (
          <span style={S.empty}>未添加 worker / material</span>
        )}
        {ctx.added_workers.length > 0 && (
          <div style={{ marginBottom: 6 }}>
            <div style={{ ...S.empty, color: '#90caf9', marginBottom: 2 }}>worker / team</div>
            {ctx.added_workers.map((p) => (
              <div key={p} style={S.fileRow} data-ctx-added-worker>
                <span style={S.fileName} title={p}>{shortPath(p)}</span>
              </div>
            ))}
          </div>
        )}
        {ctx.added_materials.length > 0 && (
          <div>
            <div style={{ ...S.empty, color: '#9575cd', marginBottom: 2 }}>material</div>
            {ctx.added_materials.map((p) => (
              <div key={p} style={S.fileRow} data-ctx-added-material>
                <span style={S.fileName} title={p}>{shortPath(p)}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <div style={{ ...S.empty, padding: spacing.md, textAlign: 'center' as const }}>
        共 {ctx.event_count} 个 trace 事件
      </div>
    </div>
  )
}
