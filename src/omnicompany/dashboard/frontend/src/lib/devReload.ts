// 免重启更新 — 网页层自刷新。每 3s 轮询 /api/dev/versions, ui token 变了就 location.reload()。
// 这让"改完前端 → 重载整个 VSCode"变成"改完前端 → iframe 自己刷新"(VSCode/会话全程不受影响)。
// 后端实现见 dashboard/controlplane/dev_reload.py; 触发走 `omni dashboard ui-update` / `ui-reload`。
//
// 注意:
// - vite dev (5173, HMR 已覆盖) 不轮询, 只在 build 产物模式 (后端 8210 直出) 下生效。
// - 后端临时不可达 (重启中) 时静默等待, 起来后 token 若变了再刷 — 兼顾"后端重启→页面自动重挂"。
// - 首次成功拉到的 token 作为基线; 页面加载与首拉之间完成的构建会漏掉一拍, 窗口 <3s, 可接受。

const POLL_MS = 3000

let lastToken: string | null = null
let started = false

export function startDevReloadWatch(): void {
  if (started) return
  started = true
  if (import.meta.env.DEV) return

  const tick = async () => {
    try {
      const res = await fetch('/api/dev/versions', { cache: 'no-store' })
      if (!res.ok) return
      const data: { ui?: string } = await res.json()
      if (!data.ui) return
      if (lastToken === null) {
        lastToken = data.ui
      } else if (data.ui !== lastToken) {
        window.location.reload()
      }
    } catch {
      // 后端重启中 — 保持基线, 等它回来
    }
  }

  void tick()
  window.setInterval(tick, POLL_MS)
}
