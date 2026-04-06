'use client'

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Network,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Info,
  ArrowLeft,
  Globe,
  RefreshCw,
} from 'lucide-react'
import Link from 'next/link'
import { getGlobalGraph } from '@/lib/api'
import type { GraphData, GraphNode } from '@/lib/types'

const COMMUNITY_COLORS = [
  '#6366f1', '#8b5cf6', '#06b6d4', '#10b981',
  '#f59e0b', '#ef4444', '#ec4899', '#14b8a6',
  '#3b82f6', '#a855f7', '#22d3ee', '#84cc16',
]
const communityColor = (id: number) => COMMUNITY_COLORS[id % COMMUNITY_COLORS.length]

export default function GlobalNetworkPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<any>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [dimensions, setDimensions] = useState({ width: 1000, height: 700 })
  const [ForceGraph, setForceGraph] = useState<any>(null)

  useEffect(() => {
    import('react-force-graph-2d').then((mod) => setForceGraph(() => mod.default))
  }, [])

  const { data: graphData, isLoading, refetch, dataUpdatedAt } = useQuery<GraphData & { total_papers: number }>({
    queryKey: ['global-graph'],
    queryFn: getGlobalGraph,
    retry: 1,
    staleTime: 60_000,
  })

  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        setDimensions({ width: e.contentRect.width, height: Math.max(e.contentRect.height, 500) })
      }
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  const fgData = useMemo(() => {
    if (!graphData?.nodes?.length) return { nodes: [], links: [] }
    return {
      nodes: graphData.nodes.map((n) => ({
        ...n,
        // Nodes that appear in more sessions are bigger
        val: 4 + (n.pagerank_norm ?? n.relevance_score ?? 0) * 18 + ((n as any).session_count ?? 1) * 0.5,
        color: communityColor(n.community_id ?? 0),
      })),
      links: graphData.edges.map((e) => ({ source: e.source, target: e.target, type: e.type })),
    }
  }, [graphData])

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node as GraphNode)
    graphRef.current?.centerAt(node.x, node.y, 600)
    graphRef.current?.zoom(2.5, 600)
  }, [])

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const r = (node.val ?? 6) / 2
    const isSelected = selectedNode?.id === node.id
    const sessionCount = (node as any).session_count ?? 1

    // Glow for high-session nodes
    if (isSelected || sessionCount > 2) {
      ctx.shadowColor = node.color
      ctx.shadowBlur = isSelected ? 24 : Math.min(sessionCount * 4, 20)
    }
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = node.color
    ctx.fill()
    ctx.strokeStyle = isSelected ? '#fff' : sessionCount > 1 ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.08)'
    ctx.lineWidth = isSelected ? 2.5 : sessionCount > 1 ? 1.5 : 0.5
    ctx.stroke()
    ctx.shadowBlur = 0

    if (globalScale >= 1.2 || isSelected) {
      const label = (node.title ?? '').length > 40 ? node.title.slice(0, 37) + '…' : node.title
      const fs = Math.max(10 / globalScale, 3)
      ctx.textAlign = 'center'
      ctx.font = `${isSelected ? 'bold ' : ''}${fs}px Inter,sans-serif`
      ctx.fillStyle = isSelected ? 'rgba(255,255,255,0.95)' : 'rgba(248,250,252,0.80)'
      ctx.fillText(label, node.x, node.y + r + fs + 2)
      if (node.year) {
        ctx.font = `${fs * 0.82}px Inter,sans-serif`
        ctx.fillStyle = 'rgba(148,163,184,0.70)'
        ctx.fillText(String(node.year), node.x, node.y + r + fs * 2 + 3)
      }
      // Session count badge
      if (sessionCount > 1) {
        ctx.font = `bold ${fs * 0.78}px Inter,sans-serif`
        ctx.fillStyle = node.color
        ctx.fillText(`×${sessionCount}`, node.x, node.y + r + fs * 3 + 4)
      }
    }
  }, [selectedNode])

  const linkColor = useCallback((l: any) =>
    l.type === 'CITES' ? 'rgba(99,102,241,0.35)' : 'rgba(100,116,139,0.15)', [])
  const linkWidth = useCallback((l: any) => l.type === 'CITES' ? 1.2 : 0.6, [])

  const communities = graphData?.communities ?? 0
  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null

  return (
    <div className="flex min-h-screen flex-col bg-[#030712] text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-4">
          <Link
            href="/"
            className="flex items-center gap-2 text-slate-400 hover:text-slate-200 transition-colors text-sm"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </Link>

          <div className="h-5 w-px bg-slate-800" />

          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-900/50 border border-indigo-700/50">
              <Globe className="h-4 w-4 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-slate-100">Global Knowledge Network</h1>
              <p className="text-[11px] text-slate-500">Accumulated across all research sessions</p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-slate-600">Updated {lastUpdated}</span>
            )}
            <button
              onClick={() => refetch()}
              className="flex items-center gap-1.5 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 hover:border-slate-600 transition-colors"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-6 space-y-5">

        {/* Stats bar */}
        <div className="flex flex-wrap items-center gap-5 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <Network className="h-3.5 w-3.5 text-indigo-400" />
            <span className="text-slate-300 font-semibold">{fgData.nodes.length}</span> papers
            &nbsp;·&nbsp;
            <span className="text-slate-300 font-semibold">{fgData.links.length}</span> connections
          </span>
          {communities > 0 && (
            <span className="flex items-center gap-1.5">
              {communities} communities
              <span className="flex gap-1">
                {Array.from({ length: Math.min(communities, 8) }, (_, i) => (
                  <span key={i} className="h-2 w-2 rounded-full" style={{ background: communityColor(i) }} />
                ))}
              </span>
            </span>
          )}
          {graphData?.memgraph
            ? <span className="rounded-full border border-indigo-800/50 bg-indigo-900/20 px-2 py-0.5 text-indigo-300">Memgraph · PageRank + Louvain</span>
            : <span className="text-slate-600">Memgraph offline</span>
          }
          <span className="text-slate-700">
            Node size = PageRank · Brightness = appearances across sessions
          </span>
        </div>

        {/* Zoom controls */}
        <div className="flex justify-end gap-2">
          {[
            { icon: <ZoomIn className="h-3.5 w-3.5" />, fn: () => graphRef.current?.zoom(graphRef.current.zoom() * 1.4, 300) },
            { icon: <ZoomOut className="h-3.5 w-3.5" />, fn: () => graphRef.current?.zoom(graphRef.current.zoom() / 1.4, 300) },
            { icon: <Maximize2 className="h-3.5 w-3.5" />, fn: () => graphRef.current?.zoomToFit(400, 40) },
          ].map((b, i) => (
            <button key={i} onClick={b.fn}
              className="rounded border border-slate-700 bg-slate-800 p-1.5 text-slate-400 hover:text-slate-200 hover:border-slate-600 transition-colors">
              {b.icon}
            </button>
          ))}
        </div>

        {/* Canvas */}
        <div ref={containerRef} className="relative overflow-hidden rounded-xl border border-slate-800 bg-[#030712]" style={{ height: 640 }}>
          {isLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-slate-500 z-10">
              <div className="flex gap-1.5">
                {[0, 1, 2].map(i => (
                  <span key={i} className="h-2 w-2 rounded-full bg-indigo-500 animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
              <span className="text-sm">Loading global graph…</span>
            </div>
          )}
          {!isLoading && fgData.nodes.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-slate-600">
              <Globe className="h-12 w-12 opacity-20" />
              <p className="text-sm">No papers yet — run a research session first</p>
              <Link href="/" className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 underline underline-offset-2">
                Start researching →
              </Link>
            </div>
          )}
          {ForceGraph && fgData.nodes.length > 0 && (
            <ForceGraph
              ref={graphRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={fgData}
              nodeCanvasObject={nodeCanvasObject}
              nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
                ctx.fillStyle = color
                ctx.beginPath()
                ctx.arc(node.x, node.y, (node.val ?? 6) / 2 + 6, 0, 2 * Math.PI)
                ctx.fill()
              }}
              linkColor={linkColor}
              linkWidth={linkWidth}
              linkDirectionalArrowLength={(l: any) => l.type === 'CITES' ? 4 : 0}
              linkDirectionalArrowRelPos={1}
              linkDirectionalParticles={(l: any) => l.type === 'CITES' ? 2 : 0}
              linkDirectionalParticleWidth={1.5}
              linkDirectionalParticleColor={() => 'rgba(99,102,241,0.7)'}
              onNodeClick={handleNodeClick}
              onBackgroundClick={() => setSelectedNode(null)}
              backgroundColor="#030712"
              cooldownTicks={200}
              onEngineStop={() => graphRef.current?.zoomToFit(400, 40)}
            />
          )}
        </div>

        {/* Selected node info */}
        {selectedNode && (
          <div className="rounded-xl border border-indigo-800/40 bg-indigo-950/30 p-4 text-sm space-y-2">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-indigo-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-slate-100 leading-snug">{selectedNode.title}</p>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
                  {selectedNode.year && <span>Year: <span className="text-slate-300">{selectedNode.year}</span></span>}
                  <span>Citations: <span className="text-slate-300">{selectedNode.citation_count ?? 0}</span></span>
                  {(selectedNode as any).session_count > 1 && (
                    <span className="text-indigo-300 font-medium">
                      Appeared in <span className="text-indigo-200">{(selectedNode as any).session_count}</span> sessions
                    </span>
                  )}
                  {selectedNode.pagerank != null && (
                    <span>PageRank: <span className="text-slate-300">{selectedNode.pagerank.toFixed(5)}</span></span>
                  )}
                  {selectedNode.betweenness != null && selectedNode.betweenness > 0 && (
                    <span>Betweenness: <span className="text-slate-300">{selectedNode.betweenness.toFixed(3)}</span></span>
                  )}
                  {selectedNode.community_id != null && (
                    <span className="flex items-center gap-1">
                      Community:
                      <span className="h-2 w-2 rounded-full inline-block" style={{ background: communityColor(selectedNode.community_id) }} />
                      <span className="text-slate-300">{selectedNode.community_id}</span>
                    </span>
                  )}
                </div>
                {selectedNode.url && (
                  <a href={selectedNode.url} target="_blank" rel="noopener noreferrer"
                    className="mt-2 inline-block text-indigo-400 hover:text-indigo-300 underline underline-offset-2 text-xs">
                    Open paper →
                  </a>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="flex flex-wrap gap-5 text-xs text-slate-600">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-8 rounded" style={{ background: 'rgba(99,102,241,0.6)' }} /> CITES (directed)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-8 rounded" style={{ background: 'rgba(100,116,139,0.35)' }} /> RELATED_TO
          </span>
          <span>Node size = PageRank · Glow = appears in multiple sessions · ×N = session count</span>
        </div>
      </main>
    </div>
  )
}
