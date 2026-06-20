// 项目详情页 — 从首页项目卡点开。上半: 项目头(背景/名称/标签/roots/index 路径/快速工作选项);
// 下半: 计划 / 对话 / 文件 / 审阅 / index 五个内页签, 把散在各处的项目相关物聚到一个入口
// (计划=docs/plans 关联类目; 对话=cc sessions 的 active_plan 归属; 审阅=reviewstage 按 plan 过滤)。
// 快速工作选项来自 PROJECT_INDEX.md frontmatter 的 quick_actions(skill 注册表), 总控走
// omni project show 看到同一份。

import React, { useEffect, useMemo, useState } from 'react'
import { Copy, Check, ExternalLink } from 'lucide-react'
import { projectsApi, createPlan, type ProjectItem, type ProjectIndexDoc, type ProjectQuickAction, type ProjectFindings } from '../../api/projectsClient'
import { ccApi } from '../../api/ccClient'
import { reviewstageApi, type Material } from '../../api/reviewstageClient'
import { usePanels } from '../../stores/panelsStore'
import MarkdownRenderer from '../../shell/MarkdownRenderer'
import { copyText } from '../../lib/copyText'
import { openInVscode } from '../../lib/openInVscode'
import { relTimeZh as relTime } from '../../lib/time'
import NotesForTarget from '../authored/NotesForTarget'
import Composer from '../authored/Composer'
import { colors as TC, fontSize as TFS, radius as TR } from '../../shell/tokens'
import NewPlanPanel from './NewPlanPanel'

type TabKey = 'plans' | 'convos' | 'teams' | 'files' | 'reviews' | 'evidence' | 'index' | 'authored'

// 项目→内置网页 demo(web_review 实体目标 id)。有 demo 的项目在工作台直达, 消除"项目页与 demo 割裂"。
const DEMO_BY_PROJECT: Record<string, string> = { vilo: 'vilo-demo', walker: 'walker-game' }

const S: Record<string, any> = {
  root: { height: '100%', overflow: 'auto', background: '#0a0a0a', color: '#e6edf3', boxSizing: 'border-box' },
  hero: { position: 'relative', minHeight: 120, borderBottom: '1px solid #1d2630', display: 'flex', alignItems: 'flex-end' },
  heroBg: { position: 'absolute', inset: 0 },
  // 压暗层(2026-06-12 用户: 图片背景撞色压字)
  heroOverlay: { position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(4,7,10,.95) 8%, rgba(4,7,10,.66) 55%, rgba(4,7,10,.30) 100%)' },
  heroInner: { position: 'relative', padding: '14px 18px 12px', width: '100%', boxSizing: 'border-box' },
  name: { fontSize: 20, fontWeight: 750, color: '#fff', textShadow: '0 1px 4px rgba(0,0,0,.95)' },
  desc: { color: 'rgba(255,255,255,.88)', fontSize: 14, marginTop: 4, textShadow: '0 1px 3px rgba(0,0,0,.9)' },
  metaRow: { display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 8, alignItems: 'center' },
  chip: { display: 'inline-flex', alignItems: 'center', gap: 4, border: '1px solid rgba(255,255,255,.28)', borderRadius: 4, padding: '1px 6px', fontSize: 13, color: '#fff', background: 'rgba(0,0,0,.35)' },
  body: { padding: '12px 18px 30px' },
  secTitle: { color: '#9fb2c6', fontSize: 15, fontWeight: 700, margin: '14px 0 6px' },
  qaGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 8 },
  qaCard: { border: '1px solid #21303f', borderRadius: 7, padding: '8px 10px', background: '#0d1318' },
  qaLabel: { color: '#e6edf3', fontSize: 14.5, fontWeight: 650 },
  qaDesc: { color: '#a8b0ba', fontSize: 13, marginTop: 2, lineHeight: 1.4 },
  qaMeta: { display: 'flex', gap: 6, marginTop: 6, alignItems: 'center', flexWrap: 'wrap' },
  skillChip: { border: '1px solid #2f81f7', color: '#79c0ff', borderRadius: 4, padding: '0 6px', fontSize: 13, background: '#10233a' },
  noSkill: { border: '1px solid #5a4a18', color: '#d29922', borderRadius: 4, padding: '0 6px', fontSize: 13, background: '#211a07' },
  copyMini: { height: 22, border: '1px solid #263443', background: '#101820', color: '#b8c7d9', borderRadius: 4, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0 7px', fontSize: 13 },
  pathRow: { display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0', color: '#c2cdd8', fontSize: 14, fontFamily: 'Consolas, monospace' },
  tabs: { display: 'flex', gap: 4, borderBottom: '1px solid #1d2630', margin: '16px 0 10px' },
  tab: (active: boolean): React.CSSProperties => ({ border: 'none', borderBottom: active ? '2px solid #2f81f7' : '2px solid transparent', background: 'transparent', color: active ? '#79c0ff' : '#a8b0ba', padding: '6px 10px', cursor: 'pointer', fontSize: 14.5, fontWeight: active ? 650 : 400 }),
  row: { display: 'flex', alignItems: 'baseline', gap: 8, padding: '5px 8px', border: '1px solid #18222d', borderRadius: 6, marginBottom: 4, cursor: 'pointer' },
  rowTitle: { color: '#e6edf3', fontSize: 14, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  rowMeta: { color: '#a0a3aa', fontSize: 13, flexShrink: 0 },
  dim: { color: '#9aa3ad', fontSize: 14, padding: '6px 2px' },
  warn: { color: '#d29922', fontSize: 14, padding: '6px 2px' },
}

function CopyBtn({ text, label = '复制' }: { text: string; label?: string }) {
  const [state, setState] = useState<'idle' | 'done' | 'fail'>('idle')
  return (
    <button type="button" style={S.copyMini} title={text} onClick={() => {
      void copyText(text).then((ok) => {
        setState(ok ? 'done' : 'fail')
        window.setTimeout(() => setState('idle'), 1400)
      })
    }}>
      {state === 'done' ? <Check size={11} /> : <Copy size={11} />}
      {state === 'done' ? '已复制' : state === 'fail' ? '复制失败' : label}
    </button>
  )
}

/** 在 VSCode 打开文件/目录 — webview 里走 open-file 消息桥, 浏览器里走 vscode:// 协议。 */
function OpenBtn({ path, label = '打开' }: { path: string; label?: string }) {
  return (
    <button type="button" style={S.copyMini} data-testid="open-in-vscode" title={`在 VSCode 打开\n${path}`} onClick={(e) => {
      e.stopPropagation()
      openInVscode(path)
    }}>
      <ExternalLink size={11} />{label}
    </button>
  )
}

function heroBackground(p?: ProjectItem | null): string {
  const bg = (p?.bg || '').trim()
  if (bg && (/^(https?:|data:|\/|\.\/)/.test(bg) || /\.(png|jpe?g|webp)(\?|$)/i.test(bg))) {
    return `center/cover no-repeat url("${bg.replace(/"/g, '%22')}")`
  }
  return bg || 'linear-gradient(120deg, #16344c 0%, #0a0d10 95%)'
}

function QuickActions({ actions }: { actions: ProjectQuickAction[] }) {
  if (!actions.length) return <div style={S.dim}>index 文件还没注册快速工作选项 (frontmatter.quick_actions)。</div>
  return (
    <div style={S.qaGrid} data-testid="project-quick-actions">
      {actions.map((a, i) => (
        <div key={i} style={S.qaCard}>
          <div style={S.qaLabel}>{a.label}</div>
          {a.desc && <div style={S.qaDesc}>{a.desc}</div>}
          <div style={S.qaMeta}>
            {a.skill
              ? <span style={S.skillChip} title="绑定的 skill">/{a.skill}</span>
              : <span style={S.noSkill} title="尚无绑定 skill">待建技能</span>}
            {a.skill && <CopyBtn text={`/${a.skill}`} label="复制技能" />}
            {a.where && <CopyBtn text={a.where} label="复制目录" />}
            {a.where && <OpenBtn path={a.where} />}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function ProjectDetail({ entity }: { entity: { id: string }; facet?: string }) {
  const [proj, setProj] = useState<ProjectItem | null>(null)
  const [indexDoc, setIndexDoc] = useState<ProjectIndexDoc | null>(null)
  const [plans, setPlans] = useState<{ id: string; title: string; date?: string; archived?: boolean }[] | null>(null)
  const [planIds, setPlanIds] = useState<Set<string> | null>(null)
  const [convos, setConvos] = useState<{ id: string; title: string; ts?: string | null }[] | null>(null)
  const [reviews, setReviews] = useState<Material[] | null>(null)
  const [findings, setFindings] = useState<ProjectFindings | null>(null)
  const [teams, setTeams] = useState<any[] | null>(null)  // 管线(team*.py), 按项目 roots 归属
  const [tab, setTab] = useState<TabKey>('plans')
  const [composeMode, setComposeMode] = useState<'none' | 'plan' | 'draft'>('none')
  const [reloadKey, setReloadKey] = useState(0)
  const openTab = usePanels((s) => s.openTab)

  useEffect(() => {
    projectsApi.list().then((b) => setProj(b.projects.find((p) => p.id === entity.id) || null)).catch(() => setProj(null))
    projectsApi.index(entity.id).then(setIndexDoc).catch(() => setIndexDoc(null))
    // 计划归属由服务端唯一判定(治理覆盖表优先, core.resolve_project_plans) —
    // 2026-06-12 用户: 各项目计划列表全错; 前端不再自带一份前缀匹配逻辑。
    projectsApi.plans(entity.id).then((d) => {
      setPlans(d.items.map((p) => ({
        id: p.id,
        title: `${p.date ? p.date + ' ' : ''}${p.title_zh || p.topic}${p.archived ? ' (已归档)' : ''}`,
        date: p.date,
        archived: p.archived,
      })))
      setPlanIds(new Set(d.plan_ids))
    }).catch(() => { setPlans([]); setPlanIds(new Set()) })
    // 工作历史证据(重复需求/指正) — 治理部门 work_history 的项目分配结果
    projectsApi.findings(entity.id).then(setFindings).catch(() => setFindings(null))
    // 管线(team*.py): 取全量, 下面按本项目 roots 归属(roots 已校准到 packages/ 包根)
    fetch('/api/teams').then((r) => (r.ok ? r.json() : { items: [] })).then((d) => setTeams((d.items as any[]) || [])).catch(() => setTeams([]))
  }, [entity.id, reloadKey])

  useEffect(() => {
    if (!planIds) return
    const inProject = (planId?: string | null) => !!planId && planIds.has(planId)
    ccApi.list().then((ss: any[]) => {
      setConvos(ss
        .filter((s) => inProject(s.active_plan))
        .map((s) => ({ id: s.id, title: s.title || s.preview || s.id, ts: s.updated_at || s.created_at })))
    }).catch(() => setConvos([]))
    reviewstageApi.list({}).then((full) => {
      setReviews(full.items.filter((m) => inProject(m.source_plan_id)))
    }).catch(() => setReviews([]))
  }, [planIds])

  // 本项目的管线: team 源文件落在项目 roots 下(roots 已校准到 packages/ 包根, 引用级源文件归属)
  const projTeams = useMemo(() => {
    if (!teams || !proj) return [] as any[]
    const norm = (p?: string) => (p || '').replace(/\\/g, '/').toLowerCase().replace(/\/+$/, '')
    const roots = (proj.roots || []).map(norm).filter(Boolean)
    return teams.filter((t) => {
      const f = norm(t.file_path)
      return !!f && roots.some((r) => f === r || f.startsWith(r + '/'))
    })
  }, [teams, proj])

  const indexBody = useMemo(() => {
    const c = indexDoc?.content || ''
    return c.replace(/\A?^---[\s\S]*?\n---\s*\n/, '')
  }, [indexDoc])

  const filePaths: { path: string; note?: string }[] = useMemo(() => {
    const fm = (indexDoc?.data || {}) as any
    const fromIndex = [...(fm.roots || []), ...(fm.entry_points || [])]
      .filter((x: any) => x && x.path)
      .map((x: any) => ({ path: String(x.path), note: x.note ? String(x.note) : undefined }))
    if (fromIndex.length) return fromIndex
    return (proj?.roots || []).map((r) => ({ path: r }))
  }, [indexDoc, proj])

  return (
    <div style={S.root} data-testid="project-detail">
      <div style={S.hero}>
        <div style={{ ...S.heroBg, background: heroBackground(proj) }} />
        <div style={S.heroOverlay} />
        <div style={S.heroInner}>
          <div style={S.name}>{proj?.name || entity.id}</div>
          {proj?.desc && <div style={S.desc}>{proj.desc}</div>}
          <div style={S.metaRow}>
            {(proj?.tags || []).map((t) => <span key={t} style={S.chip}>{t}</span>)}
            <span style={S.chip}>活跃 {relTime(proj?.last_active)}</span>
            {proj?.index_path && (
              <span style={S.chip} data-testid="project-detail-index-path">
                index {proj.index_ok === false ? '⚠' : ''}
                <CopyBtn text={proj.index_path} label="复制路径" />
                <OpenBtn path={proj.index_path} />
              </span>
            )}
            {(proj?.links || []).map((l, i) => (
              <a key={i} href={l.url} target="_blank" rel="noreferrer" style={{ ...S.chip, textDecoration: 'none' }}>
                <ExternalLink size={11} />{l.label}
              </a>
            ))}
          </div>
        </div>
      </div>

      <div style={S.body}>
        {/* 主操作: 进项目就能一键写 —— 计划书 / 草稿(纯文本, 格式化交给 AI) */}
        <div style={{ display: 'flex', gap: 10, marginBottom: composeMode === 'none' ? 4 : 12, flexWrap: 'wrap' }}>
          <button
            type="button" data-testid="project-new-plan"
            onClick={() => setComposeMode((m) => (m === 'plan' ? 'none' : 'plan'))}
            style={{ background: composeMode === 'plan' ? TC.accentBg : TC.accent, color: composeMode === 'plan' ? TC.accent : '#fff', border: `1px solid ${TC.accent}`, borderRadius: TR.default, padding: '8px 16px', fontSize: TFS.body, fontWeight: 600, cursor: 'pointer' }}
          >＋ 新建计划书</button>
          <button
            type="button" data-testid="project-write-draft"
            onClick={() => setComposeMode((m) => (m === 'draft' ? 'none' : 'draft'))}
            style={{ background: 'transparent', color: TC.text, border: `1px solid ${TC.border}`, borderRadius: TR.default, padding: '8px 16px', fontSize: TFS.body, fontWeight: 600, cursor: 'pointer' }}
          >＋ 写草稿</button>
          {DEMO_BY_PROJECT[entity.id] && (
            <button
              type="button" data-testid="project-open-demo"
              onClick={() => openTab({ type: 'web_review', id: DEMO_BY_PROJECT[entity.id] }, `${proj?.name || entity.id} Demo`)}
              style={{ marginLeft: 'auto', background: 'transparent', color: TC.link, border: `1px solid ${TC.border}`, borderRadius: TR.default, padding: '8px 16px', fontSize: TFS.body, fontWeight: 600, cursor: 'pointer' }}
            >▶ 打开 Demo</button>
          )}
        </div>
        {composeMode === 'plan' && (
          <div style={{ marginBottom: 16 }}>
            <NewPlanPanel
              projectId={entity.id}
              onCreated={() => { setComposeMode('none'); setReloadKey((k) => k + 1); setTab('plans') }}
              onCancel={() => setComposeMode('none')}
            />
          </div>
        )}
        {composeMode === 'draft' && (
          <div style={{ marginBottom: 16 }}>
            <Composer
              target={{ kind: 'project', id: entity.id, title: proj?.name || entity.id }}
              uses={['draft']}
              targetLabel={`项目 ${proj?.name || entity.id}`}
              autoFocus
              onSaved={() => { setComposeMode('none'); if (tab === 'authored') setReloadKey((k) => k + 1) }}
              onCancel={() => setComposeMode('none')}
            />
          </div>
        )}
        <div style={S.secTitle}>常用工作选项</div>
        {proj?.index_ok === false && <div style={S.warn}>index 文件校验未通过: {proj.index_error}</div>}
        <QuickActions actions={proj?.quick_actions || []} />

        <div style={S.tabs}>
          {([['plans', `计划 ${plans ? `(${plans.length})` : ''}`], ['convos', `对话 ${convos ? `(${convos.length})` : ''}`], ['teams', `管线 ${teams ? `(${projTeams.length})` : ''}`], ['files', '文件'], ['reviews', `审阅 ${reviews ? `(${reviews.length})` : ''}`], ['evidence', `历史证据 ${findings ? `(${findings.needs.length + findings.corrections.length})` : ''}`], ['authored', '札记'], ['index', 'index 正文']] as [TabKey, string][]).map(([k, label]) => (
            <button key={k} type="button" style={S.tab(tab === k)} data-testid={`project-tab-${k}`} onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>

        {tab === 'plans' && (
          <div data-testid="project-plans">
            {plans === null && <div style={S.dim}>加载中…</div>}
            {plans?.length === 0 && <div style={S.dim}>无关联计划 (归属由治理覆盖表 + 注册表类目决定, 服务端判定)。</div>}
            {plans?.map((p) => (
              <div key={p.id} style={S.row} onClick={() => openTab({ type: 'plan', id: p.id }, p.title)}>
                <span style={S.rowTitle}>{p.title}</span>
                <span style={S.rowMeta}>{p.id}</span>
              </div>
            ))}
          </div>
        )}
        {tab === 'convos' && (
          <div data-testid="project-convos">
            {convos === null && <div style={S.dim}>加载中…</div>}
            {convos?.length === 0 && <div style={S.dim}>没有归属本项目计划的对话 (按会话 active_plan 归属)。</div>}
            {convos?.map((s) => (
              <div key={s.id} style={S.row} onClick={() => openTab({ type: 'cc_session', id: s.id }, s.title)}>
                <span style={S.rowTitle}>{s.title}</span>
                <span style={S.rowMeta}>{relTime(s.ts)}</span>
              </div>
            ))}
          </div>
        )}
        {tab === 'teams' && (
          <div data-testid="project-teams">
            {teams === null && <div style={S.dim}>加载中…</div>}
            {teams && projTeams.length === 0 && <div style={S.dim}>本项目 roots 下没有管线(team)。归属 = 管线源文件落在项目 roots(已校准到 packages/ 包根)。</div>}
            {projTeams.map((t) => (
              <div key={t.id} style={S.row} onClick={() => openTab({ type: 'team', id: t.id }, (t.package || '').split('/').filter(Boolean).pop() || t.id)}>
                <span style={S.rowTitle}>{(t.package || '').split('/').filter(Boolean).pop() || t.name}</span>
                <span style={S.rowMeta}>{t.package}</span>
              </div>
            ))}
          </div>
        )}
        {tab === 'files' && (
          <div data-testid="project-files">
            {filePaths.length === 0 && <div style={S.dim}>index 文件未注册目录 (frontmatter.roots / entry_points)。</div>}
            {filePaths.map((f, i) => (
              <div key={i} style={S.pathRow}>
                <OpenBtn path={f.path} />
                <CopyBtn text={f.path} label="复制" />
                <span
                  style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }}
                  title="点击在 VSCode 打开"
                  onClick={() => openInVscode(f.path)}
                >{f.path}</span>
                {f.note && <span style={S.rowMeta}>· {f.note}</span>}
              </div>
            ))}
          </div>
        )}
        {tab === 'reviews' && (
          <div data-testid="project-reviews">
            {reviews === null && <div style={S.dim}>加载中…</div>}
            {reviews?.length === 0 && <div style={S.dim}>无本项目的审阅材料。</div>}
            {reviews?.map((m) => (
              <div key={m.id} style={S.row} onClick={() => openTab({ type: 'review_material', id: m.id }, (m as any).title || m.id)}>
                <span style={S.rowTitle}>{(m as any).title || m.id}</span>
                <span style={S.rowMeta}>{m.source_plan_id || ''} · {(m as any).status || ''}</span>
              </div>
            ))}
          </div>
        )}
        {tab === 'evidence' && (
          <div data-testid="project-evidence">
            {findings === null && <div style={S.dim}>还没有工作历史整理产物 (omni governance history-run + history-assign)。</div>}
            {findings && findings.needs.length + findings.corrections.length === 0 && (
              <div style={S.dim}>最近一轮整理没有分配到本项目的重复需求/指正。</div>
            )}
            {findings && findings.needs.length > 0 && (<>
              <div style={S.secTitle}>重复需求 — 你反复让 AI 干的活(近 {findings.days} 天)</div>
              {findings.needs.map((n, i) => (
                <div key={i} style={{ ...S.row, cursor: 'default', display: 'block' }}>
                  <div style={S.rowTitle}>{n.title} <span style={S.rowMeta}>×{n.count}</span></div>
                  {(n.examples || []).slice(0, 2).map((q, j) => (
                    <div key={j} style={{ color: '#a8b0ba', fontSize: 13, marginTop: 2 }}>「{q}」</div>
                  ))}
                  {n.quick_action_hint && <div style={{ color: '#d29922', fontSize: 13, marginTop: 2 }}>建议: {n.quick_action_hint}</div>}
                </div>
              ))}
            </>)}
            {findings && findings.corrections.length > 0 && (<>
              <div style={S.secTitle}>重复指正 — 你反复纠偏的内容</div>
              {findings.corrections.map((c, i) => (
                <div key={i} style={{ ...S.row, cursor: 'default', display: 'block' }}>
                  <div style={S.rowTitle}>
                    {c.title} <span style={S.rowMeta}>×{c.count}</span>
                    {c.already_in_memory === false && <span style={{ color: '#d29922', fontSize: 13, marginLeft: 6 }}>未沉淀</span>}
                  </div>
                  {(c.examples || []).slice(0, 2).map((q, j) => (
                    <div key={j} style={{ color: '#a8b0ba', fontSize: 13, marginTop: 2 }}>「{q}」</div>
                  ))}
                </div>
              ))}
            </>)}
          </div>
        )}
        {tab === 'authored' && (
          <div data-testid="project-authored">
            <NotesForTarget
              kind="project"
              id={entity.id}
              title={proj?.name || entity.id}
              heading="本项目的札记(评论/草稿)"
            />
          </div>
        )}
        {tab === 'index' && (
          <div data-testid="project-index-body">
            {!indexDoc?.content && <div style={S.dim}>项目未绑定 index 文件, 或文件不可读。</div>}
            {indexDoc?.content && <MarkdownRenderer source={indexBody} />}
          </div>
        )}
      </div>
    </div>
  )
}
