import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export function useUsers(params: { q?: string; department?: string; role?: string; sort?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ["users", params],
    queryFn: async () => {
      const { data, error } = await api.GET("/users", { params: { query: params } });
      if (error) throw error;
      return data;
    },
  });
}

export function useUser(userId: string | undefined) {
  return useQuery({
    queryKey: ["user", userId],
    queryFn: async () => {
      const { data, error } = await api.GET("/users/{user_id}", { params: { path: { user_id: userId! } } });
      if (error) throw error;
      return data;
    },
    enabled: !!userId,
  });
}

export function useUserRisk(userId: string | undefined, dateFrom?: string, dateTo?: string) {
  return useQuery({
    queryKey: ["user-risk", userId, dateFrom, dateTo],
    queryFn: async () => {
      const { data, error } = await api.GET("/users/{user_id}/risk", {
        params: { path: { user_id: userId! }, query: { date_from: dateFrom, date_to: dateTo } },
      });
      if (error) throw error;
      return data;
    },
    enabled: !!userId,
  });
}

export function useUserTimeline(userId: string | undefined, date: string | undefined) {
  return useQuery({
    queryKey: ["user-timeline", userId, date],
    queryFn: async () => {
      const { data, error } = await api.GET("/users/{user_id}/timeline", {
        params: { path: { user_id: userId! }, query: { date: date! } },
      });
      if (error) throw error;
      return data;
    },
    enabled: !!userId && !!date,
  });
}
