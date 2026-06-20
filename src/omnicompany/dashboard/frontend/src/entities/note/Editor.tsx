import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { fetchDetail, fetchLinks, saveNote, type NoteDetail, type NoteEntity, type NoteLinks } from './resolver'
import { usePanels } from '../../stores/panelsStore'
import { VSplitter } from '../../shell/Splitter'
import MarkdownRenderer from '../../shell/MarkdownRenderer'
import { type Annotation, listAnnotations, paragraphHash, snippetOf, extractText } from './annotations'
import AnnotatedParagraph from './AnnotationLayer'
import AnnotationModal from './AnnotationModal'

const MonacoEditor = React.lazy(() => import('@monaco-editor/react').then((m) => ({ default: m.default })))

const S: Record<string, any> = {
  root: { display: 'flex', flexDirection: 'column', height: '100%', background: '#0f0f0f', color: '#e0e0e0', fontFamily: 'Consolas, Menlo, monospace', overflow: 'hidden' },
  header: { padding: '6px 12px', borderBottom: '1px solid #222', background: '#0a0a0a', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8 },
  titleCol: { flex: 1, minWidth: 0 },
  title: { color: '#90caf9', fontSize: 14, marginBottom: 2, display: 'flex', alignItems: 'center', gap: 6 },
  dirty: { color: '#ffb74d', fontSize: 14 },
  path: { color: '#666', fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  modeBtn: (active: boolean): React.CSSProperties => ({
    padding: '3px 10px', border: '1px solid #2a3a4a', borderRadius: 4,
    background: active ? '#1a2a3a' : 'transparent', color: active ? '#90caf9' : '#666',
    cursor: 'pointer', fontSize: 14, fontFamily: 'inherit',
  }),
  saveBtn: { padding: '3px 12px', background: '#1a2a3a', border: '1px solid #2a3a4a', borderRadius: 4, color: '#90caf9', cursor: 'pointer', fontSize: 14, fontFamily: 'inherit' },
  saveBtnDisabled: { padding: '3px 12px', background: '#0d0d0d', border: '1px solid #1a1a1a', borderRadius: 4, color: '#444', cursor: 'not-allowed', fontSize: 14, fontFamily: 'inherit' },
  saveMsg: (ok: boolean): React.CSSProperties => ({ fontSize: 14, color: ok ? '#4caf50' : '#ef5350' }),
  body: { flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 },
  main: { flex: 1, overflow: 'auto', padding: 24, color: '#ccc', fontSize: 15, lineHeight: 1.6, fontFamily: 'system-ui, -apple-system, sans-serif', minWidth: 0 },
  editorWrap: { flex: 1, minHeight: 0, overflow: 'hidden' },
  splitPreview: { width: '50%', borderLeft: '1px solid #222', overflow: 'auto', padding: 24, color: '#ccc', fontSize: 15, lineHeight: 1.6, fontFamily: 'system-ui, -apple-system, sans-serif' },
  sidePanel: (w: number): React.CSSProperties => ({
    width: w, borderLeft: '1px solid #222', display: 'flex', flexDirection: 'column' as const,
    background: '#0a0a0a', flexShrink: 0, minWidth: 120, maxWidth: 600,
  }),
  sideHeader: { padding: '6px 10px', color: '#90caf9', fontSize: 14, borderBottom: '1px solid #222', textTransform: 'uppercase' as const, fontFamily: 'Consolas, Menlo, monospace' },
  sideList: { flex: 1, overflow: 'auto', padding: '4px 0' },
  link: { display: 'block', padding: '3px 12px', cursor: 'pointer', fontSize: 14, color: '#bbb', fontFamily: 'Consolas, Menlo, monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  unresolved: { display: 'block', padding: '3px 12px', fontSize: 14, color: '#666', fontFamily: 'Consolas, Menlo, monospace', fontStyle: 'italic' as const },
  annItem: { padding: '4px 12px', fontSize: 14, color: '#bbb', borderBottom: '1px solid #161616', cursor: 'pointer', fontFamily: 'Consolas, Menlo, monospace' },
  annSnippet: { color: '#666', fontSize: 14, fontStyle: 'italic' as const, marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  err: { padding: 24, color: '#ef5350' },
  empty: { padding: 24, color: '#666', fontStyle: 'italic' as const },
  emptyMini: { padding: '6px 12px', color: '#444', fontSize: 14, fontStyle: 'italic' as const },
}

/** Note-specific element wrappers that add annotation markers. Per user round 21 #7,
 *  every meaningful block-level element is annotatable: paragraphs, headings,
 *  list items, tables, blockquotes, and (non-language) code blocks. HR is a
 *  separator and intentionally NOT wrapped — it sits *between* annotatable blocks.
 *  Note: language-tagged code blocks bypass `pre` (they go to SyntaxHighlighter),
 *  so they're not annotatable for now — known limit, document in demo.
 */
const buildAnnotationOverride = (
  annotationsByHash: Map<string, Annotation[]>,
  onAdd: (hash: string, snippet: string) => void,
  onOpenThread: (hash: string) => void,
) => {
  const wrap = (Tag: keyof JSX.IntrinsicElements) =>
    ({ node, children }: any) => {
      const text = extractText(node)
      if (!text || text.length < 4) return React.createElement(Tag, {}, children)
      const hash = paragraphHash(text)
      const matched = annotationsByHash.get(hash) || []
      return (
        <AnnotatedParagraph
          hash={hash}
          snippet={snippetOf(text)}
          matched={matched}
          onAdd={onAdd}
          onOpen={onOpenThread}
        >
          {React.createElement(Tag, { 'data-anno-tag': Tag } as any, children)}
        </AnnotatedParagraph>
      )
    }

  return {
    p: wrap('p'),
    h1: wrap('h1'), h2: wrap('h2'), h3: wrap('h3'),
    h4: wrap('h4'), h5: wrap('h5'), h6: wrap('h6'),
    li: wrap('li'),
    table: wrap('table'),
    blockquote: wrap('blockquote'),
    pre: wrap('pre'),
  }
}

type Mode = 'view' | 'edit' | 'split'

export default function NoteEditor({ entity }: { entity: NoteEntity }) {
  const [detail, setDetail] = useState<NoteDetail | null>(null)
  const [links, setLinks] = useState<NoteLinks | null>(null)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('view')
  const [sideW, setSideW] = useState(260)
  const [draft, setDraft] = useState<string>('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [annoModal, setAnnoModal] = useState<{ anchor: { hash: string; snippet: string } | null; open: boolean }>({ anchor: null, open: false })
  const [livingHashes, setLivingHashes] = useState<Set<string>>(new Set())
  const openTab = usePanels((s) => s.openTab)
  const draftRef = useRef('')

  const loadAnnotations = (id: string) => {
    listAnnotations(id).then(setAnnotations).catch(() => setAnnotations([]))
  }

  useEffect(() => {
    let cancelled = false
    setDetail(null); setLinks(null); setAnnotations([]); setError(null); setDirty(false); setSaveMsg(null); setLivingHashes(new Set())
    fetchDetail(entity.id).then((d) => {
      if (cancelled) return
      setDetail(d)
      setDraft(d.content)
      draftRef.current = d.content
    }).catch((e) => { if (!cancelled) setError(String(e)) })
    fetchLinks(entity.id).then((l) => { if (!cancelled) setLinks(l) }).catch(() => {
      if (!cancelled) setLinks({ outgoing: [], outgoing_unresolved: [], backlinks: [] })
    })
    loadAnnotations(entity.id)
    return () => { cancelled = true }
  }, [entity.id])

  // Track which paragraph hashes exist in current rendered content (to detect orphan anchors)
  useEffect(() => {
    if (!detail) return
    // simple md paragraph splitter (reasonable approximation; ReactMarkdown agrees on \n\n bounds)
    const paragraphs = detail.content.split(/\n\s*\n/).filter((p) => p.trim().length >= 4)
    const hashes = new Set<string>()
    for (const p of paragraphs) {
      // remove markdown syntax to align with extractText (rough)
      const plain = p
        .replace(/^#+\s+/gm, '')
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/^\s*[-*+]\s+/gm, '')
        .replace(/^>\s*/gm, '')
      hashes.add(paragraphHash(plain))
    }
    setLivingHashes(hashes)
  }, [detail])

  const annotationsByHash = useMemo(() => {
    const map = new Map<string, Annotation[]>()
    for (const a of annotations) {
      const arr = map.get(a.anchor.hash) || []
      arr.push(a)
      map.set(a.anchor.hash, arr)
    }
    return map
  }, [annotations])

  const orphanAnnotations = useMemo(
    () => annotations.filter((a) => livingHashes.size > 0 && !livingHashes.has(a.anchor.hash)),
    [annotations, livingHashes],
  )

  const onChange = (v: string | undefined) => {
    const next = v || ''
    setDraft(next)
    draftRef.current = next
    setDirty(detail ? next !== detail.content : false)
    setSaveMsg(null)
  }

  const doSave = async () => {
    if (!detail || saving || !dirty) return
    setSaving(true); setSaveMsg(null)
    try {
      const r = await saveNote(entity.id, draftRef.current)
      setDetail({ ...detail, content: draftRef.current })
      setDirty(false)
      setSaveMsg({ ok: true, text: `已保存 (${r.size}B)` })
    } catch (e) {
      setSaveMsg({ ok: false, text: `保存失败: ${e}` })
    } finally { setSaving(false) }
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && mode !== 'view') {
        e.preventDefault(); doSave()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode, detail, dirty, saving])

  const switchMode = (next: Mode) => {
    if (next === 'view' && dirty) {
      if (!window.confirm('有未保存修改, 切换到只读模式会丢失. 继续?')) return
      setDraft(detail?.content || ''); draftRef.current = detail?.content || ''; setDirty(false)
    }
    setMode(next)
  }

  const jumpTo = (target: string) => {
    if (dirty && !window.confirm('有未保存修改, 跳到其他笔记会丢失. 继续?')) return
    openTab({ type: 'note', id: target }, target.split('/').pop() || target)
  }

  const openAdd = (hash: string, snippet: string) => setAnnoModal({ anchor: { hash, snippet }, open: true })
  const openThread = (hash: string) => {
    const matched = annotationsByHash.get(hash) || []
    const snippet = matched[0]?.anchor.snippet || ''
    setAnnoModal({ anchor: { hash, snippet }, open: true })
  }

  if (error) return <div style={{ ...S.root, ...S.err }}>加载失败: {error}</div>
  if (!detail) return <div style={{ ...S.root, ...S.empty }}>loading…</div>

  const linkedCount = links?.outgoing.length || 0
  const backlinkCount = links?.backlinks.length || 0
  const unresolvedCount = links?.outgoing_unresolved.length || 0
  const annCount = annotations.length

  const annoOverride = buildAnnotationOverride(annotationsByHash, openAdd, openThread)

  const previewNode = (
    <MarkdownRenderer
      source={mode === 'split' ? draft : detail.content}
      onWikilinkClick={jumpTo}
      componentsOverride={annoOverride}
      currentPath={entity.id}
    />
  )

  const modalExisting = annoModal.anchor
    ? (annotationsByHash.get(annoModal.anchor.hash) || [])
    : []

  return (
    <div style={S.root}>
      <div style={S.header}>
        <div style={S.titleCol}>
          <div style={S.title}>
            <span>{detail.title}</span>
            {dirty && <span style={S.dirty} title="未保存的修改">●</span>}
          </div>
          <div style={S.path}>{detail.path}</div>
        </div>
        <button style={S.modeBtn(mode === 'view')} onClick={() => switchMode('view')}>👁 只读</button>
        <button style={S.modeBtn(mode === 'edit')} onClick={() => switchMode('edit')}>✏ 编辑</button>
        <button style={S.modeBtn(mode === 'split')} onClick={() => switchMode('split')}>⊟ 分屏</button>
        <button
          style={dirty && !saving ? S.saveBtn : S.saveBtnDisabled}
          disabled={!dirty || saving}
          onClick={doSave}
          title="Ctrl+S"
        >
          {saving ? '保存中...' : '保存'}
        </button>
        {saveMsg && <span style={S.saveMsg(saveMsg.ok)}>{saveMsg.text}</span>}
      </div>
      <div style={S.body}>
        {mode === 'view' && <div style={S.main}>{previewNode}</div>}
        {mode === 'edit' && (
          <div style={S.editorWrap}>
            <Suspense fallback={<div style={S.empty}>loading editor…</div>}>
              <MonacoEditor value={draft} language="markdown" theme="vs-dark" onChange={onChange}
                options={{ minimap: { enabled: false }, fontSize: 14, wordWrap: 'on', scrollBeyondLastLine: false }} />
            </Suspense>
          </div>
        )}
        {mode === 'split' && (
          <>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Suspense fallback={<div style={S.empty}>loading editor…</div>}>
                <MonacoEditor value={draft} language="markdown" theme="vs-dark" onChange={onChange}
                  options={{ minimap: { enabled: false }, fontSize: 14, wordWrap: 'on', scrollBeyondLastLine: false }} />
              </Suspense>
            </div>
            <div style={S.splitPreview}>{previewNode}</div>
          </>
        )}
        <VSplitter onResize={(d) => setSideW((w) => Math.max(120, Math.min(600, w - d)))} side="left" />
        <div style={S.sidePanel(sideW)}>
          <div style={S.sideHeader}>批注 · {annCount}{orphanAnnotations.length > 0 ? ` (${orphanAnnotations.length} 失锚)` : ''}</div>
          <div style={S.sideList}>
            {annCount === 0 && <div style={S.emptyMini}>无批注. 鼠标悬停段落右侧 + 添加.</div>}
            {annotations.map((a) => {
              const orphan = !livingHashes.has(a.anchor.hash) && livingHashes.size > 0
              return (
                <div
                  key={a.id}
                  style={S.annItem}
                  onClick={() => openThread(a.anchor.hash)}
                  title={orphan ? '锚点失效 (段落已改/删)' : '点击查看 / 添加新评论'}
                >
                  <div style={{ ...S.annSnippet, color: orphan ? '#ef5350' : '#666' }}>
                    {orphan && '⚠ '}{a.anchor.snippet}
                  </div>
                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
                    {a.comment}
                  </div>
                </div>
              )
            })}
          </div>
          <div style={S.sideHeader}>反链 · {backlinkCount}</div>
          <div style={S.sideList}>
            {!links || backlinkCount === 0 ? (
              <div style={S.emptyMini}>{links ? '无反链' : '加载中...'}</div>
            ) : (
              links!.backlinks.map((b) => (
                <span key={b} style={S.link} title={b} onClick={() => jumpTo(b)}>← {b}</span>
              ))
            )}
          </div>
          <div style={S.sideHeader}>外链 · {linkedCount}{unresolvedCount > 0 ? ` (+${unresolvedCount} 未解析)` : ''}</div>
          <div style={S.sideList}>
            {linkedCount === 0 && unresolvedCount === 0 && <div style={S.emptyMini}>无外链</div>}
            {links?.outgoing.map((o) => (
              <span key={o} style={S.link} title={o} onClick={() => jumpTo(o)}>→ {o}</span>
            ))}
            {links?.outgoing_unresolved.map((o, i) => (
              <span key={`u-${i}`} style={S.unresolved} title={`未匹配的目标: ${o}`}>? {o}</span>
            ))}
          </div>
        </div>
      </div>
      <AnnotationModal
        noteId={entity.id}
        open={annoModal.open}
        anchor={annoModal.anchor}
        existing={modalExisting}
        onClose={() => setAnnoModal({ anchor: null, open: false })}
        onChange={() => loadAnnotations(entity.id)}
      />
    </div>
  )
}
