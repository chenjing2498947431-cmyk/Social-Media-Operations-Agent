import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createCampaign, getCampaign, listCampaigns } from '../api/campaigns';
import type { CampaignCreateRequest } from '../types';

export function useCampaigns() {
  return useQuery({ queryKey: ['campaigns'], queryFn: listCampaigns });
}

export function useCampaign(id: string | undefined) {
  return useQuery({
    queryKey: ['campaign', id],
    queryFn: () => getCampaign(id as string),
    enabled: !!id,
  });
}

export function useCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CampaignCreateRequest) => createCampaign(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] });
    },
  });
}
