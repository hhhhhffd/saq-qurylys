import Markdown, { type Components } from 'react-markdown';
import { Link } from 'react-router';

const linkClass = 'text-link underline underline-offset-2 hover:text-accent-text';

const isInternal = (href: string) => href.startsWith('/') && !href.startsWith('//');

/** Hostname of an absolute URL, so the officer sees where the text points; links outside SAQ are never clickable. */
function externalHost(href: string): string | null {
  try {
    return new URL(href).hostname || null;
  } catch {
    return null;
  }
}

const components: Components = {
  a: ({ href, children }) =>
    href && isInternal(href) ? (
      <Link to={href} className={linkClass}>
        {children}
      </Link>
    ) : (
      <>
        {children}
        {href && externalHost(href) && <span className="text-text-3"> ({externalHost(href)})</span>}
      </>
    ),
  p: ({ children }) => <p className="m-0 [&:not(:first-child)]:mt-2">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc pl-5 first:mt-0 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal pl-5 first:mt-0 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="[&:not(:first-child)]:mt-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-text">{children}</strong>,
  h1: ({ children }) => <p className="m-0 mt-3 font-semibold text-text first:mt-0">{children}</p>,
  h2: ({ children }) => <p className="m-0 mt-3 font-semibold text-text first:mt-0">{children}</p>,
  h3: ({ children }) => <p className="m-0 mt-3 font-semibold text-text first:mt-0">{children}</p>,
  code: ({ children }) => <code className="rounded-sm bg-surface-sunken px-1 py-0.5 font-mono text-xs text-text">{children}</code>,
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded border border-border bg-surface-sunken p-2 [&_code]:bg-transparent [&_code]:p-0">{children}</pre>
  ),
  blockquote: ({ children }) => <blockquote className="my-2 border-l-2 border-border-strong pl-3 text-text-3">{children}</blockquote>,
};

/** Model answer as markdown: no raw HTML, SAQ paths navigate in the app, other links stay plain text with their host (a prompt-injected link must not be clickable). */
export function AssistantMarkdown({ children }: { children: string }) {
  return <Markdown components={components}>{children}</Markdown>;
}
