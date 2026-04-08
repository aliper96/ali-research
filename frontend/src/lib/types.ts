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

export type PaperSource = 'arxiv' | 'semantic_scholar' | 'web' | 'crossref'
export type ReadStatus = 'full_text' | 'abstract_only' | 'inferred'

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
  // Provenance fields
  source: PaperSource | null
  read_status: ReadStatus | null
  venue: string | null
  url_verified: boolean | null
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

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export type AuditClaimStatus = 'verified' | 'partially_verified' | 'unverified' | 'contradicted'
export type AuditVerdict = 'matches' | 'partial_match' | 'mismatch' | 'no_repo_found'

export interface AuditClaim {
  claim: string
  status: AuditClaimStatus
  evidence: string
  evidence_url: string
}

export interface AuditResult {
  paper_title: string
  paper_url: string
  repo_url: string
  repo_found: boolean
  claims: AuditClaim[]
  verdict: AuditVerdict
  confidence: number
  audit_notes: string
}

export interface AuditSession {
  session_id: string
  status: SessionStatus
  input: string
  created_at: string
  progress: Progress
  result: AuditResult | null
}

// ---------------------------------------------------------------------------
// Deep Research (multi-agent)
// ---------------------------------------------------------------------------

export interface SubResearchResult {
  subtopic: string
  researcher_id: number
  status: 'pending' | 'running' | 'done' | 'error'
  papers: Paper[]
  key_findings: string
  citation_links: CitationLink[]
  error: string
}

export interface VerifiedClaim {
  claim: string
  supported_by: string[]   // paper IDs
  confidence: number
  verdict: 'supported' | 'partial' | 'unsupported'
}

export interface VerificationReport {
  verified_claims: VerifiedClaim[]
  unsupported_sentences: string[]
  overall_confidence: number
}

export interface DeepResearchResult {
  subtopics: string[]
  researchers: SubResearchResult[]
  synthesis: ResearchResult | null
  verification: VerificationReport | null
}

export interface DeepResearchSession {
  session_id: string
  status: SessionStatus
  input: string
  depth: string
  created_at: string
  progress: Progress
  result: DeepResearchResult | null
}

// ---------------------------------------------------------------------------
// AutoResearch (iterative loop)
// ---------------------------------------------------------------------------

export interface AutoResearchSession {
  session_id: string
  status: SessionStatus
  input: string
  created_at: string
  progress: Progress
  result: ResearchResult | null
}

// ---------------------------------------------------------------------------
// Literature Review
// ---------------------------------------------------------------------------

export interface LitSession {
  session_id: string
  status: SessionStatus
  input: string
  created_at: string
  progress: Progress
  result: ResearchResult | null
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------

export interface CompareResult {
  title: string
  items: string[]
  dimensions: string[]
  matrix: Record<string, Record<string, string>>
  summary: string
  recommendation: string
}

// ---------------------------------------------------------------------------
// Draft
// ---------------------------------------------------------------------------

export type DraftFormat = 'brief' | 'paper' | 'blog'

export interface DraftResult {
  title: string
  format: DraftFormat
  content: string
  word_count: number
}

// ---------------------------------------------------------------------------
// Outputs / Artifacts
// ---------------------------------------------------------------------------

export interface ArtifactFile {
  filename: string
  size_bytes: number
  modified_at: string
}

export interface SessionArtifacts {
  session_id: string
  agent_type: string
  files: ArtifactFile[]
  topic: string | null
  created_at: string | null
}

// ---------------------------------------------------------------------------
// Knowledge search
// ---------------------------------------------------------------------------

export interface KnowledgePaper {
  arxiv_id: string | null
  title: string
  authors: string[]
  year: number | null
  abstract: string
  url: string
  citation_count: number
  tags: string[]
  session_ids: string[]
  last_seen: string
}

export interface KnowledgeStats {
  total_papers: number
  total_sessions: number
  top_tags: Array<{ tag: string; count: number }>
  recent_papers: KnowledgePaper[]
}

// ---------------------------------------------------------------------------
// Docs (PDF / document Q&A)
// ---------------------------------------------------------------------------

export interface DocRecord {
  doc_id: string
  title: string
  filename: string
  page_count: number
  chunk_count: number
  created_at: string
  size_bytes: number
}

export interface DocChunkRef {
  doc_id: string
  doc_title: string
  chunk_index: number
  content: string
}

export interface DocsQAResult {
  question: string
  answer: string
  sources: DocChunkRef[]
}

// ---------------------------------------------------------------------------
// Web Search (Perplexity-like)
// ---------------------------------------------------------------------------

export interface WebSource {
  title: string
  url: string
  snippet: string
  content: string
  published_date: string | null
  domain: string
}

export interface WebSearchResult {
  answer: string
  sources: WebSource[]
  follow_up_questions: string[]
  queries_used: string[]
}

export interface WebSearchSession {
  session_id: string
  status: SessionStatus
  input: string
  created_at: string
  progress: Progress
  result: WebSearchResult | null
}

export type WebSearchRecency = 'any' | 'day' | 'week' | 'month'

// ---------------------------------------------------------------------------
// Knowledge graph (Memgraph)
// ---------------------------------------------------------------------------
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
