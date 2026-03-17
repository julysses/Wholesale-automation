import { useEffect, useState } from 'react';

// ── Minimal markdown → JSX renderer ────────────────────────────────────────
// Only handles the patterns present in USER_MANUAL.md.

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={i} className="bg-gray-100 text-[#E8720C] px-1 py-0.5 rounded text-[0.85em] font-mono">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

function MarkdownDoc({ source }: { source: string }) {
  const lines = source.split('\n');
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith('# ')) {
      nodes.push(
        <h1 key={i} className="text-3xl font-bold text-[#1B3A5C] mt-8 mb-4 pb-3 border-b-2 border-[#E8720C]">
          {line.slice(2)}
        </h1>
      );
      i++; continue;
    }

    if (line.startsWith('## ')) {
      nodes.push(
        <h2 key={i} className="text-xl font-bold text-[#1B3A5C] mt-10 mb-3 pb-1 border-b border-gray-200">
          {line.slice(3)}
        </h2>
      );
      i++; continue;
    }

    if (line.startsWith('### ')) {
      nodes.push(
        <h3 key={i} className="text-base font-bold text-[#1B3A5C] mt-6 mb-2">
          {line.slice(4)}
        </h3>
      );
      i++; continue;
    }

    if (line.startsWith('#### ')) {
      nodes.push(
        <h4 key={i} className="text-sm font-semibold text-gray-700 mt-4 mb-1">
          {line.slice(5)}
        </h4>
      );
      i++; continue;
    }

    if (/^-{3,}$/.test(line.trim())) {
      nodes.push(<hr key={i} className="my-6 border-gray-200" />);
      i++; continue;
    }

    if (line.startsWith('```')) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      nodes.push(
        <pre key={i} className="bg-gray-900 text-gray-100 rounded-lg p-4 my-3 overflow-x-auto text-sm font-mono leading-relaxed">
          {lang && <span className="text-gray-500 text-xs block mb-2">{lang}</span>}
          {codeLines.join('\n')}
        </pre>
      );
      i++; continue;
    }

    if (line.includes('|') && line.trim().startsWith('|')) {
      const tableRows: string[][] = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim().startsWith('|')) {
        const cells = lines[i].split('|').slice(1, -1).map(c => c.trim());
        if (!cells.every(c => /^:?-+:?$/.test(c))) {
          tableRows.push(cells);
        }
        i++;
      }
      if (tableRows.length > 0) {
        const [header, ...rows] = tableRows;
        nodes.push(
          <div key={i} className="my-4 overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-[#1B3A5C] text-white">
                <tr>
                  {header.map((cell, ci) => (
                    <th key={ci} className="px-4 py-2.5 text-left font-semibold whitespace-nowrap">
                      {renderInline(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, ri) => (
                  <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                    {row.map((cell, ci) => (
                      <td key={ci} className="px-4 py-2.5 border-t border-gray-100">
                        {renderInline(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      continue;
    }

    if (/^- \[[ x]\]/.test(line)) {
      const checked = line.startsWith('- [x]');
      const text = line.slice(6);
      nodes.push(
        <div key={i} className="flex items-start gap-2 my-1 ml-2">
          <input type="checkbox" checked={checked} readOnly
            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-[#E8720C] shrink-0" />
          <span className="text-sm text-gray-700">{renderInline(text)}</span>
        </div>
      );
      i++; continue;
    }

    if (/^(\s*)[-*] /.test(line)) {
      const indent = (line.match(/^(\s*)/)?.[1].length ?? 0) / 2;
      const text = line.replace(/^\s*[-*] /, '');
      nodes.push(
        <div key={i} className="flex items-start gap-2 my-0.5" style={{ marginLeft: `${indent * 1.25}rem` }}>
          <span className="text-[#E8720C] mt-1.5 shrink-0 text-xs">●</span>
          <span className="text-sm text-gray-700 leading-relaxed">{renderInline(text)}</span>
        </div>
      );
      i++; continue;
    }

    if (/^\d+\. /.test(line)) {
      const num = line.match(/^(\d+)\./)?.[1];
      const text = line.replace(/^\d+\. /, '');
      nodes.push(
        <div key={i} className="flex items-start gap-2 my-0.5 ml-2">
          <span className="text-[#E8720C] font-semibold text-sm shrink-0 w-5 text-right">{num}.</span>
          <span className="text-sm text-gray-700 leading-relaxed">{renderInline(text)}</span>
        </div>
      );
      i++; continue;
    }

    if (line.trim() === '') {
      nodes.push(<div key={i} className="h-2" />);
      i++; continue;
    }

    nodes.push(
      <p key={i} className="text-sm text-gray-700 leading-relaxed my-1">
        {renderInline(line)}
      </p>
    );
    i++;
  }

  return <>{nodes}</>;
}

// ── Page component ──────────────────────────────────────────────────────────

export function UserManual() {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch('/USER_MANUAL.md')
      .then(r => {
        if (!r.ok) throw new Error('Not found');
        return r.text();
      })
      .then(setContent)
      .catch(() => setError(true));
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header bar */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-[#1B3A5C]">User Manual</h1>
          <p className="text-sm text-gray-500 mt-0.5">WholesaleOS v2.0 — Precision Targeting Edition</p>
        </div>
        <a
          href="/USER_MANUAL.md"
          download="WholesaleOS_UserManual.md"
          className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
        >
          Download .md
        </a>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 px-8 py-6">
        {error ? (
          <p className="text-sm text-red-500">Could not load manual. Make sure USER_MANUAL.md is in the public folder.</p>
        ) : content === null ? (
          <div className="flex items-center gap-3 py-10 justify-center text-gray-400">
            <div className="h-5 w-5 border-2 border-gray-300 border-t-[#E8720C] rounded-full animate-spin" />
            <span className="text-sm">Loading manual…</span>
          </div>
        ) : (
          <MarkdownDoc source={content} />
        )}
      </div>
    </div>
  );
}
