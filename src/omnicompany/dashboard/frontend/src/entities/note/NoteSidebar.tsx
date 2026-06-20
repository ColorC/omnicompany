import React, { useEffect, useMemo, useState } from 'react'
import { fetchList, type NoteEntity } from './resolver'
import type { SidebarViewProps } from '../registry'

interface TreeNode {
  name: string
  path: string
  children: Map<string, TreeNode>
  notes: NoteEntity[]
}

function buildTree(notes: NoteEntity[]): TreeNode {
  const root: TreeNode = { name: '', path: '', children: new Map(), notes: [] }
  for (const n of notes) {
    const parts = n.id.split('/')
    const dirParts = parts.slice(0, -1)
    let cur = root
    for (const p of dirParts) {
      let next = cur.children.get(p)
      if (!next) {
        next = { name: p, path: cur.path ? cur.path + '/' + p : p, children: new Map(), notes: [] }
        cur.children.set(p, next)
      }
      cur = next
    }
    cur.notes.push(n)
  }
  return root
}

function filterTree(node: TreeNode, q: string): TreeNode | null {
  const matchedNotes = node.notes.filter((n) => n.id.toLowerCase().includes(q) || n.title.toLowerCase().includes(q))
  const filteredChildren = new Map<string, TreeNode>()
  for (const [k, v] of node.children) {
    const fc = filterTree(v, q)
    if (fc) filteredChildren.set(k, fc)
  }
  if (matchedNotes.length === 0 && filteredChildren.size === 0 && node.path) return null
  return { ...node, notes: matchedNotes, children: filteredChildren }
}

function countNotes(node: TreeNode): number {
  let n = node.notes.length
  for (const c of node.children.values()) n += countNotes(c)
  return n
}

const S: Record<string, any> = {
  treeNode: { fontSize: 14, fontFamily: 'Consolas, Menlo, monospace' },
  dir: (depth: number): React.CSSProperties => ({
    padding: '2px 0', paddingLeft: 4 + depth * 12, cursor: 'pointer',
    color: '#888', userSelect: 'none' as const,
    fontWeight: depth === 0 ? 'bold' as const : 'normal' as const,
  }),
  arr: { color: '#444', display: 'inline-block', width: 12 },
  count: { color: '#444', marginLeft: 6, fontSize: 14 },
  note: (depth: number, active: boolean): React.CSSProperties => ({
    padding: '2px 0', paddingLeft: 4 + depth * 12 + 12, cursor: 'pointer',
    color: active ? '#90caf9' : '#bbb',
    background: active ? '#1a2a3a' : 'transparent',
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
  }),
  empty: { padding: 8, color: '#444', fontStyle: 'italic' as const, fontSize: 14 },
}

interface NodeRowProps {
  node: TreeNode
  depth: number
  expanded: Set<string>
  toggle: (path: string) => void
  activeId: string | null
  onOpen: SidebarViewProps['openTab']
  forceExpandAll?: boolean
}

function NodeRow({ node, depth, expanded, toggle, activeId, onOpen, forceExpandAll }: NodeRowProps) {
  const isExpanded = forceExpandAll || expanded.has(node.path)
  const total = countNotes(node)
  return (
    <div>
      <div style={S.dir(depth)} onClick={() => toggle(node.path)} title={node.path}>
        <span style={S.arr}>{isExpanded ? '▾' : '▸'}</span>
        {node.name}
        <span style={S.count}>{total}</span>
      </div>
      {isExpanded && (
        <div>
          {[...node.children.values()].map((c) => (
            <NodeRow key={c.path} node={c} depth={depth + 1} expanded={expanded} toggle={toggle} activeId={activeId} onOpen={onOpen} forceExpandAll={forceExpandAll} />
          ))}
          {node.notes.map((n) => {
            const tabId = `note:${n.id}`
            const leaf = n.id.split('/').pop() || n.id
            return (
              <div
                key={n.id}
                style={S.note(depth, activeId === tabId)}
                title={n.id}
                onClick={() => onOpen({ type: 'note', id: n.id }, leaf)}
              >
                {leaf}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function NoteSidebar({ filter, activeId, openTab }: SidebarViewProps) {
  const [list, setList] = useState<NoteEntity[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [autoKey, setAutoKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchList().then((d) => {
      if (cancelled) return
      setList(d)
      // default expand top-level dirs (e.g. plans/, standards/, ...) — but NOT root files
      const top = new Set<string>()
      for (const n of d) {
        const parts = n.id.split('/')
        if (parts.length > 1) top.add(parts[0])
      }
      setExpanded(top)
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [])

  const tree = useMemo(() => buildTree(list), [list])
  const ql = filter.trim().toLowerCase()
  const filteredTree = useMemo(() => {
    if (!ql) return tree
    setAutoKey((k) => k + 1)
    return filterTree(tree, ql) || { ...tree, children: new Map(), notes: [] }
  }, [tree, ql])

  const toggle = (path: string) => setExpanded((s) => {
    const n = new Set(s)
    n.has(path) ? n.delete(path) : n.add(path)
    return n
  })

  if (loading) return <div style={S.empty}>加载中...</div>
  if (filteredTree.children.size === 0 && filteredTree.notes.length === 0) {
    return <div style={S.empty}>{ql ? '无匹配' : '无 note'}</div>
  }

  return (
    <div style={S.treeNode}>
      {[...filteredTree.children.values()].map((c) => (
        <NodeRow
          key={c.path + ':' + autoKey}
          node={c}
          depth={0}
          expanded={expanded}
          toggle={toggle}
          activeId={activeId}
          onOpen={openTab}
          forceExpandAll={!!ql}
        />
      ))}
      {filteredTree.notes.map((n) => {
        const tabId = `note:${n.id}`
        return (
          <div key={n.id} style={S.note(0, activeId === tabId)} title={n.id} onClick={() => openTab({ type: 'note', id: n.id }, n.id)}>
            {n.id}
          </div>
        )
      })}
    </div>
  )
}
