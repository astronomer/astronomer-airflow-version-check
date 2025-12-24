/*!
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { ChakraProvider, Box } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { FC } from "react";

import { fetchStatus } from "src/api/versionCheck";
import { WarningBanner } from "src/components/WarningBanner";
import { system } from "./theme";

export type PluginComponentProps = object;

// Auto-refresh interval (5 minutes)
const AUTO_REFRESH_INTERVAL = 5 * 60 * 1000;

/**
 * Version Check content component that displays warnings
 */
const VersionCheckContent: FC = () => {
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
const PluginComponent: FC<PluginComponentProps> = () => {
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
