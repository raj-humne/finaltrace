import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export interface IncidentQueueFilters {
  lane?: string;
  status?: string;
  min_risk?: number;
  min_confidence?: number;
  user_id?: string;
  stage_max?: number;
  campaign_id?: string;
  sort?: string;
  limit?: number;
}

export function useIncidents(filters: IncidentQueueFilters = {}) {
  return useQuery({
    queryKey: ["incidents", filters],
    queryFn: async () => {
      const { data, error } = await api.GET("/incidents", { params: { query: filters } });
      if (error) throw error;
      return data;
    },
  });
}

export function useIncident(incidentId: string | undefined) {
  return useQuery({
    queryKey: ["incident", incidentId],
    queryFn: async () => {
      const { data, error } = await api.GET("/incidents/{incident_id}", { params: { path: { incident_id: incidentId! } } });
      if (error) throw error;
      return data;
    },
    enabled: !!incidentId,
  });
}

export function useIncidentGraph(incidentId: string | undefined) {
  return useQuery({
    queryKey: ["incident-graph", incidentId],
    queryFn: async () => {
      const { data, error } = await api.GET("/incidents/{incident_id}/graph", { params: { path: { incident_id: incidentId! } } });
      if (error) throw error;
      return data;
    },
    enabled: !!incidentId,
  });
}
