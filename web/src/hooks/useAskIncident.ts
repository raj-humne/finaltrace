import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export function useAskIncident(incidentId: string) {
  return useMutation({
    mutationFn: async (question: string) => {
      const { data, error } = await api.POST("/api/v1/incidents/{incident_id}/ask", {
        params: { path: { incident_id: incidentId } },
        body: { question },
      });
      if (error) throw error;
      return data;
    },
  });
}
