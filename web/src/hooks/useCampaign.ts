import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export function useCampaign(campaignId: string | undefined) {
  return useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/campaigns/{campaign_id}", { params: { path: { campaign_id: campaignId! } } });
      if (error) throw error;
      return data;
    },
    enabled: !!campaignId,
  });
}
