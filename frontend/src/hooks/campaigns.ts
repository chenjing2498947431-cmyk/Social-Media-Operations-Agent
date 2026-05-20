import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createCampaign,
  getCampaign,
  listCampaigns,
  reviewArticle,
  selectTopic,
} from '../api/campaigns';
import type { Campaign, CampaignCreateRequest, ReviewArticleRequest } from '../types';

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

/** 提交选题后，把返回的最新 campaign 写回详情缓存。 */
function syncCampaign(qc: ReturnType<typeof useQueryClient>, data: Campaign) {
  qc.setQueryData(['campaign', data.id], data);
  qc.invalidateQueries({ queryKey: ['campaigns'] });
}

export function useSelectTopic(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (topic: string) => selectTopic(id, topic),
    onSuccess: (data) => syncCampaign(qc, data),
  });
}

export function useReviewArticle(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: ReviewArticleRequest) => reviewArticle(id, req),
    onSuccess: (data) => syncCampaign(qc, data),
  });
}
