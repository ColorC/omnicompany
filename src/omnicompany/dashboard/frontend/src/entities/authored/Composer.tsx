/**
 * Composer — 统一写作组件(成熟编辑器形态)。顶部一条工具栏(图标), 下面干净的纯文本编辑区。
 * 用户只写纯文本 + 拖/贴/点按插图, 格式化与正式化交给 AI。到处复用(项目写草稿 / 草稿箱新建 / 实体旁评论)。
 */
import React, { useRef, useState } from 'react'
import { Image as ImageIcon, Save, X } from 'lucide-react'
import { authoredApi, type AuthoredNote, type NoteTarget } from '../../api/authoredClient'
import { colors as C, fontSize as FS, radius as R } from '../../shell/tokens'

interface Props {
  target?: NoteTarget
  uses?: string[]
  targetLabel?: string
  placeholder?: string
  autoFocus?: boolean
  feedbackStatus?: string
  fill?: boolean            // 撑满父容器宽高(正文区随高度铺满), 而非内容定高
  onSaved?: (n: AuthoredNote) => void
  onCancel?: () => void
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result || ''))
    r.onerror = () => reject(new Error('读取图片失败'))
    r.readAsDataURL(file)
  })
}

const toolBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
  height: 30, padding: '0 8px', background: 'transparent', color: C.textMuted,
  border: 'none', borderRadius: R.badges, cursor: 'pointer', fontSize: FS.small,
}

export default function Composer({
  target, uses, targetLabel, placeholder, autoFocus, feedbackStatus, fill, onSaved, onCancel,
}: Props) {
  const [content, setContent] = useState('')
  const [image, setImage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const addImage = async (f: File) => {
    try { setImage(await fileToDataUrl(f)) } catch (e) { setErr(String(e)) }
  }
  const onPaste = async (e: React.ClipboardEvent) => {
    for (const it of Array.from(e.clipboardData?.items || [])) {
      if (it.type.startsWith('image/')) { const f = it.getAsFile(); if (f) { e.preventDefault(); await addImage(f); return } }
    }
  }
  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false)
    const f = e.dataTransfer?.files?.[0]
    if (!f) return
    if (f.type.startsWith('image/')) await addImage(f)
    else setContent((c) => (c ? c + '\n' : '') + `[附件: ${f.name}]`)
  }
  const save = async () => {
    const text = content.trim()
    if ((!text && !image) || busy) return
    setBusy(true); setErr(null)
    try {
      const n = await authoredApi.create({
        content: text || '(图片)', target, uses: uses || ['draft'],
        feedback_status: feedbackStatus || 'saved', image_data_url: image || undefined,
      })
      setContent(''); setImage(null); onSaved?.(n)
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const canSave = !busy && (!!content.trim() || !!image)

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      style={{ border: `1px solid ${dragging ? C.accent : C.border}`, borderRadius: R.default, background: C.bgDoc, overflow: 'hidden', display: 'flex', flexDirection: 'column', ...(fill ? { flex: 1, minHeight: 0, width: '100%' } : {}) }}
      data-testid="composer"
    >
      {/* 工具栏: 左=插入工具(图标), 右=主操作 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 6px', borderBottom: `1px solid ${C.borderSubtle}` }}>
        <button type="button" style={toolBtn} title="插入图片(也可直接拖/粘贴)" onClick={() => fileRef.current?.click()}>
          <ImageIcon size={16} />
        </button>
        {targetLabel && <span style={{ fontSize: FS.small, color: C.textFaint, marginLeft: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>针对 {targetLabel}</span>}
        <div style={{ flex: 1 }} />
        {onCancel && <button type="button" style={toolBtn} title="取消" onClick={onCancel}><X size={16} /></button>}
        <button
          type="button" onClick={() => void save()} disabled={!canSave} title="保存(Ctrl/⌘+Enter)"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 14px', background: C.accent, color: '#fff', border: 'none', borderRadius: R.badges, fontSize: FS.body, fontWeight: 600, cursor: canSave ? 'pointer' : 'default', opacity: canSave ? 1 : 0.45 }}
        ><Save size={15} />{busy ? '保存中' : '保存'}</button>
      </div>

      <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) void addImage(f); e.target.value = '' }} />

      <textarea
        autoFocus={autoFocus}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onPaste={onPaste}
        onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); void save() } }}
        placeholder={placeholder || '随手写。纯文本 + 拖/贴/点上方图标插图,格式化和正式化交给 AI。'}
        spellCheck={false}
        style={{ width: '100%', boxSizing: 'border-box', resize: fill ? 'none' : 'vertical', background: 'transparent', color: C.text, border: 'none', outline: 'none', fontSize: FS.doc, lineHeight: 1.6, fontFamily: 'inherit', padding: '14px 16px', ...(fill ? { flex: 1, minHeight: 0 } : { minHeight: 160 }) }}
      />

      {image && (
        <div style={{ position: 'relative', alignSelf: 'flex-start', margin: '0 16px 12px' }}>
          <img src={image} alt="" style={{ maxHeight: 120, borderRadius: R.badges, border: `1px solid ${C.border}`, display: 'block' }} />
          <button type="button" onClick={() => setImage(null)} title="移除图片"
            style={{ position: 'absolute', top: -8, right: -8, width: 22, height: 22, borderRadius: 11, border: `1px solid ${C.border}`, background: C.bgCard, color: C.textMuted, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <X size={13} />
          </button>
        </div>
      )}
      {err && <div style={{ color: C.warning, fontSize: FS.small, padding: '0 16px 10px' }}>保存出错: {err}</div>}
    </div>
  )
}
