import SearchForm from '@/components/SearchForm'
import SessionHistory from '@/components/SessionHistory'
import { BookOpen, Cpu, Database, Globe, FileText, FlaskConical, Bell, GitCompareArrows, RefreshCw, BookMarked, FolderOpen, Brain } from 'lucide-react'
import Link from 'next/link'

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col">
      {/* Background decorations */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 h-80 w-80 rounded-full bg-indigo-900/10 blur-3xl" />
        <div className="absolute top-1/3 -right-40 h-96 w-96 rounded-full bg-indigo-900/10 blur-3xl" />
        <div className="absolute -bottom-40 left-1/3 h-80 w-80 rounded-full bg-purple-900/10 blur-3xl" />

        {/* Grid overlay */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'linear-gradient(#6366f1 1px, transparent 1px), linear-gradient(90deg, #6366f1 1px, transparent 1px)',
            backgroundSize: '60px 60px',
          }}
        />
      </div>

      {/* Content */}
      <div className="relative flex flex-1 flex-col items-center justify-center px-4 py-16">
        {/* Header */}
        <div className="mb-12 text-center space-y-4">
          {/* Row 1: branding + existing tools */}
          <div className="flex flex-wrap items-center justify-center gap-2 mb-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-800/50 bg-indigo-900/20 px-4 py-1.5 text-xs text-indigo-300">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Powered by Claude AI
            </div>
            <Link
              href="/global-network"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-indigo-700/60 hover:bg-indigo-900/20 hover:text-indigo-300 transition-all duration-200"
            >
              <Globe className="h-3.5 w-3.5" />
              Global Network
            </Link>
            <Link
              href="/review"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-violet-700/60 hover:bg-violet-900/20 hover:text-violet-300 transition-all duration-200"
            >
              <FileText className="h-3.5 w-3.5" />
              Review My Paper
            </Link>
            <Link
              href="/audit"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-amber-700/60 hover:bg-amber-900/20 hover:text-amber-300 transition-all duration-200"
            >
              <FlaskConical className="h-3.5 w-3.5" />
              Audit a Paper
            </Link>
            <Link
              href="/watch"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-emerald-700/60 hover:bg-emerald-900/20 hover:text-emerald-300 transition-all duration-200"
            >
              <Bell className="h-3.5 w-3.5" />
              Watches
            </Link>
          </div>

          {/* Row 2: new workflows */}
          <div className="flex flex-wrap items-center justify-center gap-2 mb-6">
            <Link
              href="/deepresearch"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-indigo-700/60 hover:bg-indigo-900/20 hover:text-indigo-300 transition-all duration-200"
            >
              <Cpu className="h-3.5 w-3.5" />
              Deep Research
            </Link>
            <Link
              href="/autoresearch"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-emerald-700/60 hover:bg-emerald-900/20 hover:text-emerald-300 transition-all duration-200"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Auto Research
            </Link>
            <Link
              href="/lit"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-violet-700/60 hover:bg-violet-900/20 hover:text-violet-300 transition-all duration-200"
            >
              <BookMarked className="h-3.5 w-3.5" />
              Lit Review
            </Link>
            <Link
              href="/compare"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-cyan-700/60 hover:bg-cyan-900/20 hover:text-cyan-300 transition-all duration-200"
            >
              <GitCompareArrows className="h-3.5 w-3.5" />
              Compare
            </Link>
            <Link
              href="/draft"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-orange-700/60 hover:bg-orange-900/20 hover:text-orange-300 transition-all duration-200"
            >
              <FileText className="h-3.5 w-3.5" />
              Draft
            </Link>
            <Link
              href="/outputs"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-yellow-700/60 hover:bg-yellow-900/20 hover:text-yellow-300 transition-all duration-200"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              Outputs
            </Link>
            <Link
              href="/knowledge"
              className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 text-xs text-slate-400 hover:border-teal-700/60 hover:bg-teal-900/20 hover:text-teal-300 transition-all duration-200"
            >
              <Brain className="h-3.5 w-3.5" />
              Knowledge
            </Link>
          </div>

          <h1 className="text-5xl font-bold tracking-tight sm:text-6xl lg:text-7xl">
            <span className="gradient-text">ali_researcher</span>
          </h1>

          <p className="mt-4 text-lg text-slate-400 max-w-md mx-auto leading-relaxed">
            AI-powered academic research assistant.{' '}
            <span className="text-slate-300">Explore papers, find gaps, build your roadmap.</span>
          </p>
        </div>

        {/* Search Form */}
        <div className="w-full max-w-2xl">
          <SearchForm />
        </div>

        {/* Session History */}
        <SessionHistory />

        {/* Feature highlights */}
        <div className="mt-16 grid grid-cols-1 gap-4 sm:grid-cols-3 max-w-2xl w-full">
          {[
            {
              icon: <BookOpen className="h-5 w-5 text-indigo-400" />,
              title: 'Paper Discovery',
              description: 'Search arXiv, Semantic Scholar and curated databases',
            },
            {
              icon: <Cpu className="h-5 w-5 text-indigo-400" />,
              title: 'AI Analysis',
              description: 'Summarize findings, identify key concepts and gaps',
            },
            {
              icon: <Database className="h-5 w-5 text-indigo-400" />,
              title: 'Research Roadmap',
              description: 'Step-by-step implementation guide with difficulty ratings',
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="rounded-lg border border-slate-800 bg-slate-900/50 p-4 text-center"
            >
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-indigo-900/40 border border-indigo-800/50">
                {feature.icon}
              </div>
              <h3 className="text-sm font-semibold text-slate-200 mb-1">{feature.title}</h3>
              <p className="text-xs text-slate-500 leading-relaxed">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <footer className="relative border-t border-slate-800/50 py-6 text-center">
        <p className="text-xs text-slate-600">
          Powered by{' '}
          <span className="text-slate-500">Claude</span>
          {' + '}
          <span className="text-slate-500">arXiv</span>
          {' + '}
          <span className="text-slate-500">Semantic Scholar</span>
        </p>
      </footer>
    </main>
  )
}
