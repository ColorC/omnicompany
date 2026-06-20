// 共用 wiki 核（webworks/packages/wiki-core，经 vite alias @wiki-core 引入）的最小类型壳。
// 正本是纯 JS；这里只声明 dashboard 用到的渲染门面。
declare module '@wiki-core/render' {
  export interface WikiRenderer {
    render(markdown: string): string
  }
  export function createRenderer(options?: Record<string, unknown>): WikiRenderer
  export function stripFrontmatter(content: string): string
}
