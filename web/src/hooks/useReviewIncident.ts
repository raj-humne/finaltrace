import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/types.gen";

type ReviewRequest = components["schemas"]["ReviewRequest"];

export function useReviewIncident(incidentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ReviewRequest) => {
      const { data, error } = await api.POST("/incidents/{incident_id}/review", {
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
