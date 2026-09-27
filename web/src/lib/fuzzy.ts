/**
 * Subsequence fuzzy match: every character of `query` must appear in
 * `target`, in order, but not necessarily contiguously. Returns null when
 * `query` isn't a subsequence at all; otherwise a score where higher is a
 * better match — rewarding contiguous runs, word-boundary starts, earlier
 * matches, and exact/prefix matches, the same signals VS Code-style command
 * palettes rank on.
 */
export function fuzzyScore(query: string, target: string): number | null {
  if (!query) return 0;
  const q = query.toLowerCase();
  const t = target.toLowerCase();

  let score = 0;
  let searchFrom = 0;
  let consecutive = 0;
  let firstMatchIndex = -1;

  for (const ch of q) {
    const idx = t.indexOf(ch, searchFrom);
    if (idx === -1) return null;
    if (firstMatchIndex === -1) firstMatchIndex = idx;

    const isContiguous = idx === searchFrom;
    consecutive = isContiguous ? consecutive + 1 : 0;
    score += isContiguous ? 3 + consecutive : 1;

    const prevChar = t[idx - 1];
    if (idx === 0 || prevChar === " " || prevChar === "/" || prevChar === "-") score += 2;

    searchFrom = idx + 1;
  }

  const span = searchFrom - firstMatchIndex;
  score -= firstMatchIndex * 0.5;
  score -= span * 0.2;
  if (t === q) score += 100;
  else if (t.startsWith(q)) score += 20;

  return score;
}
