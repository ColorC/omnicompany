/**
 * CommentsFileView — 每材料一个评论 markdown 文件的视图(用户 2026-06-13/06-14)。
 * 评论落一个 .md, 一条 = 一个 `## [时间] 作者` 段。这里:
 * - 一层薄头(标题 + 在VSCode打开 + 复制路径 + 刷新 + 调用方塞的动作), 不写任何"我们这么做"的说明文字。
 * - 逐条渲染, 每条可就地"编辑/删除"(整文件存回); 也可点"在 VSCode 打开"开成页签直接改。
 * - 底部宽追加框。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { RefreshCw, Pencil, Trash2 } from 'lucide-react'
import { reviewstageApi, type Material } from '../../api/reviewstageClient'
import { createRenderer } from '@wiki-core/render'
import '@wiki-core/ui.css'
import { COLORS } from './shared'
import { openInVscode } from '../../lib/openInVscode'
import { VscodeIcon } from '../../components/VscodeIcon'

const md = createRenderer()
const btn: React.CSSProperties = { background: '#161b22', border: `1px solid ${COLORS.border}`, color: COLORS.text, borderRadius: 4, padding: '2px 8px', cursor: 'pointer', fontSize: 12 }
const linkBtn: React.CSSProperties = { ...btn, color: COLORS.borderActive }

interface Block { headerLine: string; anchorLine: string | null; body: string; meta: string }

function parseBlocks(text: string): Block[] {
  const out: Block[] = []
  let cur: { headerLine: string; anchorLine: string | null; bodyLines: string[] } | null = null
  for (const line of (text || '').split('\n')) {
    if (line.startsWith('## ')) {
      if (cur) out.push(finalize(cur))
      cur = { headerLine: line, anchorLine: null, bodyLines: [] }
    } else if (cur) {
      if (cur.bodyLines.length === 0 && cur.anchorLine === null && line.startsWith('> 锚点')) cur.anchorLine = line
      else cur.bodyLines.push(line)
    }
    // 首个 ## 之前的内容(历史预置说明等)直接丢弃 —— 文件即纯评论。
  }
  if (cur) out.push(finalize(cur))
  return out
}
function finalize(c: { headerLine: string; anchorLine: string | null; bodyLines: string[] }): Block {
  return { headerLine: c.headerLine, anchorLine: c.anchorLine, body: c.bodyLines.join('\n').trim(), meta: c.headerLine.replace(/^##\s*/, '') }
}
function blocksToFile(blocks: Block[]): string {
  return blocks.map((b) => `${b.headerLine}\n${b.anchorLine ? b.anchorLine + '\n' : ''}${b.body}\n`).join('\n').trim()
}

export function CommentsFileView({ material, pendingAnchor, clearPendingAnchor, title, headerActions }: {
  material: Material
  pendingAnchor?: string | null
  clearPendingAnchor?: () => void
  title?: string
  headerActions?: React.ReactNode
}) {
  const [content, setContent] = useState('')
  const [absPath, setAbsPath] = useState('')
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')
  const [editIdx, setEditIdx] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState('')

  const load = useCallback(() => {
    reviewstageApi.getCommentsFile(material.id, material.title)
      .then((r) => { setContent(r.content); setAbsPath(r.abs_path) })
      .catch(() => { /* 静默 */ })
  }, [material.id, material.title])
  useEffect(() => { load() }, [load])

  const blocks = useMemo(() => parseBlocks(content), [content])
  const flash = (m: string) => { setToast(m); setTimeout(() => setToast(''), 1000) }

  const append = async () => {
    const text = draft.trim()
    if (!text) return
    setBusy(true)
    try {
      const r = await reviewstageApi.appendCommentsFile(material.id, text, pendingAnchor || undefined, material.title)
      setContent(r.content); setDraft(''); clearPendingAnchor?.()
    } catch (e) { flash(`追加失败: ${String(e instanceof Error ? e.message : e)}`) } finally { setBusy(false) }
  }

  const saveFile = async (next: Block[]) => {
    setBusy(true)
    try { const r = await reviewstageApi.writeCommentsFile(material.id, blocksToFile(next)); setContent(r.content) }
    catch (e) { flash(`保存失败: ${String(e instanceof Error ? e.message : e)}`) } finally { setBusy(false) }
  }
  const saveEdit = async (i: number) => {
    const next = blocks.map((b, idx) => idx === i ? { ...b, body: editDraft.trim() } : b)
    setEditIdx(null); setEditDraft('')
    await saveFile(next)
  }
  const remove = async (i: number) => {
    if (typeof window !== 'undefined' && !window.confirm('删除这条评论?')) return
    await saveFile(blocks.filter((_, idx) => idx !== i))
  }

  return (
    <div data-testid="material-comments-file" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', background: COLORS.bg, color: COLORS.text }}>
      <div style={{ padding: '5px 10px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, flexShrink: 0 }}>
        <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={title || material.title}>评论 · {title || material.title}</span>
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <button type="button" style={{ ...linkBtn, display: 'inline-flex', alignItems: 'center' }} data-testid="comments-open-vscode" title="在 VSCode 打开此评论 .md 文件直接改/删" onClick={() => openInVscode(absPath)}><VscodeIcon size={14} /></button>
          <button type="button" style={{ ...btn, display: 'inline-flex', alignItems: 'center' }} data-testid="comments-refresh" onClick={load} title="刷新"><RefreshCw size={13} /></button>
          {toast && <span style={{ color: COLORS.accepted }}>{toast}</span>}
          {headerActions}
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {blocks.length === 0 && <div style={{ color: COLORS.textDim, fontSize: 13, padding: 6 }}>还没有评论。下面写一条。</div>}
        {blocks.map((b, i) => (
          <div key={i} data-testid="comment-block" style={{ border: `1px solid ${COLORS.border}`, borderRadius: 6, background: '#0d1117' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', borderBottom: `1px solid ${COLORS.border}`, fontSize: 12, color: COLORS.textDim }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.meta}</span>
              <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>
                {editIdx === i
                  ? <>
                      <button type="button" style={linkBtn} data-testid="comment-edit-save" onClick={() => void saveEdit(i)} disabled={busy}>保存</button>
                      <button type="button" style={btn} onClick={() => { setEditIdx(null); setEditDraft('') }}>取消</button>
                    </>
                  : <>
                      <button type="button" style={{ ...btn, display: 'inline-flex', alignItems: 'center' }} data-testid="comment-edit" title="编辑这条" onClick={() => { setEditIdx(i); setEditDraft(b.body) }}><Pencil size={13} /></button>
                      <button type="button" style={{ ...btn, color: COLORS.rejected, display: 'inline-flex', alignItems: 'center' }} data-testid="comment-delete" title="删除这条" onClick={() => void remove(i)} disabled={busy}><Trash2 size={13} /></button>
                    </>}
              </span>
            </div>
            {b.anchorLine && <div style={{ padding: '4px 8px 0', fontSize: 12, color: COLORS.borderActive }}>{b.anchorLine.replace(/^>\s*/, '')}</div>}
            {editIdx === i
              ? <textarea value={editDraft} onChange={(e) => setEditDraft(e.target.value)} data-testid="comment-edit-input"
                  style={{ width: '100%', boxSizing: 'border-box', minHeight: 80, padding: 8, background: '#0d1117', color: COLORS.text, border: 0, fontSize: 14, fontFamily: 'inherit', resize: 'vertical' }} />
              : <div className="wiki-prose" style={{ padding: '4px 12px 8px' }} dangerouslySetInnerHTML={{ __html: md.render(b.body || '') }} />}
          </div>
        ))}
      </div>

      <div style={{ borderTop: `1px solid ${COLORS.border}`, padding: 10, display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
        {pendingAnchor && (
          <div style={{ fontSize: 13, color: COLORS.borderActive }}>
            锚点(选中文本): {pendingAnchor.slice(0, 90)}
            <button type="button" style={{ ...btn, marginLeft: 8 }} onClick={clearPendingAnchor}>清除</button>
          </div>
        )}
        <textarea
          data-testid="comment-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="追加一条评论(支持 markdown)…"
          style={{ width: '100%', boxSizing: 'border-box', minHeight: 70, padding: 10, background: '#0d1117', color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 4, fontSize: 14, fontFamily: 'inherit', resize: 'vertical' }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button type="button" data-testid="comment-submit" onClick={() => void append()} disabled={!draft.trim() || busy}
            style={{ padding: '6px 16px', background: draft.trim() ? COLORS.borderActive : COLORS.border, color: '#fff', border: 0, borderRadius: 4, cursor: draft.trim() ? 'pointer' : 'default', fontSize: 14, fontWeight: 600 }}>
            {busy ? '…' : '追加评论'}
          </button>
        </div>
      </div>
    </div>
  )
}
