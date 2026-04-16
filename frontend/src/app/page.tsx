import UnifiedSearch from '@/components/UnifiedSearch'
import SessionHistory from '@/components/SessionHistory'
import {
  Cpu, Database, Globe, FileText, FlaskConical,
  Bell, GitCompareArrows, RefreshCw, BookMarked, FolderOpen,
  Brain, Search, BookOpenCheck, ArrowRight, FileCode2,
} from 'lucide-react'
import Link from 'next/link'

// Featured workflow card
const FEATURED = [
  {
    href: '/deepresearch',
    icon: Cpu,
    label: 'Deep Research',
    description: 'Multi-step autonomous research over arXiv and Semantic Scholar with roadmap generation.',
    color: 'indigo',
    border: 'border-indigo-900/50 hover:border-indigo-700/60',
    bg: 'bg-indigo-950/20 hover:bg-indigo-900/15',
    iconColor: 'text-indigo-400',
    badge: 'Agentic',
  },
  {
    href: '/docs',
    icon: BookOpenCheck,
    label: 'Document Q&A',
    description: 'Upload PDFs or text files and chat with your own documents. RAG-powered, runs locally.',
    color: 'violet',
    border: 'border-violet-900/50 hover:border-violet-700/60',
    bg: 'bg-violet-950/20 hover:bg-violet-900/15',
    iconColor: 'text-violet-400',
    badge: 'RAG',
  },
]

// Secondary tools — compact chip row
const SECONDARY = [
  { href: '/websearch',    icon: Search,           label: 'Web Search',    color: 'hover:text-cyan-300' },
  { href: '/latexcoach',   icon: FileCode2,        label: 'LaTeX Coach',   color: 'hover:text-emerald-300' },
  { href: '/review',       icon: FileText,         label: 'Review Paper',  color: 'hover:text-violet-300' },
  { href: '/audit',        icon: FlaskConical,     label: 'Audit Paper',   color: 'hover:text-amber-300' },
  { href: '/global-network', icon: Globe,          label: 'Global Network',color: 'hover:text-indigo-300' },
  { href: '/watch',        icon: Bell,             label: 'Watches',       color: 'hover:text-emerald-300' },
  { href: '/autoresearch', icon: RefreshCw,        label: 'Auto Research', color: 'hover:text-emerald-300' },
  { href: '/lit',          icon: BookMarked,       label: 'Lit Review',    color: 'hover:text-violet-300' },
  { href: '/compare',      icon: GitCompareArrows, label: 'Compare',       color: 'hover:text-cyan-300' },
  { href: '/draft',        icon: FileText,         label: 'Draft',         color: 'hover:text-orange-300' },
  { href: '/outputs',      icon: FolderOpen,       label: 'Outputs',       color: 'hover:text-yellow-300' },
  { href: '/knowledge',    icon: Brain,            label: 'Knowledge',     color: 'hover:text-teal-300' },
]

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col bg-[#080d1a]">

      {/* Background blobs */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-56 -left-56 h-[500px] w-[500px] rounded-full bg-indigo-900/8 blur-[100px]" />
        <div className="absolute top-1/2 -right-56 h-[400px] w-[400px] rounded-full bg-indigo-900/6 blur-[80px]" />
        <div className="absolute bottom-0 left-1/4 h-[300px] w-[300px] rounded-full bg-purple-900/6 blur-[80px]" />
        {/* Subtle grid */}
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{
            backgroundImage:
              'linear-gradient(#6366f1 1px, transparent 1px), linear-gradient(90deg, #6366f1 1px, transparent 1px)',
            backgroundSize: '64px 64px',
          }}
        />
      </div>

      {/* Main content */}
      <div className="relative flex flex-1 flex-col px-4 py-16 max-w-4xl mx-auto w-full">

        {/* ── Hero ────────────────────────────────────────────────────────── */}
        <div className="mb-14 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-900/60 bg-indigo-950/30 px-4 py-1.5 text-xs text-indigo-400 mb-6">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
            Powered by Claude AI
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight font-[family-name:var(--font-display)] mb-4">
            <span className="gradient-text">ali_researcher</span>
          </h1>

          <p className="text-lg text-slate-400 max-w-lg mx-auto leading-relaxed">
            AI-powered research assistant.{' '}
            <span className="text-slate-300">Search papers or the web — it figures out which automatically.</span>
          </p>
        </div>

        {/* ── Main search ─────────────────────────────────────────────────── */}
        <div className="w-full mb-16">
          <UnifiedSearch />
        </div>

        {/* ── Featured workflows ──────────────────────────────────────────── */}
        <div className="mb-10">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-600 mb-4">
            Featured workflows
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {FEATURED.map((item) => {
              const Icon = item.icon
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`group flex flex-col gap-3 rounded-2xl border ${item.border} ${item.bg} p-5 transition-all duration-200`}
                >
                  <div className="flex items-center justify-between">
                    <div className={`flex items-center gap-2 ${item.iconColor}`}>
                      <Icon className="h-4 w-4" />
                      <span className="text-sm font-semibold">{item.label}</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-600 border border-[#1d2d47] rounded px-1.5 py-0.5">
                      {item.badge}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    {item.description}
                  </p>
                  <div className={`flex items-center gap-1 text-xs ${item.iconColor} opacity-0 group-hover:opacity-100 transition-opacity`}>
                    Open <ArrowRight className="h-3 w-3" />
                  </div>
                </Link>
              )
            })}
          </div>
        </div>

        {/* ── Secondary tools ─────────────────────────────────────────────── */}
        <div className="flex flex-wrap gap-2 justify-center mb-12">
          {SECONDARY.map((item) => {
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex items-center gap-1.5 rounded-full border border-[#1d2d47] bg-[#0d1526]/50 px-3.5 py-1.5 text-xs text-slate-500 transition-all duration-150 hover:border-[#2d3f5a] ${item.color}`}
              >
                <Icon className="h-3 w-3" />
                {item.label}
              </Link>
            )
          })}
        </div>

        {/* ── Session history ──────────────────────────────────────────────── */}
        <SessionHistory />

        {/* ── Feature pills ───────────────────────────────────────────────── */}
        <div className="mt-12 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            {
              icon: <Search className="h-4 w-4 text-indigo-400" />,
              title: 'Smart Search',
              description: 'Auto-detects papers vs. web — just type and go',
            },
            {
              icon: <Cpu className="h-4 w-4 text-indigo-400" />,
              title: 'AI Analysis',
              description: 'Summarize findings, identify key concepts and gaps',
            },
            {
              icon: <Database className="h-4 w-4 text-indigo-400" />,
              title: 'Research Roadmap',
              description: 'Step-by-step guide with difficulty ratings',
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="rounded-xl border border-[#1d2d47] bg-[#0d1526]/40 p-4 text-center"
            >
              <div className="mx-auto mb-2.5 flex h-8 w-8 items-center justify-center rounded-full bg-indigo-900/30 border border-indigo-900/50">
                {feature.icon}
              </div>
              <h3 className="text-sm font-semibold text-slate-200 mb-1 font-[family-name:var(--font-display)]">
                {feature.title}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <footer className="relative border-t border-[#1d2d47]/50 py-6 text-center">
        <p className="text-xs text-slate-700">
          Claude + arXiv + Semantic Scholar + SearXNG
        </p>
      </footer>
    </main>
  )
}
