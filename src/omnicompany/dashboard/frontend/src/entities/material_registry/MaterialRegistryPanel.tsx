import React, { useEffect, useMemo, useState } from 'react'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { bossSightApi, type MaterialRegistryItem, type MaterialRegistryResponse } from '../../api/bossSightClient'
import { registry } from '../registry'
import type { EntityType } from '../types'
import { usePanels } from '../../stores/panelsStore'

const KIND_LABEL: Record<string, string> = {
  roadmap: '路线',
  plan: '计划',
  project: '项目',
  decision: '决策',
  guard: '守卫',
  policy: '策略',
  standard: '标准',
  template: '模板',
  prompt: 'Prompt',
  progress: '进度',
  handoff: '交接',
  report: '报告',
  audit: '审计',
  reflection: '反思',
  review_material: '审阅材料',
  material_definition: '材料定义',
  worker: 'Worker',
  team: 'Team',
  subagent: 'Subagent',
}

const ROLE_LABEL: Record<string, string> = {
  direction: '方向',
  boundary: '边界',
  reference: '参考',
  progress: '进度',
  review: '审阅',
  executor: '执行者',
  project_asset: '项目资产',
}

const LAYER_LABEL: Record<string, string> = {
  context: '上下文',
  executor: '执行层',
}

const ROLE_OPTIONS = ['', 'direction', 'boundary', 'progress', 'review', 'reference', 'executor', 'project_asset']
const LAYER_OPTIONS = ['', 'context', 'executor']

const S: Record<string, React.CSSProperties> = {
  root: { height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', background: '#0a0a0a', color: '#dbe7f3', fontFamily: 'Consolas, Menlo, monospace', overflow: 'hidden' },
  header: { padding: '10px 12px', borderBottom: '1px solid #1f2937', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  title: { color: '#9fd0ff', fontSize: 15, fontWeight: 700 },
  subtitle: { color: '#8b949e', fontSize: 14, marginTop: 3 },
  toolbar: { display: 'grid', gridTemplateColumns: 'minmax(180px, 1fr) repeat(4, minmax(110px, 150px)) auto', gap: 8, padding: 10, borderBottom: '1px solid #1f2937', alignItems: 'center' },
  input: { background: '#0f1720', border: '1px solid #263443', color: '#e6edf3', borderRadius: 4, padding: '6px 8px', minWidth: 0, fontSize: 14 },
  select: { background: '#0f1720', border: '1px solid #263443', color: '#e6edf3', borderRadius: 4, padding: '6px 8px', minWidth: 0, fontSize: 14 },
  button: { border: '1px solid #2b3a49', background: '#101820', color: '#dbe7f3', borderRadius: 4, padding: '6px 9px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14, whiteSpace: 'nowrap' },
  primaryButton: { border: '1px solid #2f81f7', background: '#1f6feb', color: '#fff', borderRadius: 4, padding: '6px 9px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14 },
  counts: { display: 'flex', gap: 8, padding: '8px 10px', borderBottom: '1px solid #1f2937', overflowX: 'auto' },
  metric: { border: '1px solid #263443', borderRadius: 6, padding: '6px 8px', minWidth: 96, background: '#0f1720' },
  metricValue: { color: '#e6edf3', fontWeight: 700, fontSize: 15 },
  metricLabel: { color: '#8b949e', fontSize: 14, marginTop: 2 },
  content: { flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: 'minmax(360px, 1fr) minmax(300px, 420px)', overflow: 'hidden' },
  list: { overflow: 'auto', borderRight: '1px solid #1f2937' },
  row: { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 10, padding: '9px 12px', borderBottom: '1px solid #161b22', cursor: 'pointer' },
  rowTitle: { color: '#e6edf3', fontWeight: 700, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  rowMeta: { color: '#8b949e', fontSize: 14, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  badge: { display: 'inline-flex', alignItems: 'center', border: '1px solid #2b3a49', background: '#101820', color: '#b7c8d9', borderRadius: 4, padding: '1px 5px', fontSize: 14, marginRight: 5 },
  badgeHot: { display: 'inline-flex', alignItems: 'center', border: '1px solid #214f32', background: '#10251a', color: '#7ee787', borderRadius: 4, padding: '1px 5px', fontSize: 14, marginRight: 5 },
  detail: { overflow: 'auto', padding: 12 },
  detailTitle: { color: '#9fd0ff', fontSize: 15, fontWeight: 700, marginBottom: 8 },
  kv: { display: 'grid', gridTemplateColumns: '76px minmax(0, 1fr)', gap: 8, padding: '5px 0', borderBottom: '1px solid #161b22', fontSize: 14 },
  key: { color: '#8b949e' },
  value: { color: '#dbe7f3', overflowWrap: 'anywhere' },
  snippet: { color: '#b7c8d9', whiteSpace: 'pre-wrap', lineHeight: 1.45, marginTop: 10, fontSize: 14 },
  relation: { display: 'inline-flex', margin: '0 5px 5px 0', border: '1px solid #263443', borderRadius: 4, padding: '2px 6px', color: '#b7c8d9', background: '#0f1720' },
  empty: { padding: 18, color: '#8b949e' },
  error: { padding: 18, color: '#ff7b72' },
}

function label(map: Record<string, string>, value: string | null | undefined): string {
  if (!value) return 'unknown'
  return map[value] || value
}

function statusBadge(item: MaterialRegistryItem): React.ReactNode {
  if (!item.status) return null
  const active = ['active', 'in_progress', 'in_progress_with_known_gaps'].includes(item.status)
  return <span style={active ? S.badgeHot : S.badge}>{item.status}</span>
}

function canOpen(item: MaterialRegistryItem): boolean {
  const ref = item.open_ref || {}
  if (ref.url || ref.command) return true
  return !!(ref.type && ref.id && registry.has(ref.type as EntityType))
}

export default function MaterialRegistryPanel() {
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [role, setRole] = useState('')
  const [layer, setLayer] = useState('')
  const [status, setStatus] = useState('')
  const [data, setData] = useState<MaterialRegistryResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const openTab = usePanels((s) => s.openTab)

  const load = () => {
    setLoading(true)
    setError(null)
    bossSightApi.getMaterialRegistry({ q, kind, role, layer, status, limit: 300 })
      .then((next) => {
        setData(next)
        setSelectedId((prev) => next.items.some((item) => item.id === prev) ? prev : (next.items[0]?.id || null))
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const t = window.setTimeout(load, 150)
    return () => window.clearTimeout(t)
  }, [q, kind, role, layer, status])

  const selected = useMemo(() => data?.items.find((item) => item.id === selectedId) || data?.items[0] || null, [data, selectedId])
  const kinds = useMemo(() => Object.keys(data?.counts.by_kind || {}).sort(), [data])
  const statuses = useMemo(() => Object.keys(data?.counts.by_status || {}).filter((s) => s !== 'unknown').sort(), [data])

  function openItem(item: MaterialRegistryItem) {
    const ref = item.open_ref || {}
    if (ref.url) {
      window.location.href = ref.url
      return
    }
    if (ref.type && ref.id && registry.has(ref.type as EntityType)) {
      openTab({ type: ref.type as EntityType, id: ref.id }, item.title, ref.facet)
      return
    }
    navigator.clipboard?.writeText(ref.command || item.uri).catch(() => {})
  }

  const metric = (name: string, value: number | undefined) => (
    <div style={S.metric}>
      <div style={S.metricValue}>{value || 0}</div>
      <div style={S.metricLabel}>{name}</div>
    </div>
  )

  return (
    <div style={S.root} data-testid="material-registry-panel">
      <div style={S.header}>
        <div>
          <div style={S.title}>任务材料</div>
          <div style={S.subtitle}>{data ? `${data.total} 条材料 · ${data.counts.by_layer.context || 0} 条上下文 · ${data.counts.by_layer.executor || 0} 个执行者` : '加载语义 registry'}</div>
        </div>
        <button type="button" style={S.button} onClick={load} aria-label="刷新任务材料">
          <RefreshCw size={14} />刷新
        </button>
      </div>
      <div style={S.toolbar}>
        <input aria-label="搜索任务材料" style={S.input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索标题、路径、摘要、uri" />
        <select aria-label="类型" style={S.select} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">全部类型</option>
          {kinds.map((k) => <option key={k} value={k}>{label(KIND_LABEL, k)}</option>)}
        </select>
        <select aria-label="作用" style={S.select} value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLE_OPTIONS.map((r) => <option key={r || 'all'} value={r}>{r ? label(ROLE_LABEL, r) : '全部作用'}</option>)}
        </select>
        <select aria-label="层级" style={S.select} value={layer} onChange={(e) => setLayer(e.target.value)}>
          {LAYER_OPTIONS.map((l) => <option key={l || 'all'} value={l}>{l ? label(LAYER_LABEL, l) : '全部层级'}</option>)}
        </select>
        <select aria-label="状态" style={S.select} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">全部状态</option>
          {statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <span style={{ color: '#8b949e', fontSize: 14 }}>{loading ? '加载中...' : `${data?.returned || 0} shown`}</span>
      </div>
      <div style={S.counts}>
        {metric('方向', data?.counts.by_role.direction)}
        {metric('边界', data?.counts.by_role.boundary)}
        {metric('进度', data?.counts.by_role.progress)}
        {metric('参考', data?.counts.by_role.reference)}
        {metric('执行者', data?.counts.by_role.executor)}
      </div>
      {error && <div style={S.error}>{error}</div>}
      {!error && !data && <div style={S.empty}>加载中...</div>}
      {!error && data && (
        <div style={S.content}>
          <div style={S.list}>
            {data.items.length === 0 && <div style={S.empty}>无匹配材料</div>}
            {data.items.map((item) => (
              <div
                key={item.uri}
                style={{ ...S.row, background: selected?.id === item.id ? '#101820' : 'transparent' }}
                onClick={() => setSelectedId(item.id)}
                data-testid="material-registry-row"
                title={item.uri}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={S.rowTitle}>
                    {statusBadge(item)}
                    <span style={S.badge}>{label(LAYER_LABEL, item.layer)}</span>
                    <span style={S.badge}>{label(ROLE_LABEL, item.role)}</span>
                    {item.title}
                  </div>
                  <div style={S.rowMeta}>
                    {label(KIND_LABEL, item.kind)} · {item.path || item.id}
                  </div>
                </div>
                {canOpen(item) && <ExternalLink size={14} color="#8b949e" />}
              </div>
            ))}
          </div>
          <div style={S.detail}>
            {!selected && <div style={S.empty}>选择一条 material 查看详情</div>}
            {selected && (
              <>
                <div style={S.detailTitle}>{selected.title}</div>
                <div style={S.kv}><div style={S.key}>类型</div><div style={S.value}>{label(KIND_LABEL, selected.kind)}</div></div>
                <div style={S.kv}><div style={S.key}>作用</div><div style={S.value}>{label(ROLE_LABEL, selected.role)}</div></div>
                <div style={S.kv}><div style={S.key}>层级</div><div style={S.value}>{label(LAYER_LABEL, selected.layer)}</div></div>
                <div style={S.kv}><div style={S.key}>状态</div><div style={S.value}>{selected.status || 'unknown'}</div></div>
                <div style={S.kv}><div style={S.key}>URI</div><div style={S.value}>{selected.uri}</div></div>
                <div style={S.kv}><div style={S.key}>路径</div><div style={S.value}>{selected.path || selected.id}</div></div>
                <div style={S.kv}><div style={S.key}>来源</div><div style={S.value}>{selected.source}</div></div>
                <div style={S.kv}>
                  <div style={S.key}>关系</div>
                  <div style={S.value}>
                    {selected.relations.length === 0 ? '无' : selected.relations.map((rel) => (
                      <span key={`${rel.kind}:${rel.id}:${rel.label}`} style={S.relation}>{rel.label}: {rel.kind}/{rel.id}</span>
                    ))}
                  </div>
                </div>
                <div style={{ marginTop: 10 }}>
                  <button type="button" style={canOpen(selected) ? S.primaryButton : S.button} onClick={() => openItem(selected)}>
                    <ExternalLink size={14} />{canOpen(selected) ? '打开' : '复制 URI'}
                  </button>
                </div>
                <div style={S.snippet}>{selected.snippet || '(no preview)'}</div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
