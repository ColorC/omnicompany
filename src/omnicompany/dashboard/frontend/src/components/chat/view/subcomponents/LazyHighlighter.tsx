// 被 chat/Markdown.tsx 用 React.lazy 动态引入。完整版 Prism(注册全部语言)体积很大(syntax-highlighter
// chunk ~617KB / gz 222KB), 这里拆出后, 只有真正渲染到一个代码块时才下载, 不再常驻总控聊天首屏。
import React from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

const LazyHighlighter: React.FC<{
  language: string
  value: string
  customStyle?: React.CSSProperties
  codeTagProps?: { style?: React.CSSProperties }
}> = ({ language, value, customStyle, codeTagProps }) => (
  <SyntaxHighlighter language={language} style={oneDark} customStyle={customStyle} codeTagProps={codeTagProps}>
    {value}
  </SyntaxHighlighter>
)

export default LazyHighlighter
