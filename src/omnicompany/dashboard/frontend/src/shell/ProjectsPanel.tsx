// 侧栏项目面板 — 与首页"项目工作板"同一数据源 (/api/projects, core 层唯一权威注册表)。
// 旧 WorkboardPanel(三态 lane 的 plan/card 策展, data/boss_sight/workboard.json)已于
// 2026-06-12 按用户要求退役: "双写和功能不统一…本体应该独立于 dashboard 存放, 有唯一权威,
// 任何其他位置都应该被删除"。用量小组件保留。

import React, { useCallback, useEffect, useState } from 'react'
import { RefreshCw, LayoutGrid } from 'lucide-react'
import { projectsApi, type ProjectItem, type ProjectsBoard } from '../api/projectsClient'
import { usePanels } from '../stores/panelsStore'
import { useControllerView } from '../entities/controller'
import { useRefreshBus } from '../stores/refreshBus'
import { ActivityStrip } from '../entities/project/ProjectBoard'
import { openProps } from '../utils/middleClick'
import { relTimeZh as relTime } from '../lib/time'
import { ProjectIcon } from '../lib/projectIcon'

const S: Record<string, any> = {
  root: { borderTop: '1px solid #202a35', marginTop: 8, paddingTop: 8 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 6px 6px' },
  title: { color: '#cdd9e5', fontSize: 16, fontWeight: 700 as const, letterSpacing: 0 },
  headBtns: { display: 'flex', gap: 4 },
  iconBtn: { width: 20, height: 20, border: '1px solid #263443', borderRadius: 4, background: '#101820', color: '#b8c7d9', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 },
  usage: { borderBottom: '1px solid #1c2630', padding: '0 6px 8px', marginBottom: 6 },
  usageHead: { color: '#7d8da0', fontSize: 14, fontWeight: 600 as const, margin: '2px 0 4px' },
  usageRow: { display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' as const, padding: '1px 0' },
  usageName: { color: '#9fd0ff', fontSize: 14, width: 50, flexShrink: 0 },
  usageVal: { color: '#c2cdd8', fontSize: 14 },
  usageDim: { color: '#6e7d8c', fontSize: 14 },
  groupHead: { color: '#9fb2c6', fontSize: 14.5, fontWeight: 600 as const, margin: '8px 6px 3px' },
  card: { position: 'relative' as const, borderRadius: 6, overflow: 'hidden', margin: '0 4px 5px', minHeight: 44, cursor: 'pointer', border: '1px solid #1d2630' },
  cardBgLayer: { position: 'absolute' as const, inset: 0 },
  // 压暗层(2026-06-12 用户: 图片背景撞色压字) — 文字在左, 左侧压重
  cardOverlay: { position: 'absolute' as const, inset: 0, background: 'linear-gradient(to right, rgba(5,8,11,.88) 0%, rgba(5,8,11,.62) 55%, rgba(5,8,11,.32) 100%)' },
  cardInner: { position: 'relative' as const, padding: '6px 8px' },
  cardName: { color: '#fff', fontSize: 14.5, fontWeight: 600, textShadow: '0 1px 3px rgba(0,0,0,.9)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  cardMeta: { color: 'rgba(255,255,255,.72)', fontSize: 13, marginTop: 2, textShadow: '0 1px 2px rgba(0,0,0,.9)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  empty: { color: '#586573', fontSize: 14, padding: '2px 8px 4px' },
  err: { color: '#ff8a80', fontSize: 14, padding: '2px 8px' },
}

function cardBackground(p: ProjectItem): string {
  const bg = (p.bg || '').trim()
  if (bg) {
    if (/^(https?:|data:|\/|\.\/)/.test(bg) || /\.(png|jpe?g|webp|gif|svg)(\?|$)/i.test(bg)) {
      return `center/cover no-repeat url("${bg.replace(/"/g, '%22')}")`
    }
    return bg
  }
  let h = 0
  for (let i = 0; i < p.id.length; i++) h = (h * 31 + p.id.charCodeAt(i)) >>> 0
  return `linear-gradient(105deg, hsl(${h % 360}, 42%, 30%) 0%, #0a0d10 92%)`
}

// #5 用量小组件: Claude **官方剩余配额**(直接读 Anthropic oauth/usage 端点, 见 boss_sight/usage.py)。
interface UsageWin { used_pct: number; remaining_pct: number; resets_at?: string | null; reset_in_sec?: number | null }
interface ProvUsage { available?: boolean; reason?: string; five_hour?: UsageWin | null; seven_day?: UsageWin | null; note?: string; stale?: boolean; stale_reason?: string }
interface RuntimeUsage {
  available?: boolean
  summary?: { call_count?: number; total_tokens?: number; cost_usd?: number }
  batch?: { active_count?: number; completed_count?: number; failed_count?: number; run_count?: number }
}

function fmtReset(sec?: number | null): string {
  if (sec == null) return ''
  if (sec <= 0) return '即将重置'
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60)
  if (h >= 24) return `${Math.floor(h / 24)}天${h % 24}h`
  if (h >= 1) return `${h}h${m}m`
  return `${m}m`
}

function remainColor(pct: number): string {
  if (pct <= 10) return '#f85149'
  if (pct <= 30) return '#d29922'
  return '#3fb950'
}

function UsageMeter() {
  const [data, setData] = useState<{ claude?: ProvUsage; codex?: ProvUsage; internal?: RuntimeUsage } | null>(null)
  const load = useCallback(() => {
    fetch('/api/boss-sight/usage')
      .then((r) => r.ok ? r.json() : Promise.reject(`${r.status}`))
      .then((d) => setData(d))
      .catch(() => setData({}))
  }, [])
  useEffect(() => {
    load()
    const t = window.setInterval(load, 180000)
    return () => window.clearInterval(t)
  }, [load])
  const win = (tag: string, w?: UsageWin | null) => {
    if (!w) return null
    const r = fmtReset(w.reset_in_sec)
    return (
      <span style={S.usageVal} title={`官方已用 ${w.used_pct}%${w.resets_at ? ' · 重置 ' + w.resets_at : ''}`}>
        {tag} <b style={{ color: remainColor(w.remaining_pct) }}>{w.remaining_pct}%</b>
        {r && <span style={S.usageDim}> ↻{r}</span>}
      </span>
    )
  }
  const row = (label: string, p?: ProvUsage) => {
    if (!p) return null
    if (!p.available) return <div style={S.usageRow}><span style={S.usageName}>{label}</span><span style={S.usageDim}>{p.reason || '不可用'}</span></div>
    return (
      <div style={S.usageRow}>
        <span style={S.usageName}>{label}</span>
        {win('5h', p.five_hour)}
        {win('7天', p.seven_day)}
        {p.stale && <span style={S.usageDim} title={p.stale_reason || '显示上次读数'}>·旧</span>}
      </div>
    )
  }
  const runtimeRow = (p?: RuntimeUsage) => {
    if (!p) return null
    const calls = p.summary?.call_count || 0
    const tokens = p.summary?.total_tokens || 0
    const cost = p.summary?.cost_usd || 0
    const active = p.batch?.active_count || 0
    const failed = p.batch?.failed_count || 0
    const batches = p.batch?.run_count || 0
    return (
      <div style={S.usageRow}>
        <span style={S.usageName}>LLM</span>
        <span style={S.usageVal}>{calls} calls</span>
        <span style={S.usageVal}>{tokens.toLocaleString()} tok</span>
        <span style={S.usageVal}>${cost.toFixed(4)}</span>
        <span style={S.usageDim}>{active ? `${active} running` : `${batches} batches`}{failed ? ` · ${failed} failed` : ''}</span>
      </div>
    )
  }
  return (
    <div style={S.usage} data-testid="workboard-usage">
      <div style={S.usageHead}>用量 · 官方剩余配额</div>
      {data === null && <div style={S.usageDim}>加载中…</div>}
      {data !== null && (<>{row('Claude', data.claude)}{row('Codex', data.codex)}{runtimeRow(data.internal)}</>)}
    </div>
  )
}

function ProjectsPanel() {
  const [board, setBoard] = useState<ProjectsBoard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const openTab = usePanels((s) => s.openTab)
  const openTabBg = usePanels((s) => s.openTabBackground)
  const refreshNonce = useRefreshBus((s) => s.nonce)

  const load = useCallback((fresh = false) => {
    setBusy(true)
    projectsApi.list(fresh).then((raw) => {
      // 防御: 返回形状不对(代理/测试 fallthrough)时归一成空板, 别让侧栏崩
      const b: ProjectsBoard = raw && Array.isArray((raw as any).projects)
        ? raw : { projects: [], groups_order: [], group_labels: {} }
      setBoard(b)
      setError(null)
    }).catch((e) => setError(String(e?.message || e))).finally(() => setBusy(false))
  }, [])
  useEffect(() => { load(refreshNonce > 0) }, [load, refreshNonce])

  const open = (p: ProjectItem, bg = false) => {
    (bg ? openTabBg : openTab)({ type: 'project', id: p.id }, p.name || p.id)
  }

  const groups: string[] = board
    ? [...board.groups_order, ...Array.from(new Set(board.projects.map((p) => p.group))).filter((g) => !board.groups_order.includes(g))]
    : []

  return (
    <div style={S.root} data-testid="cockpit-projects-panel">
      <div style={S.head}>
        <span style={S.title}>项目</span>
        <div style={S.headBtns}>
          <button type="button" style={S.iconBtn} title="打开首页(项目)" data-testid="projects-panel-board" onClick={() => { openTab({ type: 'controller', id: 'main' }, '总控'); useControllerView.getState().setView('project') }}><LayoutGrid size={11} /></button>
          <button type="button" style={{ ...S.iconBtn, opacity: busy ? 0.45 : 1 }} disabled={busy} title={busy ? '刷新中…' : '刷新(穿透缓存)'} data-testid="projects-panel-refresh" onClick={() => load(true)}><RefreshCw size={11} /></button>
        </div>
      </div>
      <UsageMeter />
      {error && <div style={S.err}>{error}</div>}
      {board && board.projects.length === 0 && <div style={S.empty}>还没有注册项目 (omni project register)。</div>}
      {board && groups.map((g) => {
        const rows = board.projects.filter((p) => p.group === g)
        if (!rows.length) return null
        return (
          <div key={g} data-testid={`projects-panel-group-${g}`}>
            <div style={S.groupHead}>{board.group_labels[g] || g}</div>
            {rows.map((p) => (
              <div key={p.id} style={S.card} data-testid="projects-panel-card" title={`${p.id} · 左键打开 / 中键后台开`} {...openProps(() => open(p), () => open(p, true))}>
                <div style={{ ...S.cardBgLayer, background: cardBackground(p) }} />
                <div style={S.cardOverlay} />
                <div style={S.cardInner}>
                  <div style={{ ...S.cardName, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ProjectIcon id={p.id} size={18} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name || p.id}</span>
                  </div>
                  <div style={{ ...S.cardMeta, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ActivityStrip days={p.activity_7d} />
                    <span>活跃 {relTime(p.last_active)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}

// 无 props, memo 出口 — 父级高频 state 变更不级联重渲(沿用旧 WorkboardPanel 的性能策略)。
export default React.memo(ProjectsPanel)
