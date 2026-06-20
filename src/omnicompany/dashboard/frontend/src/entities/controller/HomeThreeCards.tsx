// 首页 · 协作平台式「最近访问」统一列表 — 计划 / 审阅材料 / 对话 合并, 纯按更新时间排, 下滑加载更多。
// 用户 2026-06-14: 三列改为一个统一列表(像协作平台云文档最近访问); 默认显示计划+审阅材料, 可选也显示对话;
//   每行看到 最近更新时间 / 所属计划 / 对应路径; 纯按更新时间排, 拉到底继续加载。
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Copy, Code2, ShieldCheck } from 'lucide-react'
import { ccChatApi, type ImportableSession, type CcChatSessionMeta, type CcChatProvider } from '../../api/ccChatClient'
import { reviewstageApi, type Material } from '../../api/reviewstageClient'
import { projectsApi } from '../../api/projectsClient'
import { usePanels } from '../../stores/panelsStore'
import { openProps } from '../../utils/middleClick'
import { relTimeEn as relTime } from '../../lib/time'
import { ProjectIcon } from '../../lib/projectIcon'
import { copyText } from '../../lib/copyText'
import { openChatInVscode } from '../../lib/surface'
import KebabMenu, { type KebabItem } from '../../shared/view/ui/KebabMenu'

function planShortName(planId: string | null | undefined): string {
  if (!planId) return ''
  const last = planId.split('/').pop() || planId
  return last.replace(/^\[\d{4}-\d{2}-\d{2}\]/, '')
}
function isoMs(ts: string | null | undefined): number {
  if (!ts) return 0
  const t = new Date(ts).getTime()
  return Number.isNaN(t) ? 0 : t
}

type Kind = 'plan' | 'material' | 'conv' | 'team'
type Row = {
  key: string
  kind: Kind
  title: string
  ts: number // 统一成毫秒, 排序键
  plan: string // 所属计划(短名)
  path: string // 对应路径
  status?: string
  projId?: string // 所属项目 id(配 ProjectIcon)
  open: (bg?: boolean) => void
  menu?: KebabItem[] // 行尾「…更多」菜单(复制 id / VSCode 打开 等; 后续逐步加 plan audit)
}

const KIND_META: Record<Kind, { label: string; color: string; bg: string; border: string }> = {
  plan: { label: '计划', color: '#79c0ff', bg: '#10233a', border: '#234563' },
  material: { label: '审阅材料', color: '#d2a8ff', bg: '#1d1530', border: '#3c2d63' },
  conv: { label: '对话', color: '#3fb950', bg: '#0d1a13', border: '#214f32' },
  team: { label: '管线', color: '#f0883e', bg: '#21130a', border: '#5c3a26' },
}
const RUN_STATUS: Record<string, string> = { working: '● 运行中', done: '已完成', waiting: '等待输入', idle: '空闲' }

const S: Record<string, any> = {
  root: { height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, background: '#0a0a0a', color: '#e6edf3' },
  head: { flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: '1px solid #1f2937' },
  search: { flex: 1, height: 30, border: '1px solid #263443', background: '#080b0e', color: '#d7dee7', borderRadius: 6, padding: '0 10px', fontSize: 14, minWidth: 0 },
  btn: { border: '1px solid #2f81f7', background: '#1f6feb', color: '#fff', borderRadius: 5, padding: '5px 10px', cursor: 'pointer', fontSize: 14, flexShrink: 0 },
  ghost: { border: '1px solid #2b3a49', background: '#101820', color: '#b7c8d9', borderRadius: 5, padding: '5px 10px', cursor: 'pointer', fontSize: 14, flexShrink: 0 },
  chip: (on: boolean, m: { color: string; bg: string; border: string }): React.CSSProperties => ({
    border: `1px solid ${on ? m.border : '#263443'}`, background: on ? m.bg : 'transparent',
    color: on ? m.color : '#6e7d8c', borderRadius: 14, padding: '3px 11px', cursor: 'pointer', fontSize: 13, flexShrink: 0,
  }) as React.CSSProperties,
  scroll: { flex: 1, minHeight: 0, overflowY: 'auto' },
  // 协作平台式表格: 标题 / 类型 / 所属计划 / 对应路径 / 最近更新
  grid: '1fr 86px 168px 230px 116px 30px',
  thead: { position: 'sticky' as const, top: 0, zIndex: 1, display: 'grid', gridTemplateColumns: '1fr 86px 168px 230px 116px 30px', gap: 10, padding: '7px 16px', background: '#0d1117', borderBottom: '1px solid #1f2937', color: '#6e7d8c', fontSize: 12.5 },
  row: { display: 'grid', gridTemplateColumns: '1fr 86px 168px 230px 116px 30px', gap: 10, alignItems: 'center', padding: '9px 16px', borderBottom: '1px solid #131922', cursor: 'pointer' },
  title: { color: '#e6edf3', fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 6 },
  typeBadge: (m: { color: string; bg: string; border: string }): React.CSSProperties => ({ justifySelf: 'start', fontSize: 12, borderRadius: 4, padding: '1px 7px', color: m.color, background: m.bg, border: `1px solid ${m.border}` }),
  cell: { color: '#9fd0ff', fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  pathCell: { color: '#7d8da0', fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  timeCell: { color: '#8b949e', fontSize: 13, textAlign: 'right' as const, whiteSpace: 'nowrap' },
  empty: { color: '#8b949e', padding: 24, fontSize: 14, textAlign: 'center' as const },
  more: { color: '#6e7d8c', padding: 12, fontSize: 13, textAlign: 'center' as const },
}

function matchQ(q: string, ...fields: (string | null | undefined)[]): boolean {
  if (!q) return true
  return fields.filter(Boolean).join(' ').toLowerCase().includes(q.toLowerCase())
}

const PAGE = 40

export default function HomeThreeCards() {
  const [convs, setConvs] = useState<any[]>([])
  const [plans, setPlans] = useState<any[]>([])
  const [materials, setMaterials] = useState<Material[]>([])
  const [teams, setTeams] = useState<any[]>([])  // 管线(team*.py), 加进最近列表的一个 kind
  const [planProj, setPlanProj] = useState<Record<string, string>>({})  // planId → 所属项目 id
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  // 默认: 计划 + 审阅材料; 对话可选(默认关)
  const [kinds, setKinds] = useState<Record<Kind, boolean>>({ plan: true, material: true, conv: false, team: false })
  const [visible, setVisible] = useState(PAGE)
  const openTab = usePanels((s) => s.openTab)
  const openTabBg = usePanels((s) => s.openTabBackground)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [chat, active, allPlans, mats, teamsRaw] = await Promise.all([
        ccChatApi.list({ limit: 80, includeArchived: false }).catch(() => [] as CcChatSessionMeta[]),
        ccChatApi.activeSessions(7 * 86400, 80).catch(() => [] as ImportableSession[]),
        // 全量计划(120 条, 带 last_modified_ts) — 后端已有该接口, 不用 briefing 的 15 条活跃子集
        fetch('/api/boss-sight/plans').then((r) => (r.ok ? r.json() : { plans: [] })).then((d) => (d.plans as any[]) || []).catch(() => [] as any[]),
        reviewstageApi.list().then((r) => r.items).catch(() => [] as Material[]),
        fetch('/api/teams').then((r) => (r.ok ? r.json() : { items: [] })).then((d) => (d.items as any[]) || []).catch(() => [] as any[]),
      ])
      const omniByClaudeSid = new Map<string, CcChatSessionMeta>()
      for (const c of chat) { if (c.claude_session_id) omniByClaudeSid.set(c.claude_session_id, c) }
      const rows: any[] = active.map((it) => {
        const omni = omniByClaudeSid.get(it.session_id)
        return { provider: it.provider, status: it.status, digest: it.digest, preview: it.preview, last_user: it.last_user, last_did: it.last_did, mtime: it.mtime || 0, cwd: it.cwd, sessionId: it.session_id, omniId: omni?.id, activePlan: omni?.active_plan ?? null }
      })
      const activeSids = new Set(active.map((a) => a.session_id))
      for (const c of chat) {
        if (c.claude_session_id && activeSids.has(c.claude_session_id)) continue
        rows.push({ provider: c.provider || 'claude_code', status: c.alive ? 'idle' : 'done', preview: c.last_message || c.first_message, mtime: c.started_at || 0, sessionId: c.claude_session_id || c.id, omniId: c.id, activePlan: c.active_plan ?? null })
      }
      setConvs(rows)
      setPlans(allPlans)  // 全量 120 条; 展示走下方无限滚动分批(滚到底再多渲)
      setMaterials(mats)
      setTeams(teamsRaw)
      // planId → 所属项目 id(服务端归属权威, 不靠路径前缀猜), 给计划/材料配项目 icon
      void projectsApi.list().then((board) => {
        const projs = ((board as any)?.projects as any[]) || []
        return Promise.all(projs.map((p) =>
          projectsApi.plans(p.id).then((r) => ({ id: p.id as string, ids: (r.plan_ids || []) as string[] })).catch(() => ({ id: p.id as string, ids: [] as string[] })),
        ))
      }).then((lists) => {
        const map: Record<string, string> = {}
        for (const { id, ids } of (lists || [])) for (const pid of ids) map[pid] = id
        setPlanProj(map)
      }).catch(() => {})
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const onCreate = useCallback(async () => {
    setCreating(true)
    try {
      const m = await ccChatApi.create({ provider: 'claude_code' })
      openTab({ type: 'cc_session', id: m.id }, `${planShortName(m.active_plan) || 'chat'} · ${m.id.slice(-6)}`)
      await load()
    } finally { setCreating(false) }
  }, [openTab, load])

  // ── 导航(全部走 openTab/openTabBg, 与项目工作板同一套)──
  const onAdopt = async (c: any) => {
    try {
      const m = await ccChatApi.create({ adopt_session_id: c.sessionId, provider: c.provider as CcChatProvider, cwd: c.cwd })
      openTab({ type: 'cc_session', id: m.id }, c.digest?.title || `采纳 · ${String(c.sessionId).slice(0, 6)}`)
      await load()
    } catch { /* 外部 resume 常失败, 静默 */ }
  }
  const openConv = (c: any, bg = false) => {
    if (c.omniId) (bg ? openTabBg : openTab)({ type: 'cc_session', id: c.omniId }, c.digest?.title || `${planShortName(c.activePlan) || 'chat'} · ${String(c.omniId).slice(-6)}`)
    else void onAdopt(c)
  }
  const openPlan = (p: any, bg = false) => {
    const ref = p.open_ref
    if (ref && ref.type && ref.id) (bg ? openTabBg : openTab)({ type: ref.type, id: String(ref.id) }, p.title || p.plan_id, ref.facet)
    else (bg ? openTabBg : openTab)({ type: 'plan', id: p.plan_id }, p.title || p.plan_id)
  }
  const openMaterial = (m: Material, bg = false) => (bg ? openTabBg : openTab)({ type: 'review_queue', id: 'main' }, '审阅队列', m.id)
  // 跑 plan audit: POST 起后台 job → 开 plan_audit 页签轮询渲染报告(分钟级)
  const startAudit = useCallback(async (against: 'conversation' | 'plan', id: string, provider?: string) => {
    try {
      const r = await fetch('/api/plan-audit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ against, id, provider }) })
      if (!r.ok) return
      const d = await r.json()
      if (d?.job_id) openTab({ type: 'plan_audit', id: d.job_id }, `审计:${String(id).slice(0, 8)}`)
    } catch { /* 静默 */ }
  }, [openTab])

  // ── 合并成统一行, 纯按更新时间(ts 毫秒)降序 ──
  const rows = useMemo<Row[]>(() => {
    const out: Row[] = []
    // digest 字段可能是便宜模型如实写的占位串(「信息不足」/「无」), 视同空以便回退到 preview/路径
    const cleanDigest = (s?: string) => { const v = (s || '').trim(); return v === '信息不足' || v === '无' ? '' : v }
    if (kinds.plan) {
      for (const p of plans) {
        out.push({ key: `plan-${p.plan_id}`, kind: 'plan', title: p.title || planShortName(p.plan_id), ts: isoMs(p.last_modified_ts), plan: planShortName(p.plan_id), path: p.plan_id || '', status: p.status, projId: planProj[p.plan_id], open: (bg) => openPlan(p, bg), menu: [
          { label: '复制 plan id', icon: <Copy size={14} />, testid: 'recent-kebab-copy-plan', onClick: () => { void copyText(String(p.plan_id || '')) } },
          { label: '跑 plan audit', icon: <ShieldCheck size={14} />, testid: 'recent-kebab-audit-plan', onClick: () => { void startAudit('plan', String(p.plan_id || '')) } },
        ] })
      }
    }
    if (kinds.material) {
      for (const m of materials) {
        out.push({ key: `mat-${m.id}`, kind: 'material', title: m.title, ts: isoMs(m.created_at), plan: planShortName(m.source_plan_id), path: `${m.kind || ''}${m.tier ? ' · ' + m.tier : ''}`, status: m.status, projId: planProj[m.source_plan_id || ''], open: (bg) => openMaterial(m, bg), menu: [{ label: '复制材料 id', icon: <Copy size={14} />, testid: 'recent-kebab-copy-mat', onClick: () => { void copyText(String(m.id)) } }] })
      }
    }
    if (kinds.conv) {
      for (const c of convs) {
        const planLabel = c.activePlan ? planShortName(c.activePlan) : cleanDigest(c.digest?.plan)
        out.push({ key: `conv-${c.sessionId}-${c.omniId || ''}`, kind: 'conv', title: cleanDigest(c.digest?.title) || c.last_user || c.preview || String(c.sessionId).slice(0, 12), ts: (c.mtime || 0) * 1000, plan: planLabel || cleanDigest(c.digest?.project), path: c.cwd || '', status: c.status, open: (bg) => openConv(c, bg), menu: [
          { label: '复制 session id', icon: <Copy size={14} />, testid: 'recent-kebab-copy-sid', onClick: () => { void copyText(String(c.sessionId || '')) } },
          { label: '在 VSCode 打开', icon: <Code2 size={14} />, testid: 'recent-kebab-vscode', onClick: () => openChatInVscode(c.provider, c.cwd, c.sessionId) },
          { label: '跑 plan audit', icon: <ShieldCheck size={14} />, testid: 'recent-kebab-audit-conv', onClick: () => { void startAudit('conversation', String(c.sessionId || ''), c.provider) } },
        ] })
      }
    }
    if (kinds.team) {
      for (const t of teams) {
        const pkg = String(t.package || '')
        const name = pkg.split('/').filter(Boolean).pop() || t.name || t.id
        out.push({ key: `team-${t.id}`, kind: 'team', title: name, ts: (t.mtime || 0) * 1000, plan: '', path: pkg, open: (bg) => (bg ? openTabBg : openTab)({ type: 'team', id: t.id }, name), menu: [
          { label: '复制管线 id', icon: <Copy size={14} />, testid: 'recent-kebab-copy-team', onClick: () => { void copyText(String(t.id)) } },
          ...(t.file_path ? [{ label: '复制源码路径', icon: <Code2 size={14} />, testid: 'recent-kebab-copy-teampath', onClick: () => { void copyText(String(t.file_path)) } }] : []),
        ] })
      }
    }
    out.sort((a, b) => b.ts - a.ts)
    return out
  }, [plans, materials, convs, teams, kinds, planProj]) // eslint-disable-line react-hooks/exhaustive-deps

  const fRows = useMemo(() => rows.filter((r) => matchQ(q, r.title, r.plan, r.path, KIND_META[r.kind].label)), [rows, q])
  const shown = fRows.slice(0, visible)

  useEffect(() => { setVisible(PAGE) }, [q, kinds])

  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 120 && visible < fRows.length) {
      setVisible((v) => v + PAGE)
    }
  }

  const toggle = (k: Kind) => setKinds((s) => ({ ...s, [k]: !s[k] }))

  return (
    <div style={S.root} data-testid="home-recent-list">
      <div style={S.head}>
        <input style={S.search} placeholder="搜计划 / 材料 / 对话 / 管线…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="home-search" />
        {(['plan', 'material', 'conv', 'team'] as Kind[]).map((k) => (
          <button key={k} type="button" style={S.chip(kinds[k], KIND_META[k])} onClick={() => toggle(k)} data-testid={`home-filter-${k}`}>
            {KIND_META[k].label}
          </button>
        ))}
        <button type="button" style={S.btn} onClick={() => { void onCreate() }} disabled={creating} data-testid="home-new-session">{creating ? '新建中…' : '+ 新对话'}</button>
        <button type="button" style={S.ghost} onClick={() => { void load() }}>刷新</button>
      </div>
      <div style={S.scroll} onScroll={onScroll} data-testid="home-recent-scroll">
        <div style={S.thead}>
          <span>标题</span><span>类型</span><span>所属计划</span><span>对应路径</span><span style={{ textAlign: 'right' }}>最近更新</span><span />
        </div>
        {!loading && fRows.length === 0 && <div style={S.empty}>无内容(换个筛选或搜索词)</div>}
        {shown.map((r) => {
          const m = KIND_META[r.kind]
          return (
            <div key={r.key} style={S.row} data-testid="home-recent-row" {...openProps(() => r.open(), () => r.open(true))}>
              <div style={S.title} title={r.title}>
                {r.projId
                  ? <ProjectIcon id={r.projId} size={18} />
                  : <span style={{ width: 18, height: 18, borderRadius: 4, flexShrink: 0, background: m.bg, border: `1px solid ${m.border}`, display: 'inline-block' }} />}
                {r.kind === 'conv' && r.status && <span style={{ color: m.color, fontSize: 12 }}>{RUN_STATUS[r.status] || ''}</span>}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.title || '(无标题)'}</span>
              </div>
              <span style={S.typeBadge(m)}>{m.label}</span>
              <div style={S.cell} title={r.plan}>{r.plan || '—'}</div>
              <div style={S.pathCell} title={r.path}>{r.path || '—'}</div>
              <div style={S.timeCell}>{r.ts ? relTime(r.ts / 1000) : '—'}</div>
              <div style={{ display: 'flex', justifyContent: 'center' }} data-omni-capture-ignore="true">
                {r.menu && <KebabMenu items={r.menu} testid={`recent-kebab-${r.kind}`} iconSize={14} />}
              </div>
            </div>
          )
        })}
        {shown.length < fRows.length && <div style={S.more}>下滑加载更多 · 已显示 {shown.length}/{fRows.length}</div>}
      </div>
    </div>
  )
}
