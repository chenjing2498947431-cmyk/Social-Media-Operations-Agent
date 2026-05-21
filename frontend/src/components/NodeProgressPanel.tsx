import { Card, Space, Typography } from 'antd';
import { CheckCircleFilled, LoadingOutlined } from '@ant-design/icons';
import type { NodeRun } from '../types';

function formatDuration(ms?: number): string {
  if (ms == null) return '';
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

/** 实时展示 LangGraph 各节点的运行过程（运行中 / 已完成）。 */
export default function NodeProgressPanel({
  runs,
  title = 'Agent 节点运行过程',
}: {
  runs: NodeRun[];
  title?: string;
}) {
  if (runs.length === 0) return null;

  return (
    <Card size="small" title={title}>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        {runs.map((r, i) => (
          <div
            key={`${r.node}-${i}`}
            style={{ display: 'flex', alignItems: 'center', gap: 10 }}
          >
            {r.status === 'running' ? (
              <LoadingOutlined spin style={{ color: '#1677ff', fontSize: 16 }} />
            ) : (
              <CheckCircleFilled style={{ color: '#52c41a', fontSize: 16 }} />
            )}
            <Typography.Text strong>{r.label}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {r.status === 'running'
                ? '运行中…'
                : [
                    formatDuration(r.durationMs),
                    r.totalTokens ? `${r.totalTokens.toLocaleString()} tokens` : '',
                  ]
                    .filter(Boolean)
                    .join(' · ')}
            </Typography.Text>
          </div>
        ))}
      </Space>
    </Card>
  );
}
