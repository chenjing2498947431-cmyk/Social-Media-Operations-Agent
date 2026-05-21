import { apiClient } from './client';
import type {
  Campaign,
  CampaignCreateRequest,
  NodeEvent,
  NodeMetric,
  ReviewArticleRequest,
} from '../types';

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

export interface StreamHandlers {
  /** 文案文本增量（仅文案生成步骤会有）。 */
  onDelta?: (text: string) => void;
  /** 节点开始 / 结束事件。 */
  onNode?: (evt: NodeEvent) => void;
  /** 执行完成，返回更新后的 campaign。 */
  onDone: (campaign: Campaign) => void;
  /** 服务端报告的错误。 */
  onError: (message: string) => void;
}

/**
 * 读取后端的 SSE 流（fetch + ReadableStream），按事件类型分发。
 *
 * axios 不适合处理流式响应，故用原生 fetch。
 */
async function streamResume(
  url: string,
  body: unknown,
  handlers: StreamHandlers,
): Promise<void> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`请求失败（HTTP ${resp.status}）`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 以空行（\n\n）分隔事件
    let sep: number;
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = block.split('\n').find((l) => l.startsWith('data:'));
      if (!dataLine) continue;

      let evt: {
        type?: string;
        text?: string;
        node?: string;
        label?: string;
        phase?: 'start' | 'end';
        metric?: NodeMetric;
        campaign?: Campaign;
        message?: string;
      };
      try {
        evt = JSON.parse(dataLine.slice(5).trim());
      } catch {
        continue;
      }
      if (evt.type === 'delta') handlers.onDelta?.(evt.text ?? '');
      else if (evt.type === 'node') handlers.onNode?.(evt as NodeEvent);
      else if (evt.type === 'done' && evt.campaign) handlers.onDone(evt.campaign);
      else if (evt.type === 'error') handlers.onError(evt.message ?? '执行失败');
    }
  }
}

/** 流式提交选题：边生成文案边接收，并回传节点运行过程。 */
export function selectTopicStream(
  id: string,
  selectedTopic: string,
  handlers: StreamHandlers,
): Promise<void> {
  return streamResume(
    `/api/v1/campaigns/${id}/select-topic/stream`,
    { selected_topic: selectedTopic },
    handlers,
  );
}

/** 流式提交审核结果：实时回传节点运行过程。 */
export function reviewArticleStream(
  id: string,
  req: ReviewArticleRequest,
  handlers: StreamHandlers,
): Promise<void> {
  return streamResume(`/api/v1/campaigns/${id}/review-article/stream`, req, handlers);
}
