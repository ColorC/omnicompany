import React, { useState } from 'react'
import type { WorkerEntity } from './resolver'
import Design from './facets/Design'
import Live from './facets/Live'
import History from './facets/History'

const FACETS = [
  { key: 'design', label: '设计', Component: Design },
  { key: 'live', label: '运行', Component: Live },
  { key: 'history', label: '历史', Component: History },
] as const

const S: Record<string, any> = {
  root: { display: 'flex', flexDirection: 'column', height: '100%' },
  facetBar: { display: 'flex', gap: 1, background: '#0a0a0a', borderBottom: '1px solid #222' },
  facetBtn: (active: boolean): React.CSSProperties => ({
    padding: '4px 12px', border: 'none', cursor: 'pointer',
    background: active ? '#1a2a3a' : 'transparent',
    color: active ? '#90caf9' : '#666',
    borderBottom: active ? '2px solid #90caf9' : '2px solid transparent',
    fontFamily: 'Consolas, Menlo, monospace', fontSize: 14,
  }),
  body: { flex: 1, overflow: 'hidden', minHeight: 0 },
}

export default function WorkerEditor({ entity, facet }: { entity: WorkerEntity; facet?: string }) {
  const [current, setCurrent] = useState<string>(facet || 'design')
  const Active = (FACETS.find((f) => f.key === current) || FACETS[0]).Component

  return (
    <div style={S.root}>
      <div style={S.facetBar}>
        {FACETS.map((f) => (
          <button key={f.key} style={S.facetBtn(current === f.key)} onClick={() => setCurrent(f.key)}>
            {f.label}
          </button>
        ))}
      </div>
      <div style={S.body}>
        <Active entity={entity} />
      </div>
    </div>
  )
}
