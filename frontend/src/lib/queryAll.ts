/** Read every page with a stable server order; never present the API row cap as a total. */
export async function queryAll<T>(
  page: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>,
  pageSize = 500,
): Promise<T[]> {
  const rows: T[] = [];
  for (let from = 0; ;) {
    const { data, error } = await page(from, from + pageSize - 1);
    if (error) throw new Error(error.message);
    if (!data) throw new Error('The database did not return a result');
    if (data.length === 0) return rows;
    rows.push(...data);
    from += data.length;
  }
}

/** Bound IN filters as well as response pages for related-record lookups. */
export async function queryByIds<T>(
  ids: string[],
  page: (ids: string[], from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>,
): Promise<T[]> {
  const unique = [...new Set(ids)];
  const rows: T[] = [];
  for (let i = 0; i < unique.length; i += 100) {
    const batch = unique.slice(i, i + 100);
    rows.push(...await queryAll((from, to) => page(batch, from, to)));
  }
  return rows;
}

/** Confirm count and identities before replacing an operator's complete dataset. */
export async function queryAllConfirmed<T extends { id: string }>(
  page: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: { message: string } | null; count: number | null }>,
  label = 'Records',
): Promise<T[]> {
  let expected: number | undefined;
  const ids = new Set<string>();
  const rows = await queryAll<T>(async (from, to) => {
    const result = await page(from, to);
    if (result.error) throw new Error(result.error.message);
    if (result.count === null || !Number.isInteger(result.count) || result.count < 0) {
      throw new Error(`${label} count could not be confirmed. Refresh again.`);
    }
    if (expected !== undefined && expected !== result.count) {
      throw new Error(`${label} changed while loading. Refresh again.`);
    }
    expected = result.count;
    for (const row of result.data ?? []) {
      if (typeof row.id !== 'string' || !row.id || ids.has(row.id)) {
        throw new Error(`${label} changed while loading. Refresh again.`);
      }
      ids.add(row.id);
    }
    if (ids.size > expected) throw new Error(`${label} changed while loading. Refresh again.`);
    return result;
  });
  if (rows.length !== expected) throw new Error(`${label} could not be read completely. Refresh again.`);
  return rows;
}
