import { useState } from 'react';
import { Alert, Button, Card, Input, Radio, Space, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import { useQueryClient } from '@tanstack/react-query';
import { selectTopicStream } from '../api/campaigns';
import { toErrorMessage } from '../api/client';
import { useNodeRuns } from '../hooks/nodeRuns';
import NodeProgressPanel from './NodeProgressPanel';
import type { Campaign } from '../types';

const CUSTOM = '__custom__';

export default function TopicSelectStep({ campaign }: { campaign: Campaign }) {
  const topics = campaign.workflow_state?.interrupt?.topics ?? [];
  const [selected, setSelected] = useState<string>('');
  const [custom, setCustom] = useState<string>('');
  const [streaming, setStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const { runs, onNode, onToolCall, reset } = useNodeRuns();
  const qc = useQueryClient();

  const finalTopic = selected === CUSTOM ? custom.trim() : selected;
  // 一旦开始生成（流式中 / 已有文本 / 出错），就切到生成视图
  const started = streaming || streamedText.length > 0 || error !== null;

  async function handleSubmit() {
    setStreaming(true);
    setStreamedText('');
    setError(null);
    reset();
    try {
      await selectTopicStream(campaign.id, finalTopic, {
        onDelta: (text) => setStreamedText((prev) => prev + text),
        onNode,
        onToolCall,
        onDone: (updated) => {
          // 写回缓存：父组件据此切到「文案审核」步骤
          qc.setQueryData(['campaign', updated.id], updated);
          qc.invalidateQueries({ queryKey: ['campaigns'] });
        },
        onError: (msg) => setError(msg),
      });
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setStreaming(false);
    }
  }

  function backToSelect() {
    setStreamedText('');
    setError(null);
    reset();
  }

  if (started) {
    const title = streaming
      ? '正在生成文案…'
      : error
        ? '文案生成失败'
        : '文案已生成';
    return (
      <Card title={title}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            {streaming
              ? 'AI 正在根据选题撰写文案，节点运行过程与内容实时显示…'
              : error
                ? '可重试，或返回重新选择选题。'
                : '生成完成，正在进入审核环节。'}
          </Typography.Text>

          <NodeProgressPanel runs={runs} />

          <div
            className="markdown-body"
            style={{
              border: '1px solid #f0f0f0',
              borderRadius: 8,
              padding: 16,
              minHeight: 180,
              maxHeight: 480,
              overflow: 'auto',
            }}
          >
            <ReactMarkdown>{streamedText}</ReactMarkdown>
            {streaming && <span className="stream-caret">▋</span>}
          </div>
          {error && (
            <>
              <Alert type="error" showIcon message="生成失败" description={error} />
              <Space>
                <Button type="primary" onClick={handleSubmit}>
                  重试
                </Button>
                <Button onClick={backToSelect}>返回重新选题</Button>
              </Space>
            </>
          )}
        </Space>
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
        <Button type="primary" disabled={!finalTopic} onClick={handleSubmit}>
          提交选题并生成文案
        </Button>
      </Space>
    </Card>
  );
}
