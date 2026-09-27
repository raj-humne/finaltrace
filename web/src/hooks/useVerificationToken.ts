import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

/**
 * Issues a single-use signed verification token for an AUTO_FLAG incident
 * (judge-requested: "the flagged report can be shown to identify the fake
 * report"). Mirrors useIncidentFeedback.ts's shape. Distinct from every
 * other mutation in this app: the token this returns is meant to be copied
 * out and handed to someone with no SentinelTrace account at all — see
 * VerifyTokenPage.tsx, which is intentionally NOT behind <Protected>.
 */
export function useIssueVerificationToken(incidentId: string) {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/v1/incidents/{incident_id}/verification-token", {
        params: { path: { incident_id: incidentId } },
      });
      if (error) throw error;
      return data;
    },
  });
}
