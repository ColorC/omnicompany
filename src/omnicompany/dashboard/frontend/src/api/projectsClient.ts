// 项目工作板 API 客户端 — 首页项目卡片 + 项目详情页的数据源。
// 后端: dashboard 进程 controlplane/projects.py (/api/projects*), 唯一权威模型在
// core/projects_registry (data/registry/projects.json) + 各项目自己的 PROJECT_INDEX.md
// (quick_actions/links 从它的 frontmatter 浮出)。

export interface ProjectQuickAction {
  label: string
  skill?: string | null
  where?: string
  desc?: string
}

export interface ProjectLink {
  label: string
  url: string
}

export interface ProjectItem {
  id: string
  name: string
  group: string
  tags?: string[]
  desc?: string
  roots?: string[]
  index_path?: string
  bg?: string
  /** 卡片小图标: lucide 图标名(kebab-case, 如 shield-check) */
  icon?: string
  plan_categories?: string[]
  links?: ProjectLink[]
  pinned?: boolean
  // enrich 计算字段
  last_active?: string | null
  /** 近 7 天逐日活跃(旧→新, 末位=今天) */
  activity_7d?: boolean[]
  plan_count?: number
  index_ok?: boolean | null
  index_error?: string | null
  index_latest?: string[]
  quick_actions?: ProjectQuickAction[]
  updated_at?: string
}

export interface ProjectsBoard {
  projects: ProjectItem[]
  groups_order: string[]
  group_labels: Record<string, string>
  updated_at?: string
}

export interface ProjectIndexDoc {
  ok: boolean
  error?: string
  path?: string
  content?: string
  data?: Record<string, unknown>
  mtime?: string
}

async function jsonOrThrow<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json() as Promise<T>
}

export interface ProjectPlanItem {
  id: string
  topic?: string
  /** 治理部门(plan_steward)给的中文标题 */
  title_zh?: string | null
  date?: string
  category?: string
  archived?: boolean
}

export interface ProjectPlans {
  project: string
  items: ProjectPlanItem[]
  /** 本项目全部计划 id — 前端用它过滤对话(active_plan)/审阅(source_plan_id) */
  plan_ids: string[]
}

export interface ProjectFindingItem {
  title: string
  count: number
  projects?: string[]
  examples?: string[]
  quick_action_hint?: string | null
  already_in_memory?: boolean | null
}

export interface ProjectFindings {
  project: string
  generated_at?: string
  days?: number
  needs: ProjectFindingItem[]
  corrections: ProjectFindingItem[]
}

export const projectsApi = {
  /** fresh=true = 用户主动刷新, 穿透服务端 index 解析缓存 */
  list: (fresh = false): Promise<ProjectsBoard> =>
    fetch(fresh ? '/api/projects?fresh=1' : '/api/projects').then((r) => jsonOrThrow<ProjectsBoard>(r)),
  index: (id: string): Promise<ProjectIndexDoc> =>
    fetch(`/api/projects/${encodeURIComponent(id)}/index`).then((r) => jsonOrThrow<ProjectIndexDoc>(r)),
  /** 项目关联计划 — 服务端归属(治理覆盖表优先), 前端不再自带匹配逻辑 */
  plans: (id: string): Promise<ProjectPlans> =>
    fetch(`/api/projects/${encodeURIComponent(id)}/plans`).then((r) => jsonOrThrow<ProjectPlans>(r)),
  /** 本项目的工作历史证据(重复需求/重复指正, 治理部门 work_history 分配) */
  findings: (id: string): Promise<ProjectFindings> =>
    fetch(`/api/projects/${encodeURIComponent(id)}/findings`).then((r) => jsonOrThrow<ProjectFindings>(r)),
}

/** 一键在某项目下新建计划书(纯文本草稿; formalize=true 先用 AI 整理成规范计划书)。 */
export async function createPlan(body: {
  topic: string; project_id?: string; category?: string; title?: string;
  content?: string; work_type?: string; formalize?: boolean
}): Promise<{ ok: boolean; plan_id: string; abs_path: string; category: string; formalized: boolean }> {
  const r = await fetch('/api/plans', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  return jsonOrThrow(r)
}
