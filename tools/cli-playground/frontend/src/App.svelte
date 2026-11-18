<script lang="ts">
  import { QueryClient, QueryClientProvider } from "@tanstack/svelte-query";
  import Playground from "./preview/Playground.svelte";
  import { environmentIdFromPath } from "./services/environment";

  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        networkMode: "always",
      },
    },
  });
</script>

<QueryClientProvider {client}>
  <Playground id={environmentIdFromPath(window.location.pathname)} />
</QueryClientProvider>
