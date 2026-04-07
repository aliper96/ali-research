import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

interface MarkdownContentProps {
  children: string
  className?: string
}

/**
 * Renders markdown text with GFM support (tables, strikethrough, task lists).
 * Styled for the dark theme used throughout the app.
 */
export default function MarkdownContent({ children, className }: MarkdownContentProps) {
  return (
    <div className={cn(
      'prose prose-invert prose-sm max-w-none',
      'prose-headings:text-slate-100 prose-headings:font-bold',
      'prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-h4:text-sm',
      'prose-p:text-slate-300 prose-p:leading-relaxed prose-p:my-2',
      'prose-strong:text-slate-100 prose-em:text-slate-300',
      'prose-code:text-orange-300 prose-code:bg-slate-800 prose-code:px-1 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none',
      'prose-pre:bg-slate-800 prose-pre:border prose-pre:border-slate-700',
      'prose-blockquote:border-orange-700 prose-blockquote:text-slate-400',
      'prose-ul:text-slate-300 prose-ol:text-slate-300',
      'prose-li:my-0.5 prose-li:marker:text-orange-400',
      'prose-a:text-orange-400 prose-a:no-underline hover:prose-a:underline',
      'prose-hr:border-slate-700',
      'prose-table:text-slate-300 prose-thead:border-slate-700 prose-tr:border-slate-800',
      'prose-th:text-slate-200 prose-td:text-slate-300',
      className,
    )}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
