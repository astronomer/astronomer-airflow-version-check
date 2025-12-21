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
import { Button } from "@chakra-ui/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FC } from "react";
import { LuX } from "react-icons/lu";

import { dismissEobsWarning, dismissEomWarning, WarningType } from "src/api/versionCheck";

interface DismissButtonProps {
  warningType: WarningType;
  onDismissed?: () => void;
}

export const DismissButton: FC<DismissButtonProps> = ({ warningType, onDismissed }) => {
  const queryClient = useQueryClient();

  const dismissMutation = useMutation({
    mutationFn: () => {
      if (warningType === "eom") {
        return dismissEomWarning();
      } else if (warningType === "eobs") {
        return dismissEobsWarning();
      }
      throw new Error(`Cannot dismiss ${warningType} warnings`);
    },
    onSuccess: () => {
      // Invalidate and refetch the status
      queryClient.invalidateQueries({ queryKey: ["versionStatus"] });
      onDismissed?.();
    },
  });

  // Don't render for yanked warnings (can't be dismissed)
  if (warningType === "yanked") {
    return null;
  }

  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={() => dismissMutation.mutate()}
      loading={dismissMutation.isPending}
      aria-label="Dismiss warning"
      title="Dismiss warning for 7 days"
    >
      <LuX />
      Dismiss
    </Button>
  );
};
