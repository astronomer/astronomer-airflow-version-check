import { ChakraProvider, Box } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

import { fetchStatus } from "src/api/versionCheck";
import { WarningBanner } from "src/components/WarningBanner";
import { system } from "./theme";

export type PluginComponentProps = object;

// Auto-refresh interval (5 minutes)
const AUTO_REFRESH_INTERVAL = 5 * 60 * 1000;

/**
 * Version Check content component that displays warnings
 */
const VersionCheckContent = () => {
  const { data, isLoading, error } = useQuery({
    queryKey: ["versionStatus"],
    queryFn: fetchStatus,
    refetchInterval: AUTO_REFRESH_INTERVAL,
    staleTime: AUTO_REFRESH_INTERVAL,
  });

  // Don't render anything if loading, error, or no warning
  if (isLoading || error || !data?.status?.warning) {
    return null;
  }

  return (
    <Box p={2}>
      <WarningBanner
        warning={data.status.warning}
        eomDismissalPeriodDays={data.eom_dismissal_period_days}
        eobsDismissalPeriodDays={data.eobs_dismissal_period_days}
      />
    </Box>
  );
};

/**
 * Main plugin component
 */
const PluginComponent = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: AUTO_REFRESH_INTERVAL,
        retry: 1,
      },
    },
  });

  return (
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <VersionCheckContent />
      </QueryClientProvider>
    </ChakraProvider>
  );
};

export default PluginComponent;
