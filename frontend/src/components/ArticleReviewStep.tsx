import { useState } from 'react';
import { Alert, Button, Card, Input, Space, Spin, Tag, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import { useReviewArticle } from '../hooks/campaigns';
import { toErrorMessage } from '../api/client';
import type { Campaign } from '../types';

export default function ArticleReviewStep({ campaign }: { campaign: Campaign }) {
  const interrupt = campaign.workflow_state?.interrupt;
  const state = campaign.workflow_state?.state;
  const draft = interrupt?.draft_article ?? state?.draft_article ?? '';
  const round = interrupt?.revision_round ?? state?.revision_round ?? 0;
  const [feedback, setFeedback] = useState('');
  const mutation = useReviewArticle(campaign.id);

  if (mutation.isPending) {
    const tip =
      mutation.variables?.decision === 'approve'
        ? '已通过，正在生成配图，约 30-60 秒，请稍候…'
        : '正在根据修改意见改写文案，约 20-40 秒，请稍候…';
    return (
      <Card>
        <Spin tip={tip}>
          <div style={{ height: 120 }} />
        </Spin>
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
        {mutation.isError && (
          <Alert
            type="error"
            showIcon
            message="提交失败"
            description={toErrorMessage(mutation.error)}
          />
        )}
        <Space>
          <Button
            type="primary"
            onClick={() => mutation.mutate({ decision: 'approve' })}
          >
            通过，生成配图
          </Button>
          <Button
            danger
            disabled={!feedback.trim()}
            onClick={() =>
              mutation.mutate({ decision: 'reject', feedback: feedback.trim() })
            }
          >
            退回修改
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
