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
