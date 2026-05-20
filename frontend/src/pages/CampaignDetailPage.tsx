import { Alert, Button, Card, Skeleton, Space, Steps, Tag, Typography } from 'antd';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import { Link, useParams } from 'react-router-dom';
import { useCampaign } from '../hooks/campaigns';
import { toErrorMessage } from '../api/client';
import { STATUS_META } from '../status';
import type { CampaignStatus } from '../types';
import TopicSelectStep from '../components/TopicSelectStep';
import ArticleReviewStep from '../components/ArticleReviewStep';
import ResultPanel from '../components/ResultPanel';

const STEP_ITEMS = [
  { title: '创建任务' },
  { title: '选题确认' },
  { title: '文案审核' },
  { title: '完成' },
];

function currentStep(status: CampaignStatus): number {
  switch (status) {
    case 'pending_topic':
      return 1;
    case 'pending_review':
    case 'generating':
      return 2;
    case 'completed':
      return 3;
    default:
      return 0;
  }
}

function stepsStatus(status: CampaignStatus): 'error' | 'finish' | 'process' {
  if (status === 'failed') return 'error';
  if (status === 'completed') return 'finish';
  return 'process';
}

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: campaign, isLoading, isError, error, refetch, isFetching } =
    useCampaign(id);

  if (isLoading) {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 6 }} />
      </Card>
    );
  }

  if (isError || !campaign) {
    return (
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Link to="/">
          <Button icon={<ArrowLeftOutlined />}>返回列表</Button>
        </Link>
        <Alert
          type="error"
          showIcon
          message="加载任务失败"
          description={toErrorMessage(error)}
        />
      </Space>
    );
  }

  const meta = STATUS_META[campaign.status];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Link to="/">
          <Button icon={<ArrowLeftOutlined />}>返回列表</Button>
        </Link>
        <Button
          icon={<ReloadOutlined />}
          loading={isFetching}
          onClick={() => refetch()}
        >
          刷新
        </Button>
      </div>

      <Card>
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Space>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {campaign.title || '未命名任务'}
            </Typography.Title>
            <Tag color={meta.color}>{meta.label}</Tag>
          </Space>
          <Typography.Text type="secondary">
            背景：{campaign.context}
          </Typography.Text>
        </Space>
      </Card>

      <Card>
        <Steps
          current={currentStep(campaign.status)}
          status={stepsStatus(campaign.status)}
          items={STEP_ITEMS}
        />
      </Card>

      {campaign.status === 'pending_topic' && (
        <TopicSelectStep campaign={campaign} />
      )}
      {(campaign.status === 'pending_review' ||
        campaign.status === 'generating') && (
        <ArticleReviewStep campaign={campaign} />
      )}
      {campaign.status === 'completed' && <ResultPanel campaign={campaign} />}
      {campaign.status === 'failed' && (
        <Alert
          type="error"
          showIcon
          message="工作流执行失败"
          description="请查看后端日志排查原因，或重新创建任务。"
        />
      )}
    </Space>
  );
}
