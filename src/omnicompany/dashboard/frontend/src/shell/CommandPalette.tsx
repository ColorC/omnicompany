import React, { useEffect, useMemo, useState } from 'react'
import {
  KBarProvider, KBarPortal, KBarPositioner, KBarAnimator, KBarSearch,
  useMatches, KBarResults, useRegisterActions, type Action,
} from 'kbar'
import { registry } from '../entities/registry'
import { usePanels } from '../stores/panelsStore'
import type { Entity, EntityType } from '../entities/types'

const POSITIONER: React.CSSProperties = {
  position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
  display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
  paddingTop: 80, background: 'rgba(0,0,0,0.5)', zIndex: 9999,
}
const ANIMATOR: React.CSSProperties = {
  width: 600, maxWidth: '90vw', background: '#0d0d0d',
  border: '1px solid #2a3a4a', borderRadius: 6, overflow: 'hidden',
  boxShadow: '0 6px 32px rgba(0,0,0,.6)', fontFamily: 'Consolas, Menlo, monospace',
}
const SEARCH: React.CSSProperties = {
  width: '100%', padding: '12px 16px', background: '#0d0d0d',
  border: 'none', outline: 'none', color: '#e0e0e0', fontSize: 15,
  fontFamily: 'Consolas, Menlo, monospace',
}

function ResultRow({ active, item }: { active: boolean; item: any }) {
  return (
    <div style={{
      padding: '8px 16px', cursor: 'pointer', display: 'flex', gap: 8,
      background: active ? '#1a2a3a' : 'transparent',
      color: active ? '#90caf9' : '#bbb', fontSize: 14,
    }}>
      <span style={{ color: '#666', width: 60, flexShrink: 0 }}>{item.section || ''}</span>
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span>
      <span style={{ color: '#444', fontSize: 14 }}>{item.subtitle || ''}</span>
    </div>
  )
}

function ResultsRender() {
  const { results } = useMatches()
  return (
    <KBarResults
      items={results}
      onRender={({ item, active }) =>
        typeof item === 'string' ? (
          <div style={{ padding: '4px 16px', color: '#666', fontSize: 14, textTransform: 'uppercase' }}>{item}</div>
        ) : (
          <ResultRow active={active} item={item} />
        )
      }
    />
  )
}

function DynamicActions() {
  const openTab = usePanels((s) => s.openTab)
  const [actions, setActions] = useState<Action[]>([])

  useEffect(() => {
    let dead = false
    const types = registry.types() as EntityType[]
    Promise.all(
      types.map(async (t) => {
        const reg = registry.get(t)
        if (!reg) return [] as Entity[]
        try { return await reg.resolver.list() } catch { return [] }
      }),
    ).then((groups) => {
      if (dead) return
      const acts: Action[] = []
      groups.flat().forEach((e) => {
        const reg = registry.get(e.type)
        acts.push({
          id: `open:${e.type}:${e.id}`,
          name: e.title,
          subtitle: e.id,
          section: reg?.label || e.type,
          keywords: `${e.id} ${(e.tags || []).join(' ')}`,
          perform: () => openTab(e, e.title),
        })
      })
      setActions(acts)
    })
    return () => { dead = true }
  }, [openTab])

  return <ActionLoader actions={actions} />
}

function ActionLoader({ actions }: { actions: Action[] }) {
  useRegisterActions(actions, [actions])
  return null
}

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  return (
    <KBarProvider actions={[]} options={{ enableHistory: false }}>
      <DynamicActions />
      <KBarPortal>
        <KBarPositioner style={POSITIONER}>
          <KBarAnimator style={ANIMATOR}>
            <KBarSearch style={SEARCH} defaultPlaceholder="跳转: 输入笔记/任务/worker/trace 名..." />
            <ResultsRender />
          </KBarAnimator>
        </KBarPositioner>
      </KBarPortal>
      {children}
    </KBarProvider>
  )
}
