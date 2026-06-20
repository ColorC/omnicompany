/**
 * entities/review/MaterialViews — 5 类 material 渲染器 + 统一分发入口.
 *
 * R2 从 standalone 审阅台剪切而来 (结构搬移, 行为零变化); R4 起 standalone 已退役,
 * 消费方为驾驶舱 review_queue / review_material 面板.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { reviewstageApi, type Material } from '../../api/reviewstageClient'
import { buildSelectorPath } from '../../lib/iframePicker'
import { createRenderer, stripFrontmatter } from '@wiki-core/render'
import '@wiki-core/ui.css'
import { COLORS } from './shared'
import { FileTreeDiffView } from './FileTreeDiffView'
import { WebgameSpecView } from './WebgameSpecView'


// 块 5 R1: data_schema_id → 渲染组件注册表. 这里只有"分支剧情线"示例 + fallback.
// 新载体由 subagent 设计后, 走 PR / runtime 注册路径加进来 (元编程的 plumbing 是这层).
export const CUSTOM_TEMPLATE_REGISTRY: Record<string, (data: any, m?: Material) => React.ReactNode> = {
  'filetree_diff_v1': (data, m) => <FileTreeDiffView data={data} material={m} />,
  'branch_storyline_v1': (data) => (
    <div style={{ padding: 16, color: COLORS.text }}>
      <h2 style={{ marginTop: 0 }}>{data.title || '分支剧情线'}</h2>
      <div style={{ color: COLORS.textDim, fontSize: 14, marginBottom: 12 }}>
        节点: {(data.nodes || []).length} · 分支: {(data.branches || []).length}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {(data.nodes || []).map((n: any, i: number) => (
          <div key={i} style={{ padding: 12, background: COLORS.panel, borderRadius: 6, border: `1px solid ${COLORS.border}` }}>
            <div style={{ fontWeight: 600 }}>{n.id || `节点${i + 1}`}: {n.title}</div>
            <div style={{ fontSize: 15, marginTop: 6 }}>{n.body || ''}</div>
            {n.choices && n.choices.length > 0 && (
              <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: `2px solid ${COLORS.borderActive}` }}>
                {n.choices.map((c: any, j: number) => (
                  <div key={j} style={{ fontSize: 14, color: COLORS.textDim }}>
                    → {c.label} (去 {c.next})
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  ),
}


// ── Material 渲染组件 ──────────────────────────────────────────────

export function ImageMaterialView({ m }: { m: Material }) {
  const src = m.file_relpath
    ? reviewstageApi.fileUrl(m.id)
    : `data:image/png;base64,${m.inline_content || ''}`
  return (
    <div style={{ padding: 16, textAlign: 'center', background: '#0a0d12' }}>
      <img
        src={src}
        alt={m.title}
        style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain' }}
        data-testid="material-image"
      />
      {m.annotations.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 14, color: COLORS.textDim }}>
          {m.annotations.length} 个 AI 批注 — 见右侧批注栏
        </div>
      )}
    </div>
  )
}


export function MarkdownMaterialView({ m }: { m: Material }) {
  const [content, setContent] = useState<string>('')
  useEffect(() => {
    if (m.inline_content) {
      setContent(m.inline_content)
    } else if (m.file_relpath) {
      fetch(reviewstageApi.fileUrl(m.id)).then(r => r.text()).then(setContent)
    }
  }, [m.id, m.inline_content, m.file_relpath])

  // 共用 wiki 核渲染（obsidian flavor 全量: wikilink/callout/高亮/任务列表/数学等）。
  // DOM 仍是普通段落流, 圈选/批注的段落锚点机制不受影响。
  const html = useMemo(() => (content ? wikiMarkdown.render(stripFrontmatter(content)) : ''), [content])

  return (
    <div
      data-testid="material-markdown"
      className="wiki-prose"
      style={{
        padding: 24,
        background: '#0a0d12',
        color: COLORS.text,
        fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif',
        // 滚动唯一归 selection-surface（外层）；这里 height:100%+overflow:auto 会造出
        // 第二个滚动容器，且 padding 让它恒比外层高 48px → 双滚动条
        minHeight: '100%',
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

// markdown-it 实例可复用, 模块级建一份即可
const wikiMarkdown = createRenderer()


export function HtmlMaterialView({ m }: { m: Material }) {
  // 实时网页材料(如 walker-game): extra.live_url 经 dashboard 代理同源; 优先于落盘文件。
  const liveUrl = (m.extra as Record<string, unknown> | undefined)?.live_url as string | undefined
  const src = liveUrl ?? (m.file_relpath ? reviewstageApi.fileUrl(m.id) : undefined)
  const useSrcdoc = !src && !!m.inline_content
  // 元素圈选评论走 dashboard 全局捕获工具, 不在每条材料里再叠第二个(用户 2026-06-13)。
  // 全屏看网页本体走顶栏"在页签打开", 这里不再放重复按钮。整块就是网页本体, 让它占满。
  return (
    <iframe
      data-testid="material-html"
      src={src}
      srcDoc={useSrcdoc ? (m.inline_content || undefined) : undefined}
      sandbox="allow-same-origin allow-scripts"
      style={{ flex: 1, border: 'none', background: '#fff', width: '100%', minHeight: 0 }}
      title={m.title}
    />
  )
}


export function CustomTemplateMaterialView({ m }: { m: Material }) {
  let parsed: any = null
  try {
    parsed = m.inline_content ? JSON.parse(m.inline_content) : null
  } catch { /* */ }
  const schemaId = (m.extra && (m.extra as any).data_schema_id) as string | undefined
  const renderer = schemaId ? CUSTOM_TEMPLATE_REGISTRY[schemaId] : undefined

  return (
    <div data-testid="material-custom-template" style={{ height: '100%', overflow: 'auto', background: '#0a0d12' }}>
      <div style={{
        padding: '8px 16px', borderBottom: `1px solid ${COLORS.border}`,
        fontSize: 14, color: COLORS.textDim,
      }}>
        自定义网页模板 · schema={schemaId || '(none)'}
        {!renderer && schemaId && <span style={{ marginLeft: 8, color: COLORS.important }}>未注册 schema, fallback 显示 raw JSON</span>}
      </div>
      {parsed && renderer ? (
        renderer(parsed, m)
      ) : (
        <pre style={{ padding: 16, color: COLORS.text, fontSize: 14, whiteSpace: 'pre-wrap' }}>
          {parsed ? JSON.stringify(parsed, null, 2) : (m.inline_content || '(no content)')}
        </pre>
      )}
    </div>
  )
}


export function KeyQuestionMaterialView({ m }: { m: Material }) {
  let parsed: any = null
  try {
    parsed = m.inline_content ? JSON.parse(m.inline_content) : null
  } catch { /* */ }

  if (!parsed) {
    return <pre style={{ padding: 16, color: COLORS.text }}>{m.inline_content || '(no content)'}</pre>
  }
  const question = parsed.question || ''
  const options = parsed.options as string[] | undefined
  const explanation = parsed.explanation || ''

  return (
    <div data-testid="material-key-question" style={{ padding: 24, color: COLORS.text, height: '100%', overflow: 'auto' }}>
      <h2 style={{ marginTop: 0 }}>关键问题</h2>
      <div style={{
        background: COLORS.panel, padding: 16, borderRadius: 6,
        border: `2px solid ${COLORS.important}`, marginBottom: 16,
      }}>
        <div style={{ fontSize: 16, lineHeight: 1.6 }}>{question}</div>
      </div>
      {options && options.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {options.map((opt, i) => (
            <div key={i} style={{
              padding: 12, background: COLORS.panel, border: `1px solid ${COLORS.border}`,
              borderRadius: 6, cursor: 'pointer',
            }}>
              <span style={{ color: COLORS.textDim, marginRight: 8 }}>{String.fromCharCode(65 + i)}.</span>
              {opt}
            </div>
          ))}
        </div>
      )}
      {explanation && (
        <details style={{ marginTop: 16, color: COLORS.textDim }}>
          <summary>说明</summary>
          <div style={{ padding: 12 }}>{explanation}</div>
        </details>
      )}
    </div>
  )
}


// 文档里"选中文字就地评论"(用户 2026-06-14): 选一段 → 选区旁冒出"评论"小按钮 → 点开就地写 →
// 落进该材料的评论 .md(锚点=选中文字)。不依赖右侧评论栏是否在显示, 文档自带这条路。
function SelectionCommentLayer({ material, surfaceRef }: { material: Material; surfaceRef: React.RefObject<HTMLDivElement> }) {
  const [sel, setSel] = useState<{ text: string; x: number; y: number } | null>(null)
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => {
    const surface = surfaceRef.current
    if (!surface) return
    const onUp = () => {
      // 让点"评论"/在编辑框里的操作不被当成新选区(那些目标在本 layer 的 fixed 层, 不在 surface 内)。
      const s = window.getSelection()
      const text = s?.toString().replace(/\s+/g, ' ').trim() || ''
      if (!text || !s || s.rangeCount === 0 || !s.anchorNode || !surface.contains(s.anchorNode)) return
      const r = s.getRangeAt(0).getBoundingClientRect()
      const x = Math.min(Math.max(r.left + r.width / 2, 80), window.innerWidth - 200)
      setSel({ text: text.slice(0, 400), x, y: r.bottom })
      setComposing(false); setDraft('')
    }
    const clear = () => { setSel(null); setComposing(false) }
    surface.addEventListener('mouseup', onUp)
    surface.addEventListener('scroll', clear, true)
    return () => { surface.removeEventListener('mouseup', onUp); surface.removeEventListener('scroll', clear, true) }
  }, [surfaceRef])

  const submit = async () => {
    const text = draft.trim()
    if (!text || !sel) return
    setBusy(true)
    try {
      await reviewstageApi.appendCommentsFile(material.id, text, sel.text, material.title)
      setSel(null); setComposing(false); setDraft('')
      window.getSelection()?.removeAllRanges()
      setToast('已评论'); setTimeout(() => setToast(''), 1200)
    } catch (e) {
      setToast(`失败: ${String(e instanceof Error ? e.message : e)}`); setTimeout(() => setToast(''), 1600)
    } finally { setBusy(false) }
  }

  return (
    <>
      {sel && !composing && (
        <button
          type="button"
          data-testid="selection-comment-btn"
          onMouseDown={(e) => e.preventDefault()} // 别让点击清掉选区
          onClick={() => setComposing(true)}
          style={{ position: 'fixed', left: sel.x, top: sel.y + 6, transform: 'translateX(-50%)', zIndex: 95, display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px', background: COLORS.borderActive, color: '#fff', border: 0, borderRadius: 14, cursor: 'pointer', fontSize: 13, fontWeight: 600, boxShadow: '0 6px 16px rgba(0,0,0,.4)' }}
        >💬 评论</button>
      )}
      {sel && composing && (
        <div
          data-testid="selection-comment-composer"
          onMouseDown={(e) => e.stopPropagation()}
          style={{ position: 'fixed', left: sel.x, top: sel.y + 6, transform: 'translateX(-50%)', zIndex: 95, width: 320, maxWidth: '90vw', background: '#0d1117', border: `1px solid ${COLORS.border}`, borderRadius: 8, boxShadow: '0 14px 40px rgba(0,0,0,.5)', padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}
        >
          <div style={{ fontSize: 12, color: COLORS.borderActive, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>锚点: {sel.text.slice(0, 60)}{sel.text.length > 60 ? '…' : ''}</div>
          <textarea
            autoFocus
            data-testid="selection-comment-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') void submit() }}
            placeholder="对选中文字写评论(Ctrl+Enter 提交)…"
            style={{ width: '100%', boxSizing: 'border-box', minHeight: 64, padding: 8, background: '#0a0d12', color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 4, fontSize: 14, fontFamily: 'inherit', resize: 'vertical' }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
            <button type="button" onClick={() => { setSel(null); setComposing(false) }} style={{ padding: '4px 10px', background: 'transparent', color: COLORS.textDim, border: `1px solid ${COLORS.border}`, borderRadius: 4, cursor: 'pointer', fontSize: 13 }}>取消</button>
            <button type="button" data-testid="selection-comment-submit" disabled={!draft.trim() || busy} onClick={() => void submit()} style={{ padding: '4px 14px', background: draft.trim() ? COLORS.borderActive : COLORS.border, color: '#fff', border: 0, borderRadius: 4, cursor: draft.trim() ? 'pointer' : 'default', fontSize: 13, fontWeight: 600 }}>{busy ? '…' : '提交'}</button>
          </div>
        </div>
      )}
      {toast && <div style={{ position: 'fixed', left: '50%', bottom: 24, transform: 'translateX(-50%)', zIndex: 96, background: '#161b22', color: COLORS.accepted, border: `1px solid ${COLORS.border}`, borderRadius: 6, padding: '6px 14px', fontSize: 13 }}>{toast}</div>}
    </>
  )
}

// 统一分发: 按 m.kind 分发到上面 5 个渲染器 (原 MaterialDetail 内的 switch 逻辑).
// onMouseUp 文本选择 / data-testid="material-selection-surface" 随原样保留.
export function MaterialContentView({ m, onElementSelect, onTextSelection }: {
  m: Material
  onElementSelect: (selector: string) => void
  onTextSelection?: () => void
}) {
  // webgame-spec / html 是"占满型"(内含 iframe / 复合视图): 用 flex 撑满, 让里面的 iframe flex:1 能拉满高度,
  // 否则 iframe 在非 flex 容器里 flex:1 失效 → 回落到默认 150px(就是"网页框好小"的根因)。
  // 其余(图/文档/JSON)是文档型, overflow:auto 滚动。
  const fullBleed = (m.kind as string) === 'webgame-spec' || m.kind === 'html'
  // 文档型(文字内容)才挂"选中即评论"层; 图/网页/复合视图不挂。
  const isDocument = m.kind === 'markdown' || m.kind === 'key_question' || m.kind === 'custom_web_template'
  const surfaceRef = useRef<HTMLDivElement>(null)
  return (
    <div
      ref={surfaceRef}
      style={{ flex: 1, minWidth: 0, minHeight: 0, ...(fullBleed ? { display: 'flex', flexDirection: 'column' } : { overflow: 'auto' }) }}
      onMouseUp={onTextSelection}
      data-testid="material-selection-surface"
    >
      {m.kind === 'image' && <ImageMaterialView m={m} />}
      {m.kind === 'markdown' && <MarkdownMaterialView m={m} />}
      {m.kind === 'html' && <HtmlMaterialView m={m} />}
      {m.kind === 'key_question' && <KeyQuestionMaterialView m={m} />}
      {m.kind === 'custom_web_template' && <CustomTemplateMaterialView m={m} />}
      {(m.kind as string) === 'webgame-spec' && <WebgameSpecView m={m} />}
      {isDocument && <SelectionCommentLayer material={m} surfaceRef={surfaceRef} />}
    </div>
  )
}
