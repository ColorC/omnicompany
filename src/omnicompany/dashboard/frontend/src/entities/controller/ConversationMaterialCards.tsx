import React, { useEffect, useMemo, useState } from 'react'
import { reviewstageApi, type Material } from '../../api/reviewstageClient'
import { usePanels } from '../../stores/panelsStore'

/**
 * #3d 本对话新材料卡片: 把"本轮对话期间新出现、还需审阅"的材料做成简要卡片, 贴在对话末尾。
 * 卡片含: 路径 + 内容开头(对 md/html 取最前面真实显示文字)。点卡片快速跳到审阅台对应材料。
 *
 * "属于本对话"的判定(2026-06-04 修正):
 *   不能只看时间 —— 那样会把跟本对话无关的子代理(别的总控派的 / 后台跑的)产出也算进来。
 *   系统里没有"子代理→父总控"的持久链接, 唯一可靠的归属键是 active_plan:
 *   总控派子代理时把 plan 带下去, 子代理/总控交的材料 source_plan_id 都是这个 plan。
 *   所以判定 = source_plan_id === 本总控 activePlan ∩ created_at >= 会话 startedAt ∩ status=pending。
 *   没有 activePlan 就无法可靠归属 → 不显示(宁缺毋滥), 材料仍可在审阅台看到。
 *   另排除用户自己的圈选/快照(source_plan_id=cockpit/user-capture)。
 */
interface Props {
  sessionStartedAt?: number
  activePlan?: string | null
}

/** 取"最前面真实显示文字": 去 markdown/html 标记, 压空白, 截断。 */
function contentPreview(m: Material, limit = 140): string {
  const raw = m.inline_content || ''
  if (!raw.trim()) return ''
  let text = raw
  if (m.kind === 'html') {
    text = text.replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<[^>]+>/g, ' ')
  } else if (m.kind === 'markdown') {
    text = text
      .replace(/```[\s\S]*?```/g, ' ')
      .replace(/^#{1,6}\s+/gm, '')
      .replace(/[*_`>#-]+/g, ' ')
      .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
  } else if (m.kind === 'key_question') {
    try {
      const parsed = JSON.parse(raw)
      text = String(parsed.question || parsed.title || raw)
    } catch { /* 保持原文 */ }
  }
  text = text.replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim()
  return text.length > limit ? text.slice(0, limit) + '…' : text
}

function pathLabel(m: Material): string {
  if (m.file_relpath) return m.file_relpath
  return `内联 ${m.kind}`
}

const TIER_TONE: Record<string, string> = {
  mandatory: 'text-red-400 border-red-900/60',
  important: 'text-amber-300 border-amber-900/60',
  processual: 'text-sky-300 border-sky-900/60',
  ignored: 'text-gray-500 border-gray-700',
}

export default function ConversationMaterialCards({ sessionStartedAt, activePlan }: Props) {
  const [materials, setMaterials] = useState<Material[]>([])
  const openTab = usePanels((s) => s.openTab)

  const reload = useMemo(() => () => {
    reviewstageApi.list({ status: 'pending' })
      .then((r) => setMaterials(r.items || []))
      .catch(() => { /* 静默: 没有审阅台也不该挡对话 */ })
  }, [])

  useEffect(() => {
    reload()
    // 实时: 审阅台有新材料/状态变更时刷新这块。
    const close = reviewstageApi.openStream((e) => {
      if (e.event_type === 'snapshot') { setMaterials((e.items || []).filter((m) => m.status === 'pending')); return }
      if (e.event_type === 'ping') return
      reload()
    })
    return () => { try { close() } catch { /* */ } }
  }, [reload])

  const items = useMemo(() => {
    // 没有当前任务(plan)就无法可靠归属到"本对话" → 不显示, 避免把无关子代理产出拉进来。
    if (!activePlan) return []
    const start = sessionStartedAt && sessionStartedAt > 0 ? sessionStartedAt : 0
    return materials
      .filter((m) => m.status === 'pending')
      .filter((m) => m.source_plan_id === activePlan)
      .filter((m) => {
        if (!start) return true
        const t = m.created_at ? new Date(m.created_at).getTime() / 1000 : 0
        return t >= start - 2
      })
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
  }, [materials, sessionStartedAt, activePlan])

  if (items.length === 0) return null

  return (
    <div className="px-3 pt-2 sm:px-1" data-testid="conversation-material-cards">
      <div className="mb-1.5 flex items-center gap-2 text-[14px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
        <span>本对话新材料</span>
        <span className="rounded-full bg-gray-200 px-1.5 text-[14px] text-gray-600 dark:bg-gray-700 dark:text-gray-300">{items.length}</span>
      </div>
      <div className="space-y-1.5">
        {items.map((m) => {
          const preview = contentPreview(m)
          return (
            <button
              key={m.id}
              type="button"
              data-testid="conversation-material-card"
              onClick={() => openTab({ type: 'review_queue', id: 'main' }, '审阅队列', m.id)}
              className={`block w-full rounded-md border bg-gray-50 px-3 py-2 text-left transition-colors hover:bg-gray-100 dark:bg-gray-800/50 dark:hover:bg-gray-800 ${TIER_TONE[m.tier] || 'border-gray-300 dark:border-gray-700'}`}
            >
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{m.title || m.id}</span>
                <span className="ml-auto shrink-0 text-[14px] uppercase tracking-wide opacity-70">{m.tier}</span>
              </div>
              <div className="mt-0.5 truncate font-mono text-[14px] text-gray-500 dark:text-gray-400" title={pathLabel(m)}>{pathLabel(m)}</div>
              {preview && <div className="mt-1 line-clamp-2 text-[14px] text-gray-600 dark:text-gray-300">{preview}</div>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
