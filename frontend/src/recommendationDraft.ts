export function shouldLoadRecommendationDraft(
  userId: string | undefined,
  loadedUserId: string | null,
  refreshVersion: number,
  handledRefreshVersion: number,
): boolean {
  return Boolean(userId && (userId !== loadedUserId || refreshVersion !== handledRefreshVersion))
}
