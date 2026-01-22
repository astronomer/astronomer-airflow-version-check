import { Button } from "@chakra-ui/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FC } from "react";
import { LuX } from "react-icons/lu";

import { dismissEobsWarning, dismissEomWarning, WarningType } from "src/api/versionCheck";

interface DismissButtonProps {
  warningType: WarningType;
  dismissalPeriodDays: number;
  onDismissed?: () => void;
}

export const DismissButton: FC<DismissButtonProps> = ({ warningType, dismissalPeriodDays, onDismissed }) => {
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
      title={`Dismiss warning for ${dismissalPeriodDays} day${dismissalPeriodDays !== 1 ? "s" : ""}`}
    >
      <LuX />
      Dismiss
    </Button>
  );
};
