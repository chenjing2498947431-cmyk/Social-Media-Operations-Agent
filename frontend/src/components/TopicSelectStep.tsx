import { useState } from 'react';
import { Alert, Button, Card, Input, Radio, Space, Spin, Typography } from 'antd';
import { useSelectTopic } from '../hooks/campaigns';
import { toErrorMessage } from '../api/client';
import type { Campaign } from '../types';

const CUSTOM = '__custom__';

export default function TopicSelectStep({ campaign }: { campaign: Campaign }) {
  const topics = campaign.workflow_state?.interrupt?.topics ?? [];
  const [selected, setSelected] = useState<string>('');
  const [custom, setCustom] = useState<string>('');
  const mutation = useSelectTopic(campaign.id);

  const finalTopic = selected === CUSTOM ? custom.trim() : selected;

  if (mutation.isPending) {
    return (
      <Card>
        <Spin tip="正在根据选题生成文案，约 20-40 秒，请稍候…">
          <div style={{ height: 120 }} />
        </Spin>
      </Card>
    );
  }

  return (
    <Card title="第二步 · 确认选题">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Typography.Text type="secondary">
          从 AI 生成的备选选题中挑选一个，或自定义一个选题：
        </Typography.Text>
        <Radio.Group
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
        >
          {topics.map((t) => (
            <Radio key={t} value={t}>
              {t}
            </Radio>
          ))}
          <Radio value={CUSTOM}>自定义选题</Radio>
        </Radio.Group>
        {selected === CUSTOM && (
          <Input
            placeholder="请输入自定义选题"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            maxLength={60}
          />
        )}
        {mutation.isError && (
          <Alert
            type="error"
            showIcon
            message="提交失败"
            description={toErrorMessage(mutation.error)}
          />
        )}
        <Button
          type="primary"
          disabled={!finalTopic}
          onClick={() => mutation.mutate(finalTopic)}
        >
          提交选题并生成文案
        </Button>
      </Space>
    </Card>
  );
}
