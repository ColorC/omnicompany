import React, { useEffect, useMemo, useState } from 'react'
import { api, type TraceListItem } from '../../api/client'
import { usePanels } from '../../stores/panelsStore'
import { statusColorOf } from '../tokens'

const S: Record<string, any> = {
  root: { display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0a0a', color: '#bbb', fontFamily: 'Consolas, Menlo, monospace', fontSize: 14 },
  bar: { display: 'flex', gap: 6, padding: '4px 8px', borderBottom: '1px solid #222', alignItems: 'center' },
  input: { flex: 1, background: '#111', border: '1px solid #333', borderRadius: 4, color: '#e0e0e0', padding: '3px 8px', fontSize: 14, fontFamily: 'Consolas, Menlo, monospace' },
  meta: { color: '#666', fontSize: 14 },
  list: { flex: 1, overflow: 'auto' },
  row: (active: boolean): React.CSSProperties => ({
    display: 'flex', gap: 8, padding: '3px 8px', cursor: 'pointer',
    background: active ? '#1a2a3a' : 'transparent',
    borderBottom: '1px solid #161616',
  }),
  ts: { color: '#555', flexShrink: 0, width: 100 },
  src: { color: '#888', flexShrink: 0, width: 110, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  desc: { flex: 1, color: '#bbb', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  status: (s: string): React.CSSProperties => ({
    flexShrink: 0, width: 60, fontSize: 14,
    color: statusColorOf(s),
  }),
  evct: { color: '#555', flexShrink: 0, width: 60, fontSize: 14, textAlign: 'right' as const },
}

function fmtTs(s: string | null): string {
  if (!s) return ''
  try { return new Date(s).toLocaleString('zh', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
  catch { return s.slice(0, 16) }
}

export default function TraceList() {
  const [items, setItems] = useState<TraceListItem[]>([])
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState('')
  const [domain, setDomain] = useState('')
  const [loading, setLoading] = useState(true)
  const openTab = usePanels((s) => s.openTab)
  const activeId = usePanels((s) => s.activeId)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.traceList({ limit: 200, q: filter || undefined, source: domain || undefined })
      .then((d) => {
        if (cancelled) return
        setItems(d.items); setTotal(d.total)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [filter, domain])

  const domains = useMemo(() => Array.from(new Set(items.map((t) => t.domain))).sort(), [items])

  return (
    <div style={S.root}>
      <div style={S.bar}>
        <input style={S.input} placeholder="过滤 task_desc..." value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select
          style={{ ...S.input, flex: 0, width: 120 }}
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
        >
          <option value="">全部域</option>
          {domains.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <span style={S.meta}>{loading ? '加载中...' : `${items.length}/${total}`}</span>
      </div>
      <div style={S.list}>
        {items.length === 0 && !loading && <div style={{ padding: 12, color: '#444' }}>无 trace</div>}
        {items.map((t) => {
          const tabId = `trace:${t.trace_id}`
          return (
            <div
              key={t.trace_id}
              style={S.row(activeId === tabId)}
              onClick={() => openTab({ type: 'trace', id: t.trace_id }, t.task_desc || t.trace_id.slice(0, 24))}
              title={t.trace_id}
            >
              <span style={S.ts}>{fmtTs(t.started_at)}</span>
              <span style={S.src}>{t.domain}</span>
              <span style={S.desc}>{t.task_desc || t.trace_id}</span>
              <span style={S.evct}>{t.event_count}ev</span>
              <span style={S.status(t.status)}>{t.status}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
