import React, { useEffect, useMemo, useState } from 'react'
import { workerResolver, type WorkerEntity } from './resolver'
import type { SidebarViewProps } from '../registry'

interface TreeNode {
  name: string
  path: string
  children: Map<string, TreeNode>
  workers: WorkerEntity[]
}

function buildTree(workers: WorkerEntity[]): TreeNode {
  const root: TreeNode = { name: '', path: '', children: new Map(), workers: [] }
  for (const w of workers) {
    const parts = w.id.split('/')
    const dirParts = parts.slice(0, -2)
    let cur = root
    for (const p of dirParts) {
      let next = cur.children.get(p)
      if (!next) {
        next = { name: p, path: cur.path ? cur.path + '/' + p : p, children: new Map(), workers: [] }
        cur.children.set(p, next)
      }
      cur = next
    }
    cur.workers.push(w)
  }
  return root
}

function filterTree(node: TreeNode, q: string): TreeNode | null {
  const matchedWorkers = node.workers.filter((w) =>
    w.id.toLowerCase().includes(q) || w.title.toLowerCase().includes(q),
  )
  const filteredChildren = new Map<string, TreeNode>()
  for (const [k, v] of node.children) {
    const fc = filterTree(v, q)
    if (fc) filteredChildren.set(k, fc)
  }
  if (matchedWorkers.length === 0 && filteredChildren.size === 0 && node.path) return null
  return { ...node, workers: matchedWorkers, children: filteredChildren }
}

const S: Record<string, any> = {
  treeNode: { fontSize: 14, fontFamily: 'Consolas, Menlo, monospace' },
  dir: (depth: number, expanded: boolean): React.CSSProperties => ({
    padding: '2px 0', paddingLeft: 4 + depth * 12, cursor: 'pointer',
    color: '#a8a8a8', userSelect: 'none' as const,
    fontWeight: depth === 0 ? 'bold' as const : 'normal' as const,
  }),
  arr: { color: '#666', display: 'inline-block', width: 12 },
  count: { color: '#777', marginLeft: 6, fontSize: 14 },
  worker: (depth: number, active: boolean): React.CSSProperties => ({
    padding: '2px 0', paddingLeft: 4 + depth * 12 + 12, cursor: 'pointer',
    color: active ? '#90caf9' : '#d0d0d0',
    background: active ? '#1a2a3a' : 'transparent',
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  }),
  empty: { padding: 8, color: '#888', fontSize: 14 },
}

interface NodeRowProps {
  node: TreeNode
  depth: number
  expanded: Set<string>
  toggle: (path: string) => void
  activeId: string | null
  onOpen: SidebarViewProps['openTab']
  initiallyOpen: boolean
  forceExpandAll?: boolean
}

function NodeRow({ node, depth, expanded, toggle, activeId, onOpen, initiallyOpen, forceExpandAll }: NodeRowProps) {
  const isExpanded = initiallyOpen || forceExpandAll || expanded.has(node.path)
  const total = countWorkers(node)
  return (
    <div>
      <div style={S.dir(depth, isExpanded)} onClick={() => toggle(node.path)} title={node.path}>
        <span style={S.arr}>{isExpanded ? '▾' : '▸'}</span>
        {node.name}
        <span style={S.count}>{total}</span>
      </div>
      {isExpanded && (
        <div>
          {[...node.children.values()].map((c) => (
            <NodeRow
              key={c.path}
              node={c}
              depth={depth + 1}
              expanded={expanded}
              toggle={toggle}
              activeId={activeId}
              onOpen={onOpen}
              initiallyOpen={false}
              forceExpandAll={forceExpandAll}
            />
          ))}
          {node.workers.map((w) => {
            const tabId = `worker:${w.id}`
            return (
              <div
                key={w.id}
                style={S.worker(depth, activeId === tabId)}
                title={w.id}
                onClick={() => onOpen({ type: 'worker', id: w.id }, w.title)}
              >
                {w.title}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function countWorkers(node: TreeNode): number {
  let n = node.workers.length
  for (const c of node.children.values()) n += countWorkers(c)
  return n
}

export default function WorkerSidebar({ filter, activeId, openTab }: SidebarViewProps) {
  const [list, setList] = useState<WorkerEntity[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [autoExpandKey, setAutoExpandKey] = useState(0)

  useEffect(() => {
    setLoading(true)
    workerResolver.list().then((d) => {
      setList(d)
      const top = new Set<string>()
      for (const w of d) {
        const seg = w.id.split('/')[0]
        if (seg) top.add(seg)
      }
      setExpanded(top)
      setLoading(false)
    })
  }, [])

  const tree = useMemo(() => buildTree(list), [list])
  const ql = filter.trim().toLowerCase()
  const filteredTree = useMemo(() => {
    if (!ql) return tree
    setAutoExpandKey((k) => k + 1)
    return filterTree(tree, ql) || { ...tree, children: new Map(), workers: [] }
  }, [tree, ql])

  const toggle = (path: string) => setExpanded((s) => {
    const n = new Set(s)
    n.has(path) ? n.delete(path) : n.add(path)
    return n
  })

  if (loading) return <div style={S.empty}>加载中...</div>
  if (filteredTree.children.size === 0 && filteredTree.workers.length === 0) {
    return <div style={S.empty}>{ql ? '无匹配' : '无 worker'}</div>
  }

  return (
    <div style={S.treeNode} data-tree="worker">
      {[...filteredTree.children.values()].map((c) => (
        <NodeRow
          key={c.path + ':' + autoExpandKey}
          node={c}
          depth={0}
          expanded={expanded}
          toggle={toggle}
          activeId={activeId}
          onOpen={openTab}
          initiallyOpen={!!ql}
          forceExpandAll={!!ql}
        />
      ))}
      {filteredTree.workers.map((w) => {
        const tabId = `worker:${w.id}`
        return (
          <div key={w.id} style={S.worker(0, activeId === tabId)} title={w.id} onClick={() => openTab({ type: 'worker', id: w.id }, w.title)}>
            {w.title}
          </div>
        )
      })}
    </div>
  )
}
