import React from 'react'
import 'dockview/dist/styles/dockview.css'
import { CommandPaletteProvider } from './CommandPalette'
import { registerAllEntities } from './registerEntities'
import CockpitShell from './CockpitShell'
// @ts-ignore — jsx 文件没 .d.ts
import { ThemeProvider } from '../contexts/ThemeContext'

registerAllEntities()

// ThemeProvider 必须包在最外层: 驾驶舱内嵌的总控/subagent 对话(CcChatPanel → ChatInterface)
// 依赖 useTheme(), 没有 provider 会直接抛错。默认深色, 与驾驶舱一致。
export default function App() {
  return (
    <ThemeProvider>
      <CommandPaletteProvider>
        <CockpitShell />
      </CommandPaletteProvider>
    </ThemeProvider>
  )
}
