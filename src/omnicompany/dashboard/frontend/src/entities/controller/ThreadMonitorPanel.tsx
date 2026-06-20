import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ccApi, type CcSessionMeta } from '../../api/ccClient'
import { ccChatApi, type CcChatSessionMeta, type CcChatProvider, type ImportableSession } from '../../api/ccChatClient'
import { usePanels } from '../../stores/panelsStore'
import { useControllerView } from './index'
import { relTimeEn as relTime } from '../../lib/time'
import { openChatInVscode } from '../../lib/surface'

// 新建会话时可选的执行者。总控(controller)走 BOSS SIGHT 总控;其余是 subagent。
const PROVIDER_OPTIONS: Array<{ value: CcChatProvider; label: string }> = [
  { value: 'claude_code', label: 'Claude Code' },
  { value: 'codex', label: 'Codex' },
  { value: 'omni_agent', label: 'OmniAgent' },
  { value: 'controller', label: '总控' },
]

type ThreadRow =
  | { kind: 'chat'; id: string; title: string; provider: string; status: string; activePlan: string | null; startedAt: number; lastMessage?: string }
  | { kind: 'pty'; id: string; title: string; provider: string; status: string; activePlan: string | null; startedAt: number; lastMessage?: string }

const S: Record<string, any> = {
  root: { borderTop: '1px solid #1f2937', paddingTop: 12, marginTop: 12 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 8 },
  title: { color: '#9fd0ff', fontSize: 15, fontWeight: 700 },
  button: { border: '1px solid #2f81f7', background: '#1f6feb', color: '#fff', borderRadius: 4, padding: '5px 9px', cursor: 'pointer', fontSize: 14 },
  ghostButton: { border: '1px solid #2b3a49', background: '#101820', color: '#b7c8d9', borderRadius: 4, padding: '5px 9px', cursor: 'pointer', fontSize: 14 },
  controls: { display: 'flex', alignItems: 'center', gap: 6 },
  select: { height: 28, border: '1px solid #263443', background: '#080b0e', color: '#d7dee7', borderRadius: 4, padding: '0 6px', fontSize: 14 },
  list: { display: 'grid', gap: 8 },
  row: { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 10, alignItems: 'center', background: '#0f1720', border: '1px solid #263443', borderRadius: 6, padding: 10 },
  rowTitle: { color: '#e6edf3', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  meta: { color: '#8b949e', fontSize: 14, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  badge: { display: 'inline-block', color: '#7ee787', background: '#10251a', border: '1px solid #214f32', borderRadius: 4, padding: '1px 5px', marginRight: 6, fontSize: 14 },
  empty: { color: '#8b949e', padding: 10, border: '1px dashed #263443', borderRadius: 6 },
  error: { color: '#ff7b72' },
  modalBackdrop: { position: 'fixed', zIndex: 90, inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 },
  modal: { width: 'min(680px, 100%)', maxHeight: '80vh', display: 'flex', flexDirection: 'column', border: '1px solid #263443', borderRadius: 8, background: '#0c1116', color: '#d7dee7', boxShadow: '0 24px 70px rgba(0,0,0,.55)', padding: 14 },
  modalHead: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 6 },
  modalList: { overflow: 'auto', display: 'grid', gap: 6, marginTop: 8 },
  importRow: { display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 10, alignItems: 'center', border: '1px solid #263443', borderRadius: 6, padding: '8px 10px' },
  providerTag: (codex: boolean): React.CSSProperties => ({ display: 'inline-block', fontSize: 14, borderRadius: 4, padding: '1px 5px', marginRight: 6, color: codex ? '#f0c674' : '#79c0ff', background: codex ? '#231c0b' : '#10233a', border: `1px solid ${codex ? '#5c4a1f' : '#234563'}` }),
}

function planShortName(planId: string | null | undefined): string {
  if (!planId) return 'no-plan'
  const last = planId.split('/').pop() || planId
  return last.replace(/^\[\d{4}-\d{2}-\d{2}\]/, '')
}

// 多 agent 完成感知(后端 /active 的 status): 一眼看出每个 agent 在跑还是干完了。
const RUN_STATUS: Record<string, { label: string; color: string; bg: string; border: string }> = {
  working: { label: '运行中', color: '#f0b429', bg: '#241d0b', border: '#5c4a1f' },
  done: { label: '已完成', color: '#3fb950', bg: '#0d1a13', border: '#214f32' },
  waiting: { label: '等待输入', color: '#79c0ff', bg: '#10233a', border: '#234563' },
  idle: { label: '空闲', color: '#8b949e', bg: '#161b22', border: '#30363d' },
}

function StatusBadge({ status }: { status?: string }) {
  const m = RUN_STATUS[status || 'idle'] || RUN_STATUS.idle
  return (
    <span style={{ display: 'inline-block', fontSize: 13, borderRadius: 4, padding: '1px 6px', marginRight: 6, color: m.color, background: m.bg, border: `1px solid ${m.border}` }} data-testid="run-status" data-status={status || 'idle'}>
      {status === 'working' ? '● ' : ''}{m.label}
    </span>
  )
}

function chatToRow(m: CcChatSessionMeta): ThreadRow {
  const title = `${planShortName(m.active_plan)} · chat · ${m.id.slice(-6)}`
  return {
    kind: 'chat',
    id: m.id,
    title,
    provider: m.provider || 'claude_code',
    status: m.status || (m.alive ? 'alive' : 'ended'),
    activePlan: m.active_plan,
    startedAt: m.started_at,
    lastMessage: m.last_message || m.first_message,
  }
}

function ptyToRow(m: CcSessionMeta): ThreadRow {
  const status = m.status || (m.alive ? 'alive' : 'recoverable')
  const title = `${planShortName(m.active_plan)} · pty · ${m.id.slice(0, 8)}`
  return {
    kind: 'pty',
    id: m.id,
    title,
    provider: 'claude_code',
    status,
    activePlan: m.active_plan || null,
    startedAt: m.started_at,
  }
}

export default function ThreadMonitorPanel() {
  const [threads, setThreads] = useState<ThreadRow[]>([])
  const [activeSessions, setActiveSessions] = useState<ImportableSession[]>([])
  // 驾驶舱自管会话按 claude_session_id 并进同一对话列表 —— 让它们也带摘要/项目/状态,
  // 而不是被去重踢到下面那个裸 hash 列表(用户 2026-06-13: 新建的对话在主列表里看不到)。
  const [omniByClaudeSid, setOmniByClaudeSid] = useState<Map<string, CcChatSessionMeta>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [newProvider, setNewProvider] = useState<CcChatProvider>('claude_code')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  // #2 载入已有会话(Claude Code / Codex)。
  const [importOpen, setImportOpen] = useState(false)
  const [importItems, setImportItems] = useState<ImportableSession[]>([])
  const [importLoading, setImportLoading] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [importingId, setImportingId] = useState<string | null>(null)
  const [adoptingId, setAdoptingId] = useState<string | null>(null)
  const [loadNote, setLoadNote] = useState<string | null>(null)
  const openTab = usePanels((s) => s.openTab)
  // 窄窗口(vscode 侧边栏)适配: 容器宽度 < 360 视为窄, 用 compact 驱动样式(按钮换行/行单列/隐藏长说明)。
  const rootRef = useRef<HTMLDivElement>(null)
  const [compact, setCompact] = useState(false)
  useEffect(() => {
    const el = rootRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((es) => setCompact(es[0].contentRect.width < 360))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const runningCount = useMemo(() => activeSessions.filter((a) => a.status === 'working').length, [activeSessions])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [chat, pty, active] = await Promise.all([
        ccChatApi.list({ limit: 80, includeArchived: false }).catch(() => [] as CcChatSessionMeta[]),
        ccApi.list().catch(() => [] as CcSessionMeta[]),
        ccChatApi.activeSessions(7 * 86400, 80).catch(() => [] as ImportableSession[]),
      ])
      // claude_session_id → 自管 chat 会话(渲染时拿权威 plan + 自管 id 供"打开")
      const omniMap = new Map<string, CcChatSessionMeta>()
      for (const c of chat) { if (c.claude_session_id) omniMap.set(c.claude_session_id, c) }
      setOmniByClaudeSid(omniMap)
      // 统一对话列表 = 所有有 transcript 的对话(自管 + 外部), /active 已按最近活动排好序。
      // 自管会话的 transcript 也在 ~/.claude/projects, 一样被 /active 摘要, 所以不再过滤掉它们。
      setActiveSessions(active)
      // 线程列表只留"还没 transcript"的(全新没说话的 chat / pty), 避免和上面重复。
      const activeSids = new Set(active.map((a) => a.session_id))
      const hasTranscript = (sid: string | null | undefined) => Boolean(sid && activeSids.has(sid))
      const rows = [
        ...chat.filter((c) => !hasTranscript(c.claude_session_id)).map(chatToRow),
        ...pty.filter((p) => !hasTranscript((p as any).claude_session_id)).map(ptyToRow),
      ].sort((a, b) => b.startedAt - a.startedAt)
      setThreads(rows)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  function openThread(thread: ThreadRow) {
    openTab({ type: 'cc_session', id: thread.id }, thread.title)
  }

  async function onCreate() {
    setCreating(true)
    setCreateError(null)
    try {
      const m = await ccChatApi.create({ provider: newProvider })
      openTab({ type: 'cc_session', id: m.id }, `${planShortName(m.active_plan)} · chat · ${m.id.slice(-6)}`)
      await load()
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e))
    } finally {
      setCreating(false)
    }
  }

  async function openImport() {
    setImportOpen(true)
    setImportLoading(true)
    setImportError(null)
    try {
      setImportItems(await ccChatApi.importable(40))
    } catch (e) {
      setImportError(e instanceof Error ? e.message : String(e))
    } finally {
      setImportLoading(false)
    }
  }

  // A1(用户明示 2026-06-06): "载入"= 把这段已有对话的真实内容作为【总控对话的前文】注入,
  // 不是另起一个会话(那样既看不到真实历史, 外部会话还常 resume 失败)。
  async function onImport(item: ImportableSession) {
    setImportingId(item.session_id)
    setImportError(null)
    setLoadNote(null)
    try {
      const res = await ccChatApi.loadContext(item)
      if (!res.ok) {
        setImportError(
          res.reason === 'no_active_controller'
            ? '没有活跃的总控会话 —— 先打开"总控对话"再载入。'
            : `载入失败: ${res.reason || '未知原因'}`,
        )
        return
      }
      setImportOpen(false)
      // 切到总控对话, 让用户看到载入的前文 + 总控的简短确认。
      useControllerView.getState().setView('chat')
      openTab({ type: 'controller', id: 'main' }, '总控')
      setLoadNote(
        `已把这段对话(${res.message_count ?? 0} 条)载入为总控前文${res.truncated ? '(内容较长, 已截断尾部)' : ''} —— 在总控对话里可见`,
      )
    } catch (e) {
      setImportError(e instanceof Error ? e.message : String(e))
    } finally {
      setImportingId(null)
    }
  }

  // #2 接管式采纳: resume 这段别处会话当 subagent(总控可驱动/你可接管), 打开成 chat 页签。
  async function onAdopt(item: ImportableSession) {
    setAdoptingId(item.session_id)
    setError(null)
    try {
      const m = await ccChatApi.create({ adopt_session_id: item.session_id, provider: item.provider, cwd: item.cwd })
      openTab({ type: 'cc_session', id: m.id }, `采纳 · ${item.provider === 'codex' ? 'Codex' : 'Claude'} · ${item.session_id.slice(0, 6)}`)
    } catch (e) {
      setError(`采纳失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setAdoptingId(null)
    }
  }

  return (
    <div ref={rootRef} style={S.root} data-testid="thread-monitor-panel">
      <div style={{ ...S.header, ...(compact ? { flexDirection: 'column', alignItems: 'stretch', gap: 6 } : {}) }}>
        <div>
          <div style={S.title}>执行者 · 线程监视</div>
          <div style={S.meta}>{activeSessions.length + threads.length} 个对话 · {runningCount} 运行中{compact ? '' : ' · UI 关闭不终止后台会话'}</div>
        </div>
        <div style={{ ...S.controls, ...(compact ? { flexWrap: 'wrap' } : {}) }}>
          <select
            style={S.select}
            value={newProvider}
            onChange={(e) => setNewProvider(e.target.value as CcChatProvider)}
            data-testid="thread-new-provider"
            aria-label="选择执行者"
          >
            {PROVIDER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button type="button" style={S.button} onClick={() => { void onCreate() }} disabled={creating} data-testid="thread-new-session">
            {creating ? '新建中…' : '+ 新建会话'}
          </button>
          <button type="button" style={S.ghostButton} onClick={() => { void openImport() }} data-testid="thread-import-session">载入对话为前文</button>
          <button type="button" style={S.ghostButton} onClick={load}>刷新</button>
        </div>
      </div>
      {createError && <div style={S.error}>{createError}</div>}
      {error && <div style={S.error}>{error}</div>}
      {/* #1 修复: 载入错误以前只在弹窗里显示, 这里(其他目录的对话)点"载入"出错被吞掉了 → 看着像没反应。现在两处都显示。 */}
      {importError && <div style={S.error} data-testid="import-error">{importError}</div>}
      {loadNote && <div style={{ ...S.meta, color: '#7ee787' }} data-testid="load-note">{loadNote}</div>}
      {activeSessions.length > 0 && (
        <div style={{ marginBottom: 12 }} data-testid="active-sessions">
          <div style={{ ...S.meta, color: '#7ee787', marginBottom: 6 }}>
            对话 · 按最近活动 ({activeSessions.length}){!compact && <span style={{ color: '#8b949e' }}> · 「本舱」=驾驶舱里建的, 点「打开」回页签 · 别处的「采纳」接管或「载入」喂总控</span>}
          </div>
          <div style={S.list}>
            {activeSessions.map((it) => {
              const fresh = (Date.now() / 1000 - (it.mtime || 0)) < 86400
              const omni = omniByClaudeSid.get(it.session_id)
              const planLabel = omni?.active_plan
                ? planShortName(omni.active_plan)
                : (it.digest?.plan && it.digest.plan !== '无' ? it.digest.plan : '')
              return (
                <div key={`act-${it.provider}-${it.session_id}-${it.file}`} style={{ ...S.row, ...(compact ? { gridTemplateColumns: '1fr' } : {}), ...(fresh ? { borderColor: '#27553a', background: '#0d1a13' } : {}) }} data-testid="active-session-row" data-fresh={fresh ? '1' : '0'} data-owned={omni ? '1' : '0'}>
                  <div style={{ minWidth: 0 }}>
                    <div style={S.rowTitle}>
                      <StatusBadge status={it.status} />
                      {omni && <span style={{ display: 'inline-block', fontSize: 13, borderRadius: 4, padding: '1px 5px', marginRight: 6, color: '#d2a8ff', background: '#1d1530', border: '1px solid #3c2d63' }}>本舱</span>}
                      <span style={S.providerTag(it.provider === 'codex')}>{it.provider === 'codex' ? 'Codex' : 'Claude'}</span>
                      {it.digest?.title || it.preview || it.session_id}
                    </div>
                    {(it.digest?.project || planLabel) && (
                      <div style={{ ...S.meta, color: '#9fd0ff' }} data-testid="active-session-project">
                        📁 {it.digest?.project || '—'}{planLabel ? ` · 计划: ${planLabel}` : ''}
                      </div>
                    )}
                    <div style={{ ...S.meta, color: '#adbac7' }} data-testid="active-session-did" title={it.digest?.last_step || it.last_did || ''}>
                      {it.status === 'working' ? '正在做: ' : '最近一步: '}{it.digest?.last_step || it.last_did || '—'}
                    </div>
                    <div style={S.meta}>{it.cwd || '(未知目录)'} · {relTime(it.mtime)} · {it.session_id.slice(0, 12)}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0, ...(compact ? { flexWrap: 'wrap', flexShrink: 1, paddingTop: 6 } : {}) }}>
                    {/* 在 VSCode 打开此对话(2026-06-14 用户#4): claude→Claude Code(插件/CLI), codex→PowerShell codex resume --yolo */}
                    <button type="button" style={S.ghostButton} data-testid="active-session-open-vscode"
                      title={`在 VSCode 打开(${it.provider === 'codex' ? 'PowerShell: codex resume --yolo' : 'Claude Code'})`}
                      onClick={() => openChatInVscode(it.provider, it.cwd, it.session_id)}>
                      <span style={{ color: '#0098FF', fontWeight: 700 }}>VS</span>
                    </button>
                    {omni ? (
                      <button type="button" style={S.button} data-testid="active-session-open" onClick={() => openTab({ type: 'cc_session', id: omni.id }, it.digest?.title || `${planShortName(omni.active_plan)} · ${omni.id.slice(-6)}`)} title="回到驾驶舱里这个会话的页签">打开</button>
                    ) : (
                      <>
                        <button type="button" style={S.ghostButton} data-testid="active-session-load" disabled={importingId === it.session_id} onClick={() => { void onImport(it) }} title="把这段对话的真实内容载入为总控前文">
                          {importingId === it.session_id ? '载入中…' : '载入为前文'}
                        </button>
                        <button type="button" style={S.button} data-testid="active-session-adopt" disabled={adoptingId === it.session_id} onClick={() => { void onAdopt(it) }} title="resume 这段会话接管它当 subagent: 你能实时看+随时接管, 不接管时总控驱动">
                          {adoptingId === it.session_id ? '采纳中…' : '采纳为 subagent'}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
      {loading && <div style={S.empty}>加载中...</div>}
      {!loading && !error && activeSessions.length === 0 && threads.length === 0 && <div style={S.empty}>暂无对话</div>}
      {!loading && !error && threads.length > 0 && (
        <div style={S.list}>
          <div style={{ ...S.meta, color: '#8b949e', marginBottom: 2 }}>还没产生对话内容的会话(全新 / pty)</div>
          {threads.map((thread) => {
            const fresh = (Date.now() / 1000 - thread.startedAt) < 86400
            return (
            <div key={`${thread.kind}-${thread.id}`} style={{ ...S.row, ...(compact ? { gridTemplateColumns: '1fr' } : {}), ...(fresh ? { borderColor: '#27553a' } : {}) }} data-testid="thread-monitor-row" data-fresh={fresh ? '1' : '0'}>
              <div style={{ minWidth: 0 }}>
                <div style={S.rowTitle}>
                  {fresh && <span style={{ color: '#3fb950', marginRight: 6, fontSize: 14 }}>● 24h</span>}
                  <span style={S.badge}>{thread.status}</span>
                  {thread.title}
                </div>
                <div style={S.meta}>
                  {thread.provider} · {thread.kind} · {planShortName(thread.activePlan)} · {relTime(thread.startedAt)}
                  {thread.lastMessage ? ` · ${thread.lastMessage}` : ''}
                </div>
              </div>
              <button type="button" style={S.button} onClick={() => openThread(thread)}>打开</button>
            </div>
            )
          })}
        </div>
      )}
      {importOpen && (
        <div style={S.modalBackdrop} data-testid="import-session-modal" onMouseDown={(e) => { if (e.target === e.currentTarget) setImportOpen(false) }}>
          <div style={S.modal}>
            <div style={S.modalHead}>
              <div style={S.title}>载入已有对话为总控前文 · Claude Code / Codex</div>
              <button type="button" style={S.ghostButton} onClick={() => setImportOpen(false)}>关闭</button>
            </div>
            <div style={S.meta}>选一段本机已有对话, 把它的真实内容作为【前文/背景】插入当前总控对话(总控会看到并简短确认)。不另起会话。</div>
            {importError && <div style={S.error}>{importError}</div>}
            {importLoading && <div style={S.empty}>扫描中…</div>}
            {!importLoading && !importError && importItems.length === 0 && (
              <div style={S.empty}>没扫到可载入的历史会话(~/.claude/projects、~/.codex/sessions 近 90 天内)。</div>
            )}
            {!importLoading && importItems.length > 0 && (
              <div style={S.modalList}>
                {importItems.map((item) => (
                  <div key={`${item.provider}-${item.session_id}-${item.file}`} style={S.importRow} data-testid="import-session-row">
                    <div style={{ minWidth: 0 }}>
                      <div style={S.rowTitle}>
                        <span style={S.providerTag(item.provider === 'codex')}>{item.provider === 'codex' ? 'Codex' : 'Claude'}</span>
                        {item.preview || item.session_id}
                      </div>
                      <div style={S.meta}>{item.cwd || '(未知目录)'} · {relTime(item.mtime)} · {item.session_id.slice(0, 12)}</div>
                    </div>
                    <button
                      type="button"
                      style={S.button}
                      disabled={importingId === item.session_id}
                      data-testid="import-session-go"
                      onClick={() => { void onImport(item) }}
                    >
                      {importingId === item.session_id ? '载入中…' : '载入为前文'}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
