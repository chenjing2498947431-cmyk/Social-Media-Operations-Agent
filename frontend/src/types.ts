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

/** 单个计算节点的运行指标（耗时 + token 用量）。 */
export interface NodeMetric {
  node: string;
  label: string;
  started_at: string;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  llm_calls: number;
}

/** 流式 SSE 中的节点生命周期事件。 */
export interface NodeEvent {
  type: 'node';
  node: string;
  label: string;
  phase: 'start' | 'end';
  metric?: NodeMetric;
}

/** 前端展示「节点运行过程」的一行记录。 */
export interface NodeRun {
  node: string;
  label: string;
  status: 'running' | 'done';
  durationMs?: number;
  totalTokens?: number;
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
  node_metrics?: NodeMetric[];
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
