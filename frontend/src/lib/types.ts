export type LogLevel = 'info' | 'success' | 'warning' | 'error'
export type Depth = 'quick' | 'standard' | 'deep'
export type SessionStatus = 'running' | 'completed' | 'error'
export type Difficulty = 'easy' | 'medium' | 'hard'

export interface LogEntry {
  timestamp: string
  message: string
  level: LogLevel
}

export interface Progress {
  percentage: number
  logs: LogEntry[]
}

export interface Paper {
  id: string
  title: string
  authors: string[]
  year: number | null
  abstract: string
  url: string
  arxiv_id: string | null
  doi: string | null
  relevance_score: number
  relevance_reason: string
  citation_count: number
  tags: string[]
}

export interface CitationLink {
  source: string
  target: string
}

export interface RoadmapStep {
  step: string
  description: string
  difficulty: Difficulty
}

export interface ResearchResult {
  summary: string
  papers: Paper[]
  citation_links: CitationLink[]
  gap_analysis: string[]
  implementation_roadmap: RoadmapStep[]
  key_concepts: string[]
}

export interface ResearchSession {
  session_id: string
  status: SessionStatus
  input: string
  created_at: string
  progress: Progress
  result: ResearchResult | null
}

export interface SSEProgressEvent {
  type: 'log'
  log: LogEntry
  percentage: number
}

export interface SSECompleteEvent {
  type: 'complete'
}

export interface SSEErrorEvent {
  type: 'error'
  message: string
}

export type SSEEvent = SSEProgressEvent | SSECompleteEvent | SSEErrorEvent

// Knowledge graph (Memgraph)
export interface GraphNode {
  id: string
  title: string
  year?: number | null
  citation_count?: number
  relevance_score?: number
  url?: string
  arxiv_id?: string
  // Graph algorithm outputs
  pagerank?: number
  pagerank_norm?: number
  community_id?: number
  betweenness?: number
}

export interface GraphEdge {
  source: string
  target: string
  type: 'CITES' | 'RELATED_TO' | string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  communities: number
  memgraph: boolean
}
