import { queryOptions } from "@tanstack/svelte-query";
import { loadCatalog } from "./catalog";
import { loadEnvironment, type RunnableEnvironment } from "./environment";

export function environmentQuery(id: string | null) {
  return queryOptions({
    queryKey: ["environment", id],
    queryFn: ({ signal }) => loadEnvironment(id, signal),
    refetchInterval: (query) => (query.state.data ? 10_000 : false),
    refetchIntervalInBackground: true,
  });
}

export function catalogQuery({ id, revision, sha, clis }: RunnableEnvironment) {
  return queryOptions({
    queryKey: ["catalog", id, revision, sha, clis],
    queryFn: ({ signal }) => loadCatalog(id, revision, sha, clis, signal),
    staleTime: (query) => (query.state.data ? Infinity : 0),
  });
}
