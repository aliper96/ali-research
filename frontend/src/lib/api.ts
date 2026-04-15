import type {
  AuditSession, CompareResult, DeepResearchSession, DraftFormat, DraftResult,
  AutoResearchSession, LitSession, Depth, GraphData, KnowledgePaper,
  KnowledgeStats, ResearchSession, SessionArtifacts, SSEEvent,
  WebSearchSession, WebSearchRecency,
  DocRecord, DocsQAResult,
} from '@/lib/types'

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`API error ${res.status}: ${text}`)
  }

  return res.json() as Promise<T>
}

export async function startResearch(
  input: string,
  depth: Depth
): Promise<{ session_id: string }> {
  return fetchJSON<{ session_id: string }>('/api/research', {
    method: 'POST',
    body: JSON.stringify({ input, depth }),
  })
}

export async function getSession(sessionId: string): Promise<ResearchSession> {
  return fetchJSON<ResearchSession>(`/api/research/${sessionId}`)
}

export async function getGraph(sessionId: string): Promise<GraphData> {
  return fetchJSON<GraphData>(`/api/research/${sessionId}/graph`)
}

export async function getGlobalGraph(): Promise<GraphData & { total_papers: number }> {
  return fetchJSON<GraphData & { total_papers: number }>('/api/graph/global')
}

export interface SessionSummary {
  session_id: string
  input: string
  status: 'running' | 'completed' | 'error'
  created_at: string
  has_result: boolean
}

export async function listSessions(limit = 20): Promise<SessionSummary[]> {
  return fetchJSON<SessionSummary[]>(`/api/sessions?limit=${limit}`)
}

// ---------------------------------------------------------------------------
// Review API
// ---------------------------------------------------------------------------

export interface ReviewerReport {
  reviewer_id: number
  persona: string
  status: 'pending' | 'running' | 'done' | 'error'
  novelty_score: number
  technical_score: number
  clarity_score: number
  contribution_score: number
  overall_score: number
  recommendation: 'accept' | 'minor_revision' | 'major_revision' | 'reject'
  strengths: string[]
  major_issues: string[]
  minor_issues: string[]
  missing_citations: string[]
  related_papers_found: string[]
  summary: string
  error?: string
}

export interface EditorReport {
  final_recommendation: 'accept' | 'minor_revision' | 'major_revision' | 'reject'
  novelty_score: number
  technical_score: number
  clarity_score: number
  contribution_score: number
  overall_score: number
  novelty_verdict: string
  publishability: string
  consensus_summary: string
  major_issues: string[]
  minor_issues: string[]
  strengths: string[]
  action_items: string[]
  reviewer_agreement: number
}

export interface ReviewSession {
  session_id: string
  status: 'running' | 'completed' | 'error'
  paper_title: string
  paper_abstract: string
  filename: string
  num_reviewers: number
  reviewer_reports: ReviewerReport[]
  editor_report: EditorReport | null
  created_at: string
  progress: { percentage: number; logs: Array<{ timestamp: string; message: string; level: string }> }
}

export async function startReview(
  paperFile: File,
  numReviewers: number,
  bibFile?: File,
): Promise<{ session_id: string; paper_title: string }> {
  const form = new FormData()
  form.append('paper_file', paperFile)
  form.append('num_reviewers', String(numReviewers))
  if (bibFile) form.append('bib_file', bibFile)

  const res = await fetch(`${API_BASE_URL}/api/review`, { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json()
}

export async function getReviewSession(sessionId: string): Promise<ReviewSession> {
  return fetchJSON<ReviewSession>(`/api/review/${sessionId}`)
}

export function streamReview(
  sessionId: string,
  onEvent: (event: SSEEvent & { reviewer_id?: number; status?: string; recommendation?: string; overall_score?: number }) => void,
): () => void {
  const url = `${API_BASE_URL}/api/review/${sessionId}/stream`
  const es = new EventSource(url)

  es.addEventListener('progress', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data as string)) } catch {}
  })
  es.addEventListener('complete', (e: MessageEvent) => {
    try { onEvent({ ...JSON.parse(e.data as string), type: 'complete' }) } catch { onEvent({ type: 'complete' }) }
    es.close()
  })
  es.onerror = () => { onEvent({ type: 'error', message: 'Stream error' }); es.close() }
  return () => es.close()
}

// ---------------------------------------------------------------------------
// Audit API
// ---------------------------------------------------------------------------

export async function startAudit(input: string): Promise<{ session_id: string }> {
  return fetchJSON<{ session_id: string }>('/api/audit', {
    method: 'POST',
    body: JSON.stringify({ input }),
  })
}

export async function getAuditSession(sessionId: string): Promise<AuditSession> {
  return fetchJSON<AuditSession>(`/api/audit/${sessionId}`)
}

export interface AuditSummary {
  session_id: string
  input: string
  status: 'running' | 'completed' | 'error'
  created_at: string
  verdict: string | null
  paper_title: string | null
}

export async function listAudits(limit = 20): Promise<AuditSummary[]> {
  return fetchJSON<AuditSummary[]>(`/api/audits?limit=${limit}`)
}

// ---------------------------------------------------------------------------
// Watch API
// ---------------------------------------------------------------------------

export interface Watch {
  watch_id: string
  query: string
  depth: string
  schedule_hours: number
  active: boolean
  created_at: string
  last_run_at: string | null
  next_run_at: string | null
  last_result: {
    session_id: string
    paper_count: number
    top_papers: string[]
    summary: string
  } | null
}

export async function createWatch(query: string, depth: string, schedule_hours: number): Promise<Watch> {
  return fetchJSON<Watch>('/api/watch', {
    method: 'POST',
    body: JSON.stringify({ query, depth, schedule_hours }),
  })
}

export async function listWatches(): Promise<Watch[]> {
  return fetchJSON<Watch[]>('/api/watches')
}

export async function deleteWatch(watchId: string): Promise<void> {
  await fetchJSON(`/api/watch/${watchId}`, { method: 'DELETE' })
}

export async function runWatchNow(watchId: string): Promise<{ status: string }> {
  return fetchJSON(`/api/watch/${watchId}/run`, { method: 'POST' })
}

export function streamAudit(sessionId: string, onEvent: (event: SSEEvent) => void): () => void {
  const es = new EventSource(`${API_BASE_URL}/api/audit/${sessionId}/stream`)
  es.addEventListener('progress', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data as string)) } catch {}
  })
  es.addEventListener('complete', (e: MessageEvent) => {
    try { onEvent({ ...JSON.parse(e.data as string), type: 'complete' }) } catch { onEvent({ type: 'complete' }) }
    es.close()
  })
  es.onerror = () => { onEvent({ type: 'error', message: 'Stream error' }); es.close() }
  return () => es.close()
}

// ---------------------------------------------------------------------------
// Deep Research API
// ---------------------------------------------------------------------------

export async function startDeepResearch(
  input: string, depth: Depth, num_researchers: number
): Promise<{ session_id: string }> {
  return fetchJSON('/api/deepresearch', {
    method: 'POST',
    body: JSON.stringify({ input, depth, num_researchers }),
  })
}

export async function getDeepSession(sessionId: string): Promise<DeepResearchSession> {
  return fetchJSON<DeepResearchSession>(`/api/deepresearch/${sessionId}`)
}

export async function listDeepSessions(limit = 20): Promise<SessionSummary[]> {
  return fetchJSON<SessionSummary[]>(`/api/deepresearches?limit=${limit}`)
}

export function streamDeepSession(sessionId: string, onEvent: (e: SSEEvent) => void): () => void {
  return _streamGeneric(`/api/deepresearch/${sessionId}/stream`, onEvent)
}

// ---------------------------------------------------------------------------
// AutoResearch API
// ---------------------------------------------------------------------------

export async function startAutoResearch(
  input: string, depth: Depth, max_iterations: number
): Promise<{ session_id: string }> {
  return fetchJSON('/api/autoresearch', {
    method: 'POST',
    body: JSON.stringify({ input, depth, max_iterations }),
  })
}

export async function getAutoSession(sessionId: string): Promise<AutoResearchSession> {
  return fetchJSON<AutoResearchSession>(`/api/autoresearch/${sessionId}`)
}

export async function listAutoSessions(limit = 20): Promise<SessionSummary[]> {
  return fetchJSON<SessionSummary[]>(`/api/autoresearches?limit=${limit}`)
}

export function streamAutoSession(sessionId: string, onEvent: (e: SSEEvent) => void): () => void {
  return _streamGeneric(`/api/autoresearch/${sessionId}/stream`, onEvent)
}

// ---------------------------------------------------------------------------
// Literature Review API
// ---------------------------------------------------------------------------

export async function startLitReview(input: string, depth: Depth): Promise<{ session_id: string }> {
  return fetchJSON('/api/lit', {
    method: 'POST',
    body: JSON.stringify({ input, depth }),
  })
}

export async function getLitSession(sessionId: string): Promise<LitSession> {
  return fetchJSON<LitSession>(`/api/lit/${sessionId}`)
}

export async function listLitSessions(limit = 20): Promise<SessionSummary[]> {
  return fetchJSON<SessionSummary[]>(`/api/lits?limit=${limit}`)
}

export function streamLitSession(sessionId: string, onEvent: (e: SSEEvent) => void): () => void {
  return _streamGeneric(`/api/lit/${sessionId}/stream`, onEvent)
}

// ---------------------------------------------------------------------------
// Compare API
// ---------------------------------------------------------------------------

export async function compareItems(items: string[], context?: string): Promise<CompareResult> {
  return fetchJSON<CompareResult>('/api/compare', {
    method: 'POST',
    body: JSON.stringify({ items, context: context ?? '' }),
  })
}

// ---------------------------------------------------------------------------
// Draft API
// ---------------------------------------------------------------------------

export async function createDraft(
  session_id: string, session_type: string, format: DraftFormat, title?: string
): Promise<DraftResult> {
  return fetchJSON<DraftResult>('/api/draft', {
    method: 'POST',
    body: JSON.stringify({ session_id, session_type, format, title: title ?? '' }),
  })
}

// ---------------------------------------------------------------------------
// Outputs / Artifacts API
// ---------------------------------------------------------------------------

export async function listAllOutputs(): Promise<SessionArtifacts[]> {
  return fetchJSON<SessionArtifacts[]>('/api/outputs')
}

export async function listSessionOutputs(sessionId: string): Promise<SessionArtifacts> {
  return fetchJSON<SessionArtifacts>(`/api/outputs/${sessionId}`)
}

export function getArtifactDownloadUrl(sessionId: string, filename: string): string {
  return `${API_BASE_URL}/api/outputs/${sessionId}/${filename}`
}

// ---------------------------------------------------------------------------
// Knowledge search API
// ---------------------------------------------------------------------------

export async function searchKnowledge(query: string, limit = 20): Promise<KnowledgePaper[]> {
  return fetchJSON<KnowledgePaper[]>(`/api/knowledge/search?q=${encodeURIComponent(query)}&limit=${limit}`)
}

export async function getKnowledgeStats(): Promise<KnowledgeStats> {
  return fetchJSON<KnowledgeStats>('/api/knowledge/stats')
}

// ---------------------------------------------------------------------------
// Docs API (PDF / document Q&A)
// ---------------------------------------------------------------------------

export async function uploadDocument(file: File): Promise<DocRecord> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE_URL}/api/docs/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`Upload error ${res.status}: ${text}`)
  }
  return res.json()
}

export async function listDocuments(): Promise<DocRecord[]> {
  return fetchJSON<DocRecord[]>('/api/docs')
}

export async function deleteDocument(docId: string): Promise<void> {
  await fetchJSON(`/api/docs/${docId}`, { method: 'DELETE' })
}

export async function askDocuments(question: string, topK = 5): Promise<DocsQAResult> {
  return fetchJSON<DocsQAResult>('/api/docs/ask', {
    method: 'POST',
    body: JSON.stringify({ question, top_k: topK }),
  })
}

// ---------------------------------------------------------------------------
// Web Search API (Perplexity-like)
// ---------------------------------------------------------------------------

export async function startWebSearch(
  input: string,
  recency: WebSearchRecency = 'any',
): Promise<{ session_id: string }> {
  return fetchJSON('/api/websearch', {
    method: 'POST',
    body: JSON.stringify({ input, recency }),
  })
}

export async function getWebSearchSession(sessionId: string): Promise<WebSearchSession> {
  return fetchJSON<WebSearchSession>(`/api/websearch/${sessionId}`)
}

export async function listWebSearchSessions(limit = 20): Promise<SessionSummary[]> {
  return fetchJSON<SessionSummary[]>(`/api/websearches?limit=${limit}`)
}

export function streamWebSearchSession(sessionId: string, onEvent: (e: SSEEvent) => void): () => void {
  return _streamGeneric(`/api/websearch/${sessionId}/stream`, onEvent)
}

// ---------------------------------------------------------------------------
// LaTeX Coach API
// ---------------------------------------------------------------------------

export interface TextSuggestion {
  type: 'rewrite' | 'add' | 'remove' | 'expand'
  file: string
  start_line: number
  end_line: number
  target_text: string
  replacement: string
  reason: string
}

export interface SectionAnalysis {
  title: string
  file: string
  start_line: number
  score_clarity: number
  score_rigor: number
  score_completeness: number
  issues: string[]
  suggestions: TextSuggestion[]
}

export interface LatexStructure {
  tables: Array<{ file: string; caption: string; label: string }>
  figures: Array<{ file: string; caption: string; label: string }>
  citations: string[]
  labels: string[]
  undefined_refs: string[]
}

export interface SuggestedTable {
  title: string
  rationale: string
  latex: string
}

export interface SuggestedFigure {
  title: string
  description: string
  placement: string
}

export interface GlobalAssessment {
  novelty: number
  clarity: number
  experimental_rigor: number
  submission_readiness: number
  overall: number
  top_priorities: string[]
  submission_checklist: string[]
  verdict: string
}

export interface CompilationResult {
  success: boolean
  log: string
  pdf_url: string | null
  errors: string[]
  warnings: string[]
}

export interface LatexCoachSession {
  session_id: string
  status: 'running' | 'completed' | 'error'
  filename: string
  paper_title: string
  compilation: CompilationResult | null
  structure: LatexStructure | null
  sections: SectionAnalysis[]
  suggested_tables: SuggestedTable[]
  suggested_figures: SuggestedFigure[]
  weak_claims: string[]
  global_assessment: GlobalAssessment | null
  annotated_pdf_url: string | null
  created_at: string
  progress: { percentage: number; logs: Array<{ timestamp: string; message: string; level: string }> }
  error?: string
}

export interface LatexCandidate {
  filename: string
  section_count: number
  size_kb: number
}

export interface LatexScanResult {
  candidates: LatexCandidate[]
  total_tex_files: number
}

export async function scanLatexZip(zipFile: File): Promise<LatexScanResult> {
  const form = new FormData()
  form.append('latex_zip', zipFile)
  const res = await fetch(`${API_BASE_URL}/api/latexcoach/scan`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Scan failed')
  return res.json()
}

export async function startLatexCoach(
  zipFile: File,
  mainTex?: string,
): Promise<{ session_id: string; filename: string }> {
  const form = new FormData()
  form.append('latex_zip', zipFile)
  if (mainTex) form.append('main_tex', mainTex)
  const res = await fetch(`${API_BASE_URL}/api/latexcoach`, { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json()
}

export async function getLatexCoachSession(sessionId: string): Promise<LatexCoachSession> {
  return fetchJSON<LatexCoachSession>(`/api/latexcoach/${sessionId}`)
}

export function streamLatexCoach(sessionId: string, onEvent: (e: SSEEvent) => void): () => void {
  return _streamGeneric(`/api/latexcoach/${sessionId}/stream`, onEvent)
}

export async function requestAnnotatedPdf(sessionId: string): Promise<{ annotated_pdf_url: string }> {
  return fetchJSON<{ annotated_pdf_url: string }>(`/api/latexcoach/${sessionId}/annotated`, {
    method: 'POST',
  })
}

export async function reanalyzeLatexCoach(sessionId: string): Promise<{ session_id: string; status: string }> {
  return fetchJSON<{ session_id: string; status: string }>(`/api/latexcoach/${sessionId}/reanalyze`, {
    method: 'POST',
  })
}

export async function patchLatexCoach(
  sessionId: string,
  suggestions: Array<{ section_idx: number; suggestion_idx: number }>,
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/latexcoach/${sessionId}/patch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ suggestions }),
  })
  if (!res.ok) throw new Error(`Patch failed: ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const cd = res.headers.get('content-disposition') || ''
  const match = cd.match(/filename="([^"]+)"/)
  a.download = match ? match[1] : 'patched.zip'
  a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Internal SSE helper
// ---------------------------------------------------------------------------

function _streamGeneric(path: string, onEvent: (e: SSEEvent) => void): () => void {
  const es = new EventSource(`${API_BASE_URL}${path}`)
  es.addEventListener('progress', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data as string)) } catch {}
  })
  es.addEventListener('complete', (e: MessageEvent) => {
    try { onEvent({ ...JSON.parse(e.data as string), type: 'complete' }) } catch { onEvent({ type: 'complete' }) }
    es.close()
  })
  es.onerror = () => { onEvent({ type: 'error', message: 'Stream error' }); es.close() }
  return () => es.close()
}

export function streamSession(
  sessionId: string,
  onEvent: (event: SSEEvent) => void
): () => void {
  const url = `${API_BASE_URL}/api/research/${sessionId}/stream`
  const eventSource = new EventSource(url)

  eventSource.addEventListener('progress', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data as string) as SSEEvent
      onEvent(data)
    } catch {
      // ignore parse errors
    }
  })

  eventSource.addEventListener('complete', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data as string) as SSEEvent
      onEvent(data)
    } catch {
      onEvent({ type: 'complete' })
    }
    eventSource.close()
  })

  eventSource.addEventListener('error', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data as string) as SSEEvent
      onEvent(data)
    } catch {
      onEvent({ type: 'error', message: 'Stream connection error' })
    }
    eventSource.close()
  })

  eventSource.onerror = () => {
    onEvent({ type: 'error', message: 'Failed to connect to stream' })
    eventSource.close()
  }

  return () => {
    eventSource.close()
  }
}
