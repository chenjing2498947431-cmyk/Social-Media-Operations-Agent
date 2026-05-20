// 与后端 shared_libs/schemas 对应的 TypeScript 类型。

export type CampaignStatus =
  | 'pending_topic'
  | 'pending_review'
  | 'generating'
  | 'completed'
  | 'failed';

export type WorkflowStage =
  | 'awaiting_topic'
  | 'awaiting_review'
  | 'running'
  | 'completed'
  | 'failed';

/** LangGraph 中断信息：根据 action 决定携带哪些字段。 */
export interface WorkflowInterrupt {
  action: 'select_topic' | 'review_article';
  prompt?: string;
  // action === 'select_topic'
  topics?: string[];
  // action === 'review_article'
  draft_article?: string;
  revision_round?: number;
}

/** LangGraph checkpoint 的 state 值。 */
export interface AgentStateValues {
  context?: string;
  topics?: string[];
  selected_topic?: string | null;
  draft_article?: string | null;
  human_feedback?: string | null;
  revision_round?: number;
  image_prompts?: string[];
  generated_images?: string[];
  status?: string;
}

export interface WorkflowState {
  thread_id: string;
  stage: WorkflowStage;
  state: AgentStateValues;
  interrupt?: WorkflowInterrupt | null;
}

export interface Campaign {
  id: string;
  title?: string | null;
  context: string;
  status: CampaignStatus;
  thread_id: string;
  created_at: string;
  updated_at: string;
  workflow_state?: WorkflowState | null;
}

export interface CampaignCreateRequest {
  context: string;
  title?: string;
}

export interface ReviewArticleRequest {
  decision: 'approve' | 'reject';
  feedback?: string;
}
