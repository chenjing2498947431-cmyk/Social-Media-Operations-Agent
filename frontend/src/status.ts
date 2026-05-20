import type { CampaignStatus } from './types';

/** campaign 状态 -> 中文标签 + AntD Tag 颜色。 */
export const STATUS_META: Record<CampaignStatus, { label: string; color: string }> = {
  pending_topic: { label: '待选题', color: 'gold' },
  pending_review: { label: '待审核', color: 'blue' },
  generating: { label: '生成中', color: 'processing' },
  completed: { label: '已完成', color: 'green' },
  failed: { label: '失败', color: 'red' },
};
