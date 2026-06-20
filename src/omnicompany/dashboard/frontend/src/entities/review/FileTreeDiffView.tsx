/**
 * FileTreeDiffView — filetree_diff_v1 渲染器(custom_web_template 载体)。
 * 树骨架抄 entities/note/NoteSidebar 模式；单文件 diff 复用 chat/tools 的 ToolDiffViewer。
 * 改动文件恒高亮；显示全部/仅 diff 目录同级 切换；点击看 diff、右键复制路径、可逐文件批注。
 */
import React, { useMemo, useState } from 'react'
import { reviewstageApi, type Material } from '../../api/reviewstageClient'
import { ToolDiffViewer } from '../../components/chat/tools/components/ToolDiffViewer'
import { COLORS } from './shared'

type FileStatus = 'added' | 'modified' | 'deleted' | 'renamed' | 'unchanged'
interface FilePreviewData { kind: 'image' | 'html'; data_url?: string; content?: string; oversized?: boolean }
export interface FileEntry {
  path: string
  old_path?: string | null
  status: FileStatus
  additions?: number
  deletions?: number
  annotation?: string | null
  diff?: string | null
  preview?: FilePreviewData | null
}
interface FileTreeDiffData {
  schema?: string
  source?: { mode?: string; root?: string; ref?: string | null; is_git?: boolean; generated_at?: string }
  counts?: Record<string, number>
  files?: FileEntry[]
}

interface TreeNode { name: string; path: string; children: Map<string, TreeNode>; files: FileEntry[] }

function buildTree(files: FileEntry[]): TreeNode {
  const root: TreeNode = { name: '', path: '', children: new Map(), files: [] }
  for (const f of files) {
    const parts = f.path.split('/')
    let cur = root
    for (const p of parts.slice(0, -1)) {
      let next = cur.children.get(p)
      if (!next) { next = { name: p, path: cur.path ? `${cur.path}/${p}` : p, children: new Map(), files: [] }; cur.children.set(p, next) }
      cur = next
    }
    cur.files.push(f)
  }
  return root
}

const STATUS_COLOR: Record<FileStatus, string> = {
  added: '#3fb950', modified: '#d29922', deleted: '#f85149', renamed: '#58a6ff', unchanged: '#6e7681',
}
const STATUS_MARK: Record<FileStatus, string> = { added: 'A', modified: 'M', deleted: 'D', renamed: 'R', unchanged: '·' }

function parseUnifiedToDiffLines(diffText: string): { type: string; content: string; lineNum: number }[] {
  const out: { type: string; content: string; lineNum: number }[] = []
  let n = 0
  for (const raw of (diffText || '').split('\n')) {
    if (/^(\+\+\+|---|diff |index |@@|new file|deleted file|rename |Binary |similarity)/.test(raw)) continue
    if (raw.startsWith('+')) out.push({ type: 'added', content: raw.slice(1), lineNum: ++n })
    else if (raw.startsWith('-')) out.push({ type: 'removed', content: raw.slice(1), lineNum: ++n })
  }
  return out
}

const S: Record<string, React.CSSProperties> = {
  dirRow: { padding: '2px 0', cursor: 'pointer', color: '#8b949e', userSelect: 'none' },
  arr: { color: '#586069', display: 'inline-block', width: 14 },
}

// 单文件预览: 图片直接出图(内嵌 base64), html 渲染, 其余看 diff。被内联展开与文件页签共用。
export function FilePreview({ file }: { file: FileEntry }) {
  const pv = file.preview
  if (pv?.kind === 'image') {
    if (pv.oversized || !pv.data_url) return <div style={{ color: '#8b949e', padding: 8, fontSize: 13 }}>图片过大未内嵌（{file.path}）</div>
    return <div style={{ padding: 8, background: '#fff', textAlign: 'center' }}><img src={pv.data_url} alt={file.path} style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain' }} /></div>
  }
  if (pv?.kind === 'html') {
    return <iframe data-testid="filetree-html-preview" srcDoc={pv.content || ''} sandbox="allow-same-origin" style={{ width: '100%', height: '60vh', border: 'none', background: '#fff' }} title={file.path} />
  }
  if (file.diff) {
    return (
      <ToolDiffViewer
        oldContent="" newContent={file.diff}
        filePath={file.old_path ? `${file.old_path} → ${file.path}` : file.path}
        createDiff={() => parseUnifiedToDiffLines(file.diff || '')}
        badge={file.status} badgeColor={file.status === 'added' ? 'green' : 'gray'}
      />
    )
  }
  return <div style={{ color: '#8b949e', padding: 8, fontSize: 13 }}>无可预览内容（{file.status}）</div>
}

function FileLeaf({ file, depth, material, onOpenFile }: { file: FileEntry; depth: number; material?: Material; onOpenFile?: (f: FileEntry) => void }) {
  const [open, setOpen] = useState(false)
  const canPreview = !!(file.diff || file.preview)
  const [annoting, setAnnoting] = useState(false)
  const [annoteText, setAnnoteText] = useState('')
  const [saved, setSaved] = useState<string | null>(file.annotation ?? null)
  const [toast, setToast] = useState('')
  const leaf = file.path.split('/').pop() || file.path
  const color = STATUS_COLOR[file.status] || COLORS.textDim

  const copyPath = (e: React.MouseEvent) => {
    e.preventDefault()
    void navigator.clipboard?.writeText(file.path)
    setToast('已复制路径'); setTimeout(() => setToast(''), 900)
  }
  const submitAnnote = async () => {
    if (!material || !annoteText.trim()) return
    try {
      await reviewstageApi.addAnnotation(material.id, annoteText.trim(), { kind: 'filetree_file', path: file.path })
      setSaved(annoteText.trim()); setAnnoteText(''); setAnnoting(false)
    } catch (e) {
      setToast(`批注失败: ${String(e instanceof Error ? e.message : e)}`); setTimeout(() => setToast(''), 1500)
    }
  }

  return (
    <div style={{ paddingLeft: 4 + depth * 12 }}>
      <div
        style={{
          padding: '2px 0', display: 'flex', alignItems: 'center', gap: 6,
          cursor: canPreview ? 'pointer' : 'default',
          borderLeft: file.status !== 'unchanged' ? `2px solid ${color}` : '2px solid transparent', paddingLeft: 8,
        }}
        title={file.path}
        onClick={() => canPreview && setOpen((v) => !v)}
        onContextMenu={copyPath}
      >
        <span style={{ color, fontWeight: 700, width: 12, flexShrink: 0, fontFamily: 'monospace' }}>{STATUS_MARK[file.status]}</span>
        <span style={{ color: file.status === 'unchanged' ? '#6e7681' : COLORS.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{leaf}</span>
        {(file.additions || file.deletions) ? (
          <span style={{ fontSize: 12, flexShrink: 0 }}>
            <span style={{ color: '#3fb950' }}>+{file.additions || 0}</span>{' '}
            <span style={{ color: '#f85149' }}>-{file.deletions || 0}</span>
          </span>
        ) : null}
        {onOpenFile && canPreview && (
          <button
            type="button"
            data-testid="filetree-open-file"
            onClick={(e) => { e.stopPropagation(); onOpenFile(file) }}
            style={{ marginLeft: material ? undefined : 'auto', background: 'transparent', border: 0, color: '#586069', cursor: 'pointer', fontSize: 12 }}
            title="在文件页签打开"
          >↗</button>
        )}
        {material && (
          <button
            type="button"
            data-testid="filetree-annotate"
            onClick={(e) => { e.stopPropagation(); setAnnoting((v) => !v) }}
            style={{ marginLeft: onOpenFile ? undefined : 'auto', background: 'transparent', border: 0, color: '#586069', cursor: 'pointer', fontSize: 12 }}
            title="批注此文件"
          >✎</button>
        )}
        {toast && <span style={{ color: '#3fb950', fontSize: 12 }}>{toast}</span>}
      </div>
      {saved && <div style={{ paddingLeft: 20, fontSize: 12, color: '#d29922' }}>批注: {saved}</div>}
      {annoting && (
        <div style={{ paddingLeft: 20, display: 'flex', gap: 6, margin: '4px 0' }}>
          <input
            data-testid="filetree-annotate-input"
            value={annoteText} onChange={(e) => setAnnoteText(e.target.value)}
            placeholder="对这个文件的改动写点说明…"
            style={{ flex: 1, background: '#0d1117', border: `1px solid ${COLORS.border}`, color: COLORS.text, borderRadius: 4, padding: '3px 6px', fontSize: 13 }}
            onKeyDown={(e) => { if (e.key === 'Enter') void submitAnnote() }}
          />
          <button type="button" onClick={() => void submitAnnote()} style={{ background: COLORS.borderActive, color: '#fff', border: 0, borderRadius: 4, padding: '3px 10px', cursor: 'pointer', fontSize: 13 }}>提交</button>
        </div>
      )}
      {open && (
        <div style={{ padding: '4px 0 8px 12px' }}>
          <FilePreview file={file} />
        </div>
      )}
    </div>
  )
}

function DirRow({ node, depth, forceExpand, material, onOpenFile }: { node: TreeNode; depth: number; forceExpand: boolean; material?: Material; onOpenFile?: (f: FileEntry) => void }) {
  const [expanded, setExpanded] = useState(true)
  const isOpen = forceExpand || expanded
  const childCount = useMemo(() => countChanged(node), [node])
  return (
    <div>
      {node.path !== '' && (
        <div style={{ ...S.dirRow, paddingLeft: 4 + depth * 12 }} onClick={() => setExpanded((v) => !v)} title={node.path}>
          <span style={S.arr}>{isOpen ? '▾' : '▸'}</span>
          {node.name}
          <span style={{ color: '#586069', marginLeft: 6, fontSize: 12 }}>{childCount}</span>
        </div>
      )}
      {isOpen && (
        <div>
          {[...node.children.values()].map((c) => (
            <DirRow key={c.path} node={c} depth={node.path === '' ? depth : depth + 1} forceExpand={forceExpand} material={material} onOpenFile={onOpenFile} />
          ))}
          {node.files.map((f) => (
            <FileLeaf key={f.path} file={f} depth={node.path === '' ? depth : depth + 1} material={material} onOpenFile={onOpenFile} />
          ))}
        </div>
      )}
    </div>
  )
}

function countChanged(node: TreeNode): number {
  let n = node.files.filter((f) => f.status !== 'unchanged').length
  for (const c of node.children.values()) n += countChanged(c)
  return n
}

export function FileTreeDiffView({ data, material, onOpenFile }: { data: FileTreeDiffData; material?: Material; onOpenFile?: (f: FileEntry) => void }) {
  const [showAll, setShowAll] = useState(false)
  const files = data.files || []
  const hasUnchanged = useMemo(() => files.some((f) => f.status === 'unchanged'), [files])
  const shown = useMemo(() => (showAll ? files : files.filter((f) => f.status !== 'unchanged')), [files, showAll])
  const tree = useMemo(() => buildTree(shown), [shown])
  const counts = data.counts || {}
  const src = data.source || {}

  return (
    <div data-testid="material-filetree-diff" style={{ height: '100%', overflow: 'auto', background: '#0a0d12', color: COLORS.text, fontFamily: 'Consolas, Menlo, monospace' }}>
      <div style={{ padding: '8px 12px', borderBottom: `1px solid ${COLORS.border}`, fontSize: 13, color: COLORS.textDim, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span>文件树 diff · {src.mode || '?'}{src.ref ? ` @ ${src.ref}` : ''}</span>
        <span>
          <span style={{ color: '#3fb950' }}>+{counts.added || 0}</span>{' '}
          <span style={{ color: '#d29922' }}>~{counts.modified || 0}</span>{' '}
          <span style={{ color: '#f85149' }}>-{counts.deleted || 0}</span>
          {counts.renamed ? <> <span style={{ color: '#58a6ff' }}>R{counts.renamed}</span></> : null}
          {' '}共 {counts.total || files.length}
        </span>
        {hasUnchanged && (
          <button
            type="button" data-testid="filetree-toggle-all"
            onClick={() => setShowAll((v) => !v)}
            style={{ marginLeft: 'auto', background: '#161b22', border: `1px solid ${COLORS.border}`, color: COLORS.text, borderRadius: 4, padding: '3px 10px', cursor: 'pointer', fontSize: 12 }}
          >{showAll ? '只看改动' : '显示全部'}</button>
        )}
      </div>
      <div style={{ padding: '6px 10px', fontSize: 14 }}>
        {shown.length === 0 ? <div style={{ color: COLORS.textDim, padding: 8 }}>没有改动文件。</div> : <DirRow node={tree} depth={0} forceExpand={false} material={material} onOpenFile={onOpenFile} />}
      </div>
    </div>
  )
}
