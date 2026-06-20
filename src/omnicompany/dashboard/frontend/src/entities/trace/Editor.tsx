import React, { useEffect, useMemo, useState } from 'react'
import { api, type TraceDetail, type TraceEvent } from '../../api/client'
import type { TraceEntity } from './index'
import { colors, spacing, fonts, statusColorOf } from '../../shell/tokens'

const eventTypeColor: Record<string, string> = {
  'task.intent': '#42a5f5', 'task.finish': '#66bb6a', 'task.error': '#ef5350',
  'agent.llm.request': '#7e57c2', 'agent.llm.response': '#9575cd',
  'agent.tool.call': '#ffb74d', 'agent.tool.result': '#ffa726',
  'agent.state.change': '#26c6da', 'agent.think': '#78909c',
}

function colorOf(ev: TraceEvent): string {
  // task.* → status semantic color; otherwise event-type palette.
  if (ev.event_type === 'task.finish') return statusColorOf('finished')
  if (ev.event_type === 'task.error') return statusColorOf('error')
  if (ev.event_type === 'task.intent') return statusColorOf('active')
  return eventTypeColor[ev.event_type] || '#444'
}

function fmtTs(ts: string | null | undefined): string {
  if (!ts) return ''
  try { return new Date(ts).toLocaleString('zh', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
  catch { return ts.slice(0, 19) }
}

function eventSummary(ev: TraceEvent): string {
  const p = ev.payload || {}
  switch (ev.event_type) {
    case 'task.intent': return p.instruction || p.task_desc || (p.pipeline ? `pipeline:${p.pipeline} → ${p.entry || ''}` : '-')
    case 'task.finish': return (p.result || '').toString().slice(0, 80) || 'done'
    case 'task.error': return p.error || p.reason || 'error'
    case 'agent.tool.call':
      if (p.tool) return `${p.tool}(${Object.keys(p.args || {}).join(', ')})`
      return `${p.node || '?'}: ${p.format_in || ''} → ${p.format_out || ''}`
    case 'agent.tool.result':
      if (p.tool) return `${p.tool} → ${(p.result || '').toString().slice(0, 60)}`
      return `${p.node || '?'} [${p.verdict || '?'}]`
    case 'agent.llm.response': return (p.content || p.text || '').toString().slice(0, 80)
    case 'agent.llm.request': return p.model ? `model=${p.model}` : `${p.node || '?'}: ${p.format_in || ''} → ${p.format_out || ''}`
    case 'agent.state.change': return p.from_state ? `${p.from_state} → ${p.to_state}` : `step ${p.step || '?'}: ${p.node || ''}`
    case 'agent.think': return (p.thought || '').slice(0, 80)
    default: return JSON.stringify(p).slice(0, 60)
  }
}

interface TreeNode {
  ev: TraceEvent
  depth: number
  children: TreeNode[]
}

/** Build parent_id-rooted forest. Orphans (parent_id refers nothing visible) become roots. */
function buildForest(events: TraceEvent[]): TreeNode[] {
  const byId = new Map<string, TreeNode>()
  for (const ev of events) byId.set(ev.id, { ev, depth: 0, children: [] })
  const roots: TreeNode[] = []
  for (const ev of events) {
    const node = byId.get(ev.id)!
    const parent = ev.parent_id ? byId.get(ev.parent_id) : null
    if (parent) {
      node.depth = parent.depth + 1
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }
  // sort children by timestamp asc
  const cmp = (a: TreeNode, b: TreeNode) => (a.ev.timestamp || '').localeCompare(b.ev.timestamp || '')
  const sortRec = (ns: TreeNode[]) => { ns.sort(cmp); ns.forEach((n) => sortRec(n.children)) }
  sortRec(roots)
  return roots
}

/** Flatten tree to depth-prefixed rows in pre-order. */
function flattenTree(roots: TreeNode[], collapsed: Set<string>): TreeNode[] {
  const out: TreeNode[] = []
  const walk = (n: TreeNode) => {
    out.push(n)
    if (collapsed.has(n.ev.id)) return
    n.children.forEach(walk)
  }
  roots.forEach(walk)
  return out
}

type View = 'list' | 'tree' | 'timeline'

const S: Record<string, any> = {
  root: { display: 'flex', flexDirection: 'column' as const, height: '100%', background: colors.bg, color: colors.text, fontFamily: fonts.mono, fontSize: 14 },
  toolbar: {
    display: 'flex', gap: 1, background: colors.bgPanel, borderBottom: `1px solid ${colors.border}`, flexShrink: 0,
    padding: `${spacing.xs}px ${spacing.lg}px`, alignItems: 'center', justifyContent: 'space-between',
  },
  tabs: { display: 'flex', gap: 1 },
  tab: (active: boolean): React.CSSProperties => ({
    padding: '4px 12px',
    background: active ? '#1a1a2a' : 'transparent',
    border: 'none',
    borderBottom: active ? `2px solid ${colors.accent}` : '2px solid transparent',
    color: active ? colors.accent : colors.textFaint,
    cursor: 'pointer', fontSize: 14, fontFamily: fonts.mono,
  }),
  meta: { color: colors.textFaint, fontSize: 14 },
  body: { flex: 1, display: 'flex', overflow: 'hidden' },
  events: { flex: 1, overflowY: 'auto', padding: spacing.lg, display: 'flex', flexDirection: 'column' as const, gap: 2 },
  detail: { width: 380, borderLeft: `1px solid ${colors.border}`, overflowY: 'auto', padding: spacing.lg, flexShrink: 0 },
  evRow: (selected: boolean, color: string): React.CSSProperties => ({
    padding: '4px 8px', borderRadius: 3, cursor: 'pointer',
    background: selected ? colors.accentBg : colors.bg,
    borderLeft: `3px solid ${color}`,
  }),
  treeRow: (selected: boolean, color: string, depth: number): React.CSSProperties => ({
    padding: '4px 8px', borderRadius: 3, cursor: 'pointer',
    background: selected ? colors.accentBg : colors.bg,
    borderLeft: `3px solid ${color}`,
    marginLeft: depth * 16,
    display: 'flex', alignItems: 'center', gap: 6,
  }),
  chev: { width: 12, color: colors.textFaint, cursor: 'pointer', userSelect: 'none' as const, textAlign: 'center' as const },
  tlRow: (selected: boolean): React.CSSProperties => ({
    position: 'relative', height: 22, marginBottom: 2, cursor: 'pointer',
    background: selected ? colors.accentBg : 'transparent',
    borderRadius: 3,
  }),
  tlLabel: { position: 'absolute' as const, left: 4, top: 3, color: colors.textMuted, fontSize: 14, pointerEvents: 'none' as const, whiteSpace: 'nowrap' as const, zIndex: 2, textShadow: '0 0 2px #000' },
  tlBar: (color: string, leftPct: number, widthPct: number): React.CSSProperties => ({
    position: 'absolute', top: 4, height: 14, borderRadius: 2,
    left: `${leftPct}%`, width: `${Math.max(widthPct, 0.6)}%`,
    background: color, opacity: 0.8,
  }),
  tlAxis: {
    position: 'sticky' as const, top: 0, zIndex: 20,
    background: colors.bgPanel,
    borderBottom: `1px solid ${colors.border}`,
    padding: '6px 8px', fontSize: 14, color: colors.textFaint,
    display: 'flex', justifyContent: 'space-between',
    boxShadow: '0 2px 4px rgba(0,0,0,0.5)',
  },
  tlScroll: { overflowX: 'auto' as const, overflowY: 'visible' as const },
  tlInner: (zoom: number): React.CSSProperties => ({
    width: `${100 * zoom}%`, minWidth: '100%', position: 'relative' as const,
  }),
  tlGroupRow: (selected: boolean, expanded: boolean): React.CSSProperties => ({
    position: 'relative' as const, height: 24, marginBottom: 2,
    cursor: 'pointer',
    background: selected ? colors.accentBg : (expanded ? '#0f1722' : 'transparent'),
    borderRadius: 3,
    borderTop: expanded ? `1px solid ${colors.border}` : 'none',
  }),
  tlGroupBar: (color: string, leftPct: number, widthPct: number): React.CSSProperties => ({
    position: 'absolute', top: 5, height: 14, borderRadius: 2,
    left: `${leftPct}%`, width: `${Math.max(widthPct, 0.6)}%`,
    background: color, opacity: 0.55,
    boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.05)',
  }),
  tlTick: (color: string, leftPct: number): React.CSSProperties => ({
    position: 'absolute', top: 4, width: 2, height: 16,
    left: `${leftPct}%`, background: color, opacity: 0.95,
    pointerEvents: 'none' as const, transform: 'translateX(-1px)',
  }),
  tlGroupLabel: {
    position: 'absolute' as const, left: 4, top: 4, color: colors.text, fontSize: 14,
    pointerEvents: 'none' as const, whiteSpace: 'nowrap' as const, zIndex: 3,
    textShadow: '0 0 3px #000, 0 0 3px #000',
  },
  tlGroupBadge: {
    position: 'absolute' as const, right: 6, top: 5, fontSize: 14, color: colors.textFaint,
    background: colors.bgPanel, padding: '0 5px', borderRadius: 8, zIndex: 3,
    border: `1px solid ${colors.border}`,
  },
  tlChildRow: (selected: boolean): React.CSSProperties => ({
    position: 'relative' as const, height: 18, marginBottom: 1,
    cursor: 'pointer',
    background: selected ? colors.accentBg : 'transparent',
    borderRadius: 2, marginLeft: 16,
  }),
  tlChildBar: (color: string, leftPct: number): React.CSSProperties => ({
    position: 'absolute', top: 3, height: 12, width: 4, borderRadius: 2,
    left: `${leftPct}%`, background: color, transform: 'translateX(-2px)',
  }),
  tlChildLabel: {
    position: 'absolute' as const, top: 2, color: colors.textMuted, fontSize: 14,
    pointerEvents: 'none' as const, whiteSpace: 'nowrap' as const, zIndex: 2,
    textShadow: '0 0 2px #000',
  },
  zoomCtl: {
    display: 'flex', alignItems: 'center', gap: 4, fontSize: 14, color: colors.textFaint,
  },
  zoomBtn: {
    background: 'transparent', color: colors.textFaint, border: `1px solid ${colors.border}`,
    borderRadius: 3, cursor: 'pointer', padding: '1px 6px', fontSize: 14, fontFamily: fonts.mono,
    minWidth: 20,
  },
  sectionTitle: { color: colors.accent, fontWeight: 'bold' as const, marginBottom: 4, marginTop: 8 },
  pre: { background: '#111', padding: 8, borderRadius: 4, color: '#aaa', whiteSpace: 'pre-wrap' as const, wordBreak: 'break-all' as const, fontSize: 14, maxHeight: 600, overflow: 'auto' },
}

function KV({ k, v }: { k: string; v: string | null | undefined }) {
  if (!v) return null
  return <div style={{ marginBottom: 3 }}><span style={{ color: colors.textFaint }}>{k}: </span><span style={{ color: '#ccc', wordBreak: 'break-all' }}>{v}</span></div>
}

interface TimelineSpan {
  ev: TraceEvent
  depth: number
  startMs: number
  endMs: number
}

const tsMs = (ev: TraceEvent): number => {
  if (!ev.timestamp) return 0
  const n = Date.parse(ev.timestamp)
  return Number.isFinite(n) ? n : 0
}

/** Pre-order flatten with end = max(self ts, max child end). (Ungrouped mode.) */
function buildTimelineSpans(roots: TreeNode[]): TimelineSpan[] {
  const endOf = new Map<string, number>()
  const computeEnd = (n: TreeNode): number => {
    let end = tsMs(n.ev)
    for (const c of n.children) {
      const ce = computeEnd(c)
      if (ce > end) end = ce
    }
    endOf.set(n.ev.id, end)
    return end
  }
  roots.forEach(computeEnd)
  const out: TimelineSpan[] = []
  const emit = (n: TreeNode) => {
    out.push({ ev: n.ev, depth: n.depth, startMs: tsMs(n.ev), endMs: endOf.get(n.ev.id) || tsMs(n.ev) })
    n.children.forEach(emit)
  }
  roots.forEach(emit)
  return out
}

// ─── Grouped timeline (per user round 21: 同 worker = 一行) ───────────────────

interface TimelineGroupRow {
  kind: 'group'
  key: string  // grouping key (currently == source)
  source: string
  startMs: number
  endMs: number
  events: TraceEvent[]  // sorted by timestamp asc
}

interface TimelineEventRow {
  kind: 'event'
  ev: TraceEvent
  source: string
  startMs: number
  endMs: number
}

type TimelineRow = TimelineGroupRow | TimelineEventRow

/** Group events by `source` (= worker). Each group's bar spans first→last event. */
function buildTimelineGroups(events: TraceEvent[]): TimelineGroupRow[] {
  const bySource = new Map<string, TraceEvent[]>()
  for (const ev of events) {
    const key = ev.source || 'unknown'
    if (!bySource.has(key)) bySource.set(key, [])
    bySource.get(key)!.push(ev)
  }
  const out: TimelineGroupRow[] = []
  for (const [source, evs] of bySource) {
    evs.sort((a, b) => tsMs(a) - tsMs(b))
    out.push({
      kind: 'group', key: source, source,
      startMs: tsMs(evs[0]),
      endMs: tsMs(evs[evs.length - 1]),
      events: evs,
    })
  }
  out.sort((a, b) => a.startMs - b.startMs)
  return out
}

function flattenGroupedTimeline(
  groups: TimelineGroupRow[], expanded: Set<string>,
): TimelineRow[] {
  const out: TimelineRow[] = []
  for (const g of groups) {
    out.push(g)
    if (expanded.has(g.key)) {
      for (const ev of g.events) {
        out.push({ kind: 'event', ev, source: g.source, startMs: tsMs(ev), endMs: tsMs(ev) })
      }
    }
  }
  return out
}

type GroupBy = 'none' | 'source'

export default function TraceEditor({ entity }: { entity: TraceEntity }) {
  const [detail, setDetail] = useState<TraceDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<TraceEvent | null>(null)
  const [view, setView] = useState<View>('list')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  // Timeline view controls (per ROADMAP S14):
  //   groupBy: 'source' (default) collapses every event from same worker into one row
  //   zoomFactor: horizontal stretch (1.0 = fit, 0.5 = compressed, up to 5x)
  //   expandedGroups: which group rows are showing their child events
  const [groupBy, setGroupBy] = useState<GroupBy>('source')
  const [zoomFactor, setZoomFactor] = useState(1.0)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    setDetail(null); setSelected(null); setError(null); setCollapsed(new Set())
    setExpandedGroups(new Set())
    api.trace(entity.id).then((d) => { if (!cancelled) setDetail(d) }).catch((e) => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [entity.id])

  const events = detail?.events || []
  const forest = useMemo(() => buildForest(events), [events])
  const flatTree = useMemo(() => flattenTree(forest, collapsed), [forest, collapsed])
  const timelineSpans = useMemo(() => buildTimelineSpans(forest), [forest])
  const timelineGroups = useMemo(() => buildTimelineGroups(events), [events])
  const groupedRows = useMemo(
    () => flattenGroupedTimeline(timelineGroups, expandedGroups),
    [timelineGroups, expandedGroups],
  )

  const tlBounds = useMemo(() => {
    const src = groupBy === 'source' ? timelineGroups : timelineSpans
    if (src.length === 0) return { min: 0, max: 1, span: 1 }
    let min = Infinity, max = -Infinity
    for (const s of src) {
      if (s.startMs && s.startMs < min) min = s.startMs
      if (s.endMs && s.endMs > max) max = s.endMs
    }
    if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
      return { min, max: min + 1, span: 1 }
    }
    return { min, max, span: max - min }
  }, [timelineSpans, timelineGroups, groupBy])

  const toggleCollapse = (id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  const bumpZoom = (delta: number) => {
    setZoomFactor((z) => Math.max(0.5, Math.min(5, +(z + delta).toFixed(2))))
  }
  const resetZoom = () => setZoomFactor(1)

  if (error) return <div style={{ ...S.root, padding: 16, color: '#ef5350' }}>{error}</div>
  if (!detail) return <div style={{ ...S.root, padding: 16, color: colors.textFaint }}>loading...</div>

  return (
    <div style={S.root} data-view={view}>
      <div style={S.toolbar}>
        <div style={S.tabs}>
          <button data-view-btn="list" style={S.tab(view === 'list')} onClick={() => setView('list')}>List</button>
          <button data-view-btn="tree" style={S.tab(view === 'tree')} onClick={() => setView('tree')}>Tree</button>
          <button data-view-btn="timeline" style={S.tab(view === 'timeline')} onClick={() => setView('timeline')}>Timeline</button>
        </div>
        <div style={S.meta}>trace_id: {entity.id} · {events.length} events</div>
      </div>

      <div style={S.body}>
        <div style={S.events} data-events-pane>
          {events.length === 0 && <div style={{ color: colors.textGhost }}>无事件</div>}

          {view === 'list' && events.map((ev) => {
            const color = colorOf(ev)
            return (
              <div key={ev.id} data-ev-id={ev.id} style={S.evRow(selected?.id === ev.id, color)} onClick={() => setSelected(ev)}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color }}>{ev.event_type}</span>
                  <span style={{ color: colors.textFaint, fontSize: 14 }}>{fmtTs(ev.timestamp)}</span>
                </div>
                <div style={{ color: '#aaa', fontSize: 14, marginTop: 2 }}>{eventSummary(ev)}</div>
              </div>
            )
          })}

          {view === 'tree' && flatTree.map((n) => {
            const ev = n.ev
            const color = colorOf(ev)
            const hasChildren = n.children.length > 0
            const isCollapsed = collapsed.has(ev.id)
            return (
              <div
                key={ev.id}
                data-ev-id={ev.id}
                data-depth={n.depth}
                style={S.treeRow(selected?.id === ev.id, color, n.depth)}
                onClick={() => setSelected(ev)}
              >
                <span
                  data-chev
                  style={S.chev}
                  onClick={(e) => { e.stopPropagation(); if (hasChildren) toggleCollapse(ev.id) }}
                >
                  {hasChildren ? (isCollapsed ? '▶' : '▼') : ''}
                </span>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color }}>{ev.event_type}</span>
                    <span style={{ color: colors.textFaint, fontSize: 14 }}>{fmtTs(ev.timestamp)}</span>
                  </div>
                  <div style={{ color: '#aaa', fontSize: 14, marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{eventSummary(ev)}</div>
                </div>
              </div>
            )
          })}

          {view === 'timeline' && (
            <div data-timeline>
              <div style={S.tlAxis}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <span>{tlBounds.min ? new Date(tlBounds.min).toLocaleTimeString('zh', { hour12: false }) : ''}</span>
                  <span>span: {(tlBounds.span / 1000).toFixed(2)}s</span>
                  <span>{tlBounds.max ? new Date(tlBounds.max).toLocaleTimeString('zh', { hour12: false }) : ''}</span>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <button
                    data-tl-group-toggle
                    style={{ ...S.zoomBtn, color: groupBy === 'source' ? colors.accent : colors.textFaint }}
                    onClick={() => setGroupBy(g => g === 'source' ? 'none' : 'source')}
                    title="按 worker (source) 合并行 / 不合并"
                  >
                    {groupBy === 'source' ? '☷ grouped' : '≡ flat'}
                  </button>
                  <div style={S.zoomCtl}>
                    <button data-tl-zoom-out style={S.zoomBtn} onClick={() => bumpZoom(-0.25)} title="缩小">−</button>
                    <button data-tl-zoom-reset style={S.zoomBtn} onClick={resetZoom} title="重置 1.0x">{zoomFactor.toFixed(2)}x</button>
                    <button data-tl-zoom-in style={S.zoomBtn} onClick={() => bumpZoom(0.25)} title="放大">+</button>
                  </div>
                </div>
              </div>
              <div style={S.tlScroll}>
                <div style={S.tlInner(zoomFactor)}>
                  {groupBy === 'source' ? (
                    groupedRows.map((row) => {
                      if (row.kind === 'group') {
                        const g = row
                        const isExpanded = expandedGroups.has(g.key)
                        // Use the most recent event's color as the group's "tone".
                        const tone = colorOf(g.events[g.events.length - 1])
                        const leftPct = ((g.startMs - tlBounds.min) / tlBounds.span) * 100
                        const widthPct = ((g.endMs - g.startMs) / tlBounds.span) * 100
                        return (
                          <div
                            key={`g:${g.key}`}
                            data-tl-group={g.key}
                            data-tl-expanded={isExpanded ? '1' : '0'}
                            style={S.tlGroupRow(false, isExpanded)}
                            onClick={() => toggleGroup(g.key)}
                          >
                            <div style={S.tlGroupBar(tone, Math.max(leftPct, 0), widthPct)} />
                            {/* Tick marks for individual events on the group bar. */}
                            {g.events.map((ev) => {
                              const evPct = ((tsMs(ev) - tlBounds.min) / tlBounds.span) * 100
                              return (
                                <div
                                  key={`tk:${ev.id}`}
                                  data-tl-tick
                                  style={S.tlTick(colorOf(ev), Math.max(evPct, 0))}
                                />
                              )
                            })}
                            <div style={S.tlGroupLabel}>{isExpanded ? '▾ ' : '▸ '}{g.source}</div>
                            <div style={S.tlGroupBadge}>×{g.events.length}</div>
                          </div>
                        )
                      }
                      // event row (only when group is expanded)
                      const evRow = row
                      const c = colorOf(evRow.ev)
                      const leftPct = ((evRow.startMs - tlBounds.min) / tlBounds.span) * 100
                      return (
                        <div
                          key={`e:${evRow.ev.id}`}
                          data-ev-id={evRow.ev.id}
                          style={S.tlChildRow(selected?.id === evRow.ev.id)}
                          onClick={(e) => { e.stopPropagation(); setSelected(evRow.ev) }}
                        >
                          <div style={S.tlChildBar(c, Math.max(leftPct, 0))} />
                          <div style={{ ...S.tlChildLabel, left: `${Math.max(leftPct, 0)}%`, paddingLeft: 8 }}>
                            {evRow.ev.event_type}
                          </div>
                        </div>
                      )
                    })
                  ) : (
                    timelineSpans.map((s) => {
                      const color = colorOf(s.ev)
                      const leftPct = ((s.startMs - tlBounds.min) / tlBounds.span) * 100
                      const widthPct = ((s.endMs - s.startMs) / tlBounds.span) * 100
                      return (
                        <div
                          key={s.ev.id}
                          data-ev-id={s.ev.id}
                          data-depth={s.depth}
                          style={S.tlRow(selected?.id === s.ev.id)}
                          onClick={() => setSelected(s.ev)}
                        >
                          <div style={S.tlBar(color, Math.max(leftPct, 0), widthPct)} />
                          <div style={{ ...S.tlLabel, paddingLeft: s.depth * 12 }}>{s.ev.event_type}</div>
                        </div>
                      )
                    })
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        <div style={S.detail} data-detail-pane>
          {!selected ? (
            <div style={{ color: colors.textGhost }}>点事件查看详情</div>
          ) : (
            <div>
              <div style={S.sectionTitle}>{selected.event_type}</div>
              <KV k="id" v={selected.id} />
              <KV k="source" v={selected.source} />
              <KV k="timestamp" v={fmtTs(selected.timestamp)} />
              {selected.parent_id && <KV k="parent_id" v={selected.parent_id} />}
              <div style={S.sectionTitle}>Payload</div>
              <pre style={S.pre}>{JSON.stringify(selected.payload, null, 2).slice(0, 5000)}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
