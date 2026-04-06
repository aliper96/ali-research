'use client'

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Network, ZoomIn, ZoomOut, Maximize2, Info } from 'lucide-react'
import { getGraph } from '@/lib/api'
import type { GraphData, GraphNode } from '@/lib/types'

const COMMUNITY_COLORS = [
  '#6366f1', '#8b5cf6', '#06b6d4', '#10b981',
  '#f59e0b', '#ef4444', '#ec4899', '#14b8a6',
]
const communityColor = (id: number) => COMMUNITY_COLORS[id % COMMUNITY_COLORS.length]

interface Props {
  sessionId: string
  fallbackNodes?: Array<{ id: string; title: string; relevance_score: number; year?: number | null; citation_count: number; url?: string }>
  fallbackLinks?: Array<{ source: string; target: string }>
}

export default function CitationNetwork({ sessionId, fallbackNodes = [], fallbackLinks = [] }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<any>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 })
  const [ForceGraph, setForceGraph] = useState<any>(null)

  useEffect(() => {
    import('react-force-graph-2d').then((mod) => setForceGraph(() => mod.default))
  }, [])

  const { data: graphData } = useQuery<GraphData>({
    queryKey: ['graph', sessionId],
    queryFn: () => getGraph(sessionId),
    retry: 1,
    staleTime: Infinity,
  })

  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        setDimensions({ width: e.contentRect.width, height: Math.max(e.contentRect.height, 420) })
      }
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  const fgData = useMemo(() => {
    if (graphData?.nodes?.length) {
      return {
        nodes: graphData.nodes.map((n) => ({
          ...n,
          val: 4 + (n.pagerank_norm ?? n.relevance_score ?? 0) * 14,
          color: communityColor(n.community_id ?? 0),
        })),
        links: graphData.edges.map((e) => ({ source: e.source, target: e.target, type: e.type })),
      }
    }
    return {
      nodes: fallbackNodes.map((n, i) => ({
        ...n, val: 4 + n.relevance_score * 14, color: communityColor(i),
        pagerank_norm: n.relevance_score, community_id: 0, betweenness: 0, pagerank: 0,
      })),
      links: fallbackLinks.map((l) => ({ ...l, type: 'CITES' })),
    }
  }, [graphData, fallbackNodes, fallbackLinks])

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node as GraphNode)
    graphRef.current?.centerAt(node.x, node.y, 600)
    graphRef.current?.zoom(2.5, 600)
  }, [])

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const r = (node.val ?? 6) / 2
    const isSelected = selectedNode?.id === node.id
    if (isSelected) { ctx.shadowColor = node.color; ctx.shadowBlur = 20 }
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fillStyle = node.color
    ctx.fill()
    ctx.strokeStyle = isSelected ? '#fff' : 'rgba(255,255,255,0.12)'
    ctx.lineWidth = isSelected ? 2 : 0.5
    ctx.stroke()
    ctx.shadowBlur = 0
    if (globalScale >= 1.4 || isSelected) {
      const label = (node.title ?? '').length > 38 ? node.title.slice(0, 35) + '…' : node.title
      const fs = Math.max(10 / globalScale, 3)
      ctx.textAlign = 'center'
      // Title
      ctx.font = `${fs}px Inter,sans-serif`
      ctx.fillStyle = 'rgba(248,250,252,0.85)'
      ctx.fillText(label, node.x, node.y + r + fs + 2)
      // Year — smaller, muted
      if (node.year) {
        ctx.font = `${fs * 0.85}px Inter,sans-serif`
        ctx.fillStyle = 'rgba(148,163,184,0.75)'
        ctx.fillText(String(node.year), node.x, node.y + r + fs * 2 + 4)
      }
    }
  }, [selectedNode])

  const linkColor = useCallback((l: any) => l.type === 'CITES' ? 'rgba(99,102,241,0.45)' : 'rgba(100,116,139,0.2)', [])
  const linkWidth = useCallback((l: any) => l.type === 'CITES' ? 1.5 : 0.8, [])

  const communities = graphData?.communities ?? 0

  return (
    <div className="flex flex-col gap-4">
      {/* Stats bar */}
      <div className="flex flex-wrap items-center gap-5 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <Network className="h-3.5 w-3.5 text-indigo-400" />
          <span className="text-slate-300 font-medium">{fgData.nodes.length}</span> papers
          &nbsp;·&nbsp;
          <span className="text-slate-300 font-medium">{fgData.links.length}</span> connections
        </span>
        {communities > 0 && (
          <span className="flex items-center gap-1.5">
            {communities} communities
            <span className="flex gap-1">
              {Array.from({ length: Math.min(communities, 6) }, (_, i) => (
                <span key={i} className="h-2 w-2 rounded-full" style={{ background: communityColor(i) }} />
              ))}
            </span>
          </span>
        )}
        {graphData?.memgraph
          ? <span className="rounded-full border border-indigo-800/50 bg-indigo-900/20 px-2 py-0.5 text-indigo-300">Memgraph · PageRank + Louvain</span>
          : <span className="text-slate-600">Memgraph offline — basic layout</span>
        }
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
      <div ref={containerRef} className="relative overflow-hidden rounded-lg border border-slate-800 bg-[#030712]" style={{ height: 500 }}>
        {ForceGraph && fgData.nodes.length > 0 ? (
          <ForceGraph
            ref={graphRef}
            width={dimensions.width}
            height={dimensions.height}
            graphData={fgData}
            nodeCanvasObject={nodeCanvasObject}
            nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
              ctx.fillStyle = color
              ctx.beginPath()
              ctx.arc(node.x, node.y, (node.val ?? 6) / 2 + 5, 0, 2 * Math.PI)
              ctx.fill()
            }}
            linkColor={linkColor}
            linkWidth={linkWidth}
            linkDirectionalArrowLength={(l: any) => l.type === 'CITES' ? 4 : 0}
            linkDirectionalArrowRelPos={1}
            linkDirectionalParticles={(l: any) => l.type === 'CITES' ? 2 : 0}
            linkDirectionalParticleWidth={1.5}
            linkDirectionalParticleColor={() => 'rgba(99,102,241,0.8)'}
            onNodeClick={handleNodeClick}
            onBackgroundClick={() => setSelectedNode(null)}
            backgroundColor="#030712"
            cooldownTicks={150}
            onEngineStop={() => graphRef.current?.zoomToFit(400, 40)}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-slate-600 text-sm">
            {fgData.nodes.length === 0 ? 'No papers to display' : 'Loading graph engine…'}
          </div>
        )}
      </div>

      {/* Selected node info */}
      {selectedNode && (
        <div className="rounded-lg border border-indigo-800/40 bg-indigo-950/30 p-4 text-sm space-y-2">
          <div className="flex items-start gap-2">
            <Info className="h-4 w-4 text-indigo-400 mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-slate-100 leading-snug">{selectedNode.title}</p>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
                {selectedNode.year && <span>Year: <span className="text-slate-300">{selectedNode.year}</span></span>}
                <span>Citations: <span className="text-slate-300">{selectedNode.citation_count ?? 0}</span></span>
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
      <div className="flex flex-wrap gap-5 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-8 rounded" style={{ background: 'rgba(99,102,241,0.7)' }} /> CITES (directed)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-8 rounded" style={{ background: 'rgba(100,116,139,0.4)' }} /> RELATED_TO
        </span>
        <span>Node size = PageRank · Color = Community (Louvain)</span>
      </div>
    </div>
  )
}
