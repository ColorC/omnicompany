// 单区渲染(三区化)的真源: ?surface=<queue|material|comments|full> 决定本页只渲染哪个语义区。
// full / 缺省 = 完整驾驶舱(浏览器、主 omnichat webview); 其余 = 把该区单独挂进 VSCode 原生表面
// (主侧栏 queue / 编辑页签 material / 次级侧栏 comments)。同一份前端, 只是挂载位置不同, 零分叉。

export type Surface = 'full' | 'queue' | 'material' | 'comments' | 'project' | 'plan' | 'threads' | 'authored'

const REGION_SURFACES: Surface[] = ['queue', 'material', 'comments', 'project', 'plan', 'threads', 'authored']

export function readSurface(search: string = window.location.search): { surface: Surface; id: string | null } {
  const p = new URLSearchParams(search)
  const raw = (p.get('surface') || 'full') as Surface
  return {
    surface: REGION_SURFACES.includes(raw) ? raw : 'full',
    id: p.get('id'),
  }
}

/** 页面是否嵌在 VSCode webview iframe 里(有不同的父窗口)。 */
export function isInWebview(): boolean {
  try { return !!(window.parent && window.parent !== window) } catch { return true }
}

/** 给 webview 宿主(扩展)发消息 —— 外壳会把带 __omnichat 标记的消息转发给扩展 impl。
 * 既发 parent(一级 iframe)也发 top(多层嵌套), 与 copyText/openInVscode 同款冗余。 */
export function postHostMessage(msg: Record<string, unknown>): void {
  const payload = { __omnichat: true, ...msg }
  try { window.parent?.postMessage(payload, '*') } catch { /* */ }
  try { if (window.top && window.top !== window.parent) window.top.postMessage(payload, '*') } catch { /* */ }
}

/** 在 omnidashboard(完整驾驶舱)里打开某条目: 宿主开一个完整壳编辑页签并深链到该条目。
 * 这是 VSCode 主侧栏各 section 列表点条目的默认行为(条目在编辑区打开, 侧栏只管导航)。 */
export function openInOmnidashboard(openType: string, openId: string, facet?: string, title?: string): void {
  postHostMessage({ type: 'open-omnidashboard', openType, openId, facet: facet || null, title: title || openId })
}

/** 对话"在 VSCode 打开": claude_code → 唤起 Claude Code(官方插件/CLI); 其它(codex 等) → 开 PowerShell 终端跑 codex resume。 */
export function openChatInVscode(provider: string | undefined, cwd: string | undefined, sessionId?: string): void {
  const isClaude = (provider || '').includes('claude')
  postHostMessage({
    type: isClaude ? 'open-in-claude-code' : 'open-codex-terminal',
    cwd: cwd || '',
    sessionId: sessionId || '',
  })
}
