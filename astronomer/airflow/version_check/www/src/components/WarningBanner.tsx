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
import { Alert, Box, Flex, HStack, Text } from "@chakra-ui/react";
import { FC } from "react";
import { LuTriangleAlert, LuCircleAlert, LuShieldAlert } from "react-icons/lu";

import { VersionWarning } from "src/api/versionCheck";
import { DismissButton } from "./DismissButton";

interface WarningBannerProps {
  warning: VersionWarning;
}

const getWarningTitle = (type: VersionWarning["type"]): string => {
  switch (type) {
    case "eom":
      return "End of Maintenance Warning";
    case "eobs":
      return "End of Basic Support Warning";
    case "yanked":
      return "Yanked Version Warning";
    default:
      return "Version Warning";
  }
};

const getWarningIcon = (type: VersionWarning["type"], level: VersionWarning["level"]) => {
  if (type === "yanked") {
    return <LuShieldAlert size={20} />;
  }
  if (level === "critical") {
    return <LuCircleAlert size={20} />;
  }
  return <LuTriangleAlert size={20} />;
};

export const WarningBanner: FC<WarningBannerProps> = ({ warning }) => {
  const { type, level, message, can_dismiss } = warning;
  const title = getWarningTitle(type);
  const icon = getWarningIcon(type, level);

  // Map our warning levels to Chakra UI status
  const status = level === "critical" ? "error" : "warning";

  return (
    <Alert.Root status={status} variant="subtle" borderRadius="md" mb={4}>
      <Flex width="100%" justifyContent="space-between" alignItems="flex-start">
        <HStack alignItems="flex-start" gap={3}>
          <Alert.Indicator>
            {icon}
          </Alert.Indicator>
          <Box>
            <Alert.Title fontWeight="bold" mb={1}>
              {title}
            </Alert.Title>
            <Alert.Description>
              <Text>{message}</Text>
              {warning.days_remaining !== null && warning.days_remaining > 0 && (
                <Text fontSize="sm" mt={1} opacity={0.8}>
                  {warning.days_remaining} days remaining
                </Text>
              )}
            </Alert.Description>
          </Box>
        </HStack>
        {can_dismiss && (
          <DismissButton warningType={type} />
        )}
      </Flex>
    </Alert.Root>
  );
};
