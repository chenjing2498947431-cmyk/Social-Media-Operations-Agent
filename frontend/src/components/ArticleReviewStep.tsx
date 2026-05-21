import { useState } from 'react';
import { Alert, Button, Card, Input, Space, Tag, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import { useQueryClient } from '@tanstack/react-query';
import { reviewArticleStream } from '../api/campaigns';
import { toErrorMessage } from '../api/client';
import { useNodeRuns } from '../hooks/nodeRuns';
import NodeProgressPanel from './NodeProgressPanel';
import type { Campaign, ReviewArticleRequest } from '../types';

export default function ArticleReviewStep({ campaign }: { campaign: Campaign }) {
  const interrupt = campaign.workflow_state?.interrupt;
  const state = campaign.workflow_state?.state;
  const draft = interrupt?.draft_article ?? state?.draft_article ?? '';
  const round = interrupt?.revision_round ?? state?.revision_round ?? 0;
  const [feedback, setFeedback] = useState('');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { runs, onNode, reset } = useNodeRuns();
  const qc = useQueryClient();

  async function submit(req: ReviewArticleRequest) {
    setRunning(true);
    setError(null);
    reset();
    try {
      await reviewArticleStream(campaign.id, req, {
        onNode,
        onDone: (updated) => {
          // 写回缓存：approve → 父组件切到结果页；reject → 重新渲染审核（新草稿）
          qc.setQueryData(['campaign', updated.id], updated);
          qc.invalidateQueries({ queryKey: ['campaigns'] });
          setFeedback('');
        },
        onError: (msg) => setError(msg),
      });
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setRunning(false);
    }
  }

  if (running) {
    return (
      <Card title="Agent 处理中…">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            正在执行工作流节点，请稍候…
          </Typography.Text>
          <NodeProgressPanel runs={runs} />
        </Space>
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          第三步 · 审核文案
          {round > 0 && <Tag color="blue">第 {round} 轮修订</Tag>}
        </Space>
      }
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div
          className="markdown-body"
          style={{
            border: '1px solid #f0f0f0',
            borderRadius: 8,
            padding: 16,
            maxHeight: 480,
            overflow: 'auto',
          }}
        >
          <ReactMarkdown>{draft}</ReactMarkdown>
        </div>
        <Typography.Text type="secondary">
          通过后进入配图生成；退回则填写修改意见，AI 会重写后再次送审。
        </Typography.Text>
        <Input.TextArea
          rows={3}
          placeholder="退回修改时的修改意见（点「通过」时可不填）"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
        {error && (
          <Alert type="error" showIcon message="提交失败" description={error} />
        )}
        <Space>
          <Button type="primary" onClick={() => submit({ decision: 'approve' })}>
            通过，生成配图
          </Button>
          <Button
            danger
            disabled={!feedback.trim()}
            onClick={() =>
              submit({ decision: 'reject', feedback: feedback.trim() })
            }
          >
            退回修改
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
