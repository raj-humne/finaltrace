import { useQueries, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export function useRules() {
  return useQuery({
    queryKey: ["rules"],
    queryFn: async () => {
      const { data, error } = await api.GET("/rules", {});
      if (error) throw error;
      return data;
    },
  });
}

export function useRuleStatsFor(ruleIds: string[]) {
  return useQueries({
    queries: ruleIds.map((ruleId) => ({
      queryKey: ["rule-stats", ruleId],
      queryFn: async () => {
        const { data, error } = await api.GET("/rules/{rule_id}/stats", { params: { path: { rule_id: ruleId } } });
        if (error) throw error;
        return data;
      },
    })),
  });
}

export function useDetectionHealth() {
  return useQuery({
    queryKey: ["detection-health"],
    queryFn: async () => {
      const { data, error } = await api.GET("/detection/health", {});
      if (error) throw error;
      return data;
    },
  });
}
