// 「管线」看板 — 管线 == team(TeamSpec 是 2026-04-21 从 PipelineSpec 改名来的同一模型)。
// 用户 2026-06-19: "我怎么知道一个 project 属下的管线有哪些, 在哪里？" 项目↔管线唯一的链接是
// 项目 root(包路径), 此前没任何地方展示归属。这里按项目分组: 每个 project 一组, 列它 root 路径下的
// 管线(team*.py), 显示包路径/状态/最近修改/复制源码路径; 点行打开既有 team 拓扑视图(结构图/源码/设计)。
// 数据: /api/teams(catalogue.py) + /api/projects(projects_registry, 取 roots 做归属匹配)。
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Copy, RefreshCw, FileCode2 } from 'lucide-react'
import { usePanels } from '../../stores/panelsStore'
import { useRefreshBus } from '../../stores/refreshBus'
import { openProps } from '../../utils/middleClick'
import { copyText } from '../../lib/copyText'
import { relTimeEn } from '../../lib/time'
import { ProjectIcon } from '../../lib/projectIcon'
import { projectsApi, type ProjectItem } from '../../api/projectsClient'
import KebabMenu, { type KebabItem } from '../../shared/view/ui/KebabMenu'

interface TeamItem {
  id: string
  name: string
  package: string
  file_path?: string
  size?: number
  has_design_md?: boolean
  registered_via?: string
  mtime?: number
}

const UNATTR = '__unattributed__'

function teamLabel(pkg: string): string {
  const parts = (pkg || '').split('/').filter(Boolean)
  return parts[parts.length - 1] || pkg || '?'
}
function isRegistered(via?: string): boolean {
  return !!via && via !== 'file_glob_only'
}
function norm(p?: string): string {
  return (p || '').replace(/\\/g, '/').toLowerCase().replace(/\/+$/, '')
}
/** 把一条管线按 file_path 归到 root 最长前缀匹配的项目; 没匹配返回 null。 */
function attributeProject(filePath: string | undefined, projects: ProjectItem[]): ProjectItem | null {
  const f = norm(filePath)
  if (!f) return null
  let best: ProjectItem | null = null
  let bestLen = 0
  for (const p of projects) {
    for (const r of p.roots || []) {
      const rn = norm(r)
      if (rn && (f === rn || f.startsWith(rn + '/')) && rn.length > bestLen) {
        best = p
        bestLen = rn.length
      }
    }
  }
  return best
}

const S: Record<string, any> = {
  root: { height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, background: '#0a0a0a', color: '#e6edf3' },
  head: { flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: '1px solid #1f2937' },
  title: { fontSize: 18, fontWeight: 750, color: '#e6edf3' },
  sub: { color: '#7d8da0', fontSize: 13 },
  search: { flex: 1, height: 30, border: '1px solid #263443', background: '#080b0e', color: '#d7dee7', borderRadius: 6, padding: '0 10px', fontSize: 14, minWidth: 0 },
  iconBtn: { width: 28, height: 28, border: '1px solid #263443', borderRadius: 5, background: '#101820', color: '#b8c7d9', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 },
  scroll: { flex: 1, minHeight: 0, overflowY: 'auto' },
  groupHead: { position: 'sticky' as const, top: 0, zIndex: 1, display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', background: '#0d1117', borderBottom: '1px solid #1f2937', color: '#9fb2c6', fontSize: 14, fontWeight: 700 },
  groupCount: { color: '#586573', fontSize: 12.5, fontWeight: 400 },
  row: { display: 'grid', gridTemplateColumns: '220px 1fr 140px 96px 30px', gap: 10, alignItems: 'center', padding: '8px 16px 8px 28px', borderBottom: '1px solid #131922', cursor: 'pointer' },
  name: { color: '#e6edf3', fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 8 },
  pkg: { color: '#7d8da0', fontSize: 12.5, fontFamily: 'var(--mono, monospace)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  badges: { display: 'flex', gap: 6, alignItems: 'center', overflow: 'hidden' },
  badge: (on: boolean): React.CSSProperties => ({ fontSize: 11.5, borderRadius: 4, padding: '1px 7px', whiteSpace: 'nowrap', color: on ? '#3fb950' : '#8b949e', background: on ? '#0d1a13' : '#161b22', border: `1px solid ${on ? '#214f32' : '#27313c'}` }),
  timeCell: { color: '#8b949e', fontSize: 13, textAlign: 'right' as const, whiteSpace: 'nowrap' },
  empty: { color: '#8b949e', padding: 24, fontSize: 14, textAlign: 'center' as const },
  err: { color: '#ff8a80', fontSize: 14, padding: '10px 16px' },
}

interface Group { key: string; label: string; projId?: string; teams: TeamItem[] }

export default function TeamRecentBoard() {
  const [items, setItems] = useState<TeamItem[]>([])
  const [projects, setProjects] = useState<ProjectItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const openTab = usePanels((s) => s.openTab)
  const openTabBg = usePanels((s) => s.openTabBackground)
  const refreshNonce = useRefreshBus((s) => s.nonce)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      fetch('/api/teams').then((r) => (r.ok ? r.json() : Promise.reject(new Error(`teams ${r.status}`)))),
      projectsApi.list().catch(() => ({ projects: [] as ProjectItem[] })),
    ])
      .then(([t, b]) => { setItems((t?.items as TeamItem[]) || []); setProjects(((b as any)?.projects as ProjectItem[]) || []); setError(null) })
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load, refreshNonce])

  const open = (t: TeamItem, bg = false) =>
    (bg ? openTabBg : openTab)({ type: 'team', id: t.id }, teamLabel(t.package))

  // 按项目分组: 每条管线归到 root 最长前缀匹配的项目, 项目内按最近修改排, 组间按管线数降序。
  const groups = useMemo<Group[]>(() => {
    const s = q.trim().toLowerCase()
    const filtered = s ? items.filter((t) => `${t.id} ${t.package} ${t.name}`.toLowerCase().includes(s)) : items
    const byProj = new Map<string, Group>()
    for (const t of filtered) {
      const p = attributeProject(t.file_path, projects)
      const key = p ? p.id : UNATTR
      if (!byProj.has(key)) byProj.set(key, { key, label: p ? (p.name || p.id) : '未归属到项目', projId: p?.id, teams: [] })
      byProj.get(key)!.teams.push(t)
    }
    const arr = [...byProj.values()]
    for (const g of arr) g.teams.sort((a, b) => (b.mtime || 0) - (a.mtime || 0))
    arr.sort((a, b) => {
      if ((a.key === UNATTR) !== (b.key === UNATTR)) return a.key === UNATTR ? 1 : -1
      return b.teams.length - a.teams.length
    })
    return arr
  }, [items, projects, q])

  const totalShown = groups.reduce((n, g) => n + g.teams.length, 0)

  return (
    <div style={S.root} data-testid="team-recent-board">
      <div style={S.head}>
        <div>
          <div style={S.title}>管线 · 按项目</div>
          <div style={S.sub}>管线 = team(TeamSpec/PipelineSpec) · 按所属项目分组 · 点开看拓扑/消息走向/worker 源码</div>
        </div>
        <input style={S.search} placeholder="搜管线名 / 包路径 / id…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="team-board-search" />
        <button type="button" style={S.iconBtn} title="刷新" data-testid="team-board-refresh" onClick={() => load()}><RefreshCw size={14} /></button>
      </div>
      {error && <div style={S.err}>加载失败: {error}</div>}
      <div style={S.scroll} data-testid="team-board-scroll">
        {!loading && totalShown === 0 && <div style={S.empty}>{q ? '没有匹配的管线' : '暂无管线'}</div>}
        {groups.map((g) => (
          <div key={g.key} data-testid="team-project-group" data-project={g.projId || 'none'}>
            <div style={S.groupHead}>
              {g.projId ? <ProjectIcon id={g.projId} size={18} /> : <span style={{ width: 18, height: 18, borderRadius: 4, background: '#1b1110', border: '1px solid #5c3a26', display: 'inline-block' }} />}
              <span>{g.label}</span>
              <span style={S.groupCount}>{g.teams.length} 条管线</span>
            </div>
            {g.teams.map((t) => {
              const menu: KebabItem[] = [
                { label: '复制管线 id', icon: <Copy size={14} />, testid: 'team-kebab-copy-id', onClick: () => { void copyText(t.id) } },
              ]
              if (t.file_path) menu.push({ label: '复制源码路径', icon: <FileCode2 size={14} />, testid: 'team-kebab-copy-path', onClick: () => { void copyText(t.file_path!) } })
              return (
                <div key={t.id} style={S.row} data-testid="team-recent-row" title={`${t.id} · 左键打开 / 中键后台开`} {...openProps(() => open(t), () => open(t, true))}>
                  <div style={S.name}>
                    <span style={{ width: 18, height: 18, borderRadius: 4, flexShrink: 0, background: '#101a23', border: '1px solid #28415a', color: '#79c0ff', fontSize: 11, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>⛓</span>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{teamLabel(t.package)}</span>
                  </div>
                  <div style={S.pkg} title={t.file_path || t.package}>{t.package}</div>
                  <div style={S.badges}>
                    <span style={S.badge(isRegistered(t.registered_via))}>{isRegistered(t.registered_via) ? '已注册' : '未进G2'}</span>
                    {t.has_design_md && <span style={S.badge(true)}>设计</span>}
                  </div>
                  <div style={S.timeCell}>{t.mtime ? relTimeEn(t.mtime) : '—'}</div>
                  <div style={{ display: 'flex', justifyContent: 'center' }} data-omni-capture-ignore="true">
                    <KebabMenu items={menu} testid="team-recent-kebab" iconSize={14} />
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
