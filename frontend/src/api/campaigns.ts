import { apiClient } from './client';
import type { Campaign, CampaignCreateRequest, ReviewArticleRequest } from '../types';

export async function listCampaigns(): Promise<Campaign[]> {
  const { data } = await apiClient.get<Campaign[]>('/campaigns');
  return data;
}

export async function getCampaign(id: string): Promise<Campaign> {
  const { data } = await apiClient.get<Campaign>(`/campaigns/${id}`);
  return data;
}

export async function createCampaign(req: CampaignCreateRequest): Promise<Campaign> {
  const { data } = await apiClient.post<Campaign>('/campaigns', req);
  return data;
}

export async function selectTopic(id: string, selectedTopic: string): Promise<Campaign> {
  const { data } = await apiClient.post<Campaign>(`/campaigns/${id}/select-topic`, {
    selected_topic: selectedTopic,
  });
  return data;
}

export async function reviewArticle(
  id: string,
  req: ReviewArticleRequest,
): Promise<Campaign> {
  const { data } = await apiClient.post<Campaign>(`/campaigns/${id}/review-article`, req);
  return data;
}
