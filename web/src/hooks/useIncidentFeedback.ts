import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/types.gen";

type FeedbackRequest = components["schemas"]["FeedbackRequest"];

/**
 * Analyst Feedback Loop for False-Positive Reduction (Challenge 2) — mirrors
 * useReviewIncident.ts's shape. Distinct from that hook: this one calls
 * POST /{incident_id}/feedback, which (server-side) also recomputes the
 * user's behavioral baseline and decays learned correlation-edge weights,
 * not just records a verdict.
 */
export function useIncidentFeedback(incidentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: FeedbackRequest) => {
      const { data, error } = await api.POST("/api/v1/incidents/{incident_id}/feedback", {
        params: { path: { incident_id: incidentId } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["incident", incidentId] });
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}
