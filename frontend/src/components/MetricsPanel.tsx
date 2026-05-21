import { Card, Col, Row, Statistic, Table, Tag, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { ClockCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { NodeMetric } from '../types';

/** 毫秒 -> 人类可读耗时。 */
function formatDuration(ms: number): string {
  if (!ms || ms < 0) return '0 ms';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${Math.round(ms)} ms`;
}

export default function MetricsPanel({ metrics }: { metrics: NodeMetric[] }) {
  if (!metrics || metrics.length === 0) return null;

  const totalDuration = metrics.reduce((s, m) => s + (m.duration_ms || 0), 0);
  const totalInput = metrics.reduce((s, m) => s + (m.input_tokens || 0), 0);
  const totalOutput = metrics.reduce((s, m) => s + (m.output_tokens || 0), 0);
  const totalTokens = totalInput + totalOutput;
  const totalCalls = metrics.reduce((s, m) => s + (m.llm_calls || 0), 0);

  const columns: TableColumnsType<NodeMetric> = [
    {
      title: '流程节点',
      dataIndex: 'label',
      key: 'label',
      render: (label: string, _record, index) => `${index + 1}. ${label}`,
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      align: 'right',
      render: (ms: number) => formatDuration(ms),
    },
    {
      title: '输入 Token',
      dataIndex: 'input_tokens',
      key: 'input_tokens',
      align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '输出 Token',
      dataIndex: 'output_tokens',
      key: 'output_tokens',
      align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '总 Token',
      dataIndex: 'total_tokens',
      key: 'total_tokens',
      align: 'right',
      render: (v: number) => <strong>{v.toLocaleString()}</strong>,
    },
    {
      title: 'LLM 调用',
      dataIndex: 'llm_calls',
      key: 'llm_calls',
      align: 'right',
      render: (v: number) =>
        v > 0 ? v : <Typography.Text type="secondary">—</Typography.Text>,
    },
  ];

  return (
    <Card
      title={
        <span>
          流程统计 · 耗时与 Token 用量{' '}
          <Tag color="geekblue">{metrics.length} 个节点</Tag>
        </span>
      }
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Statistic
            title="总耗时"
            value={formatDuration(totalDuration)}
            prefix={<ClockCircleOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="总 Token"
            value={totalTokens}
            prefix={<ThunderboltOutlined />}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="输入 / 输出 Token"
            value={`${totalInput.toLocaleString()} / ${totalOutput.toLocaleString()}`}
          />
        </Col>
        <Col span={6}>
          <Statistic title="LLM 调用次数" value={totalCalls} />
        </Col>
      </Row>

      <Table<NodeMetric>
        size="small"
        rowKey={(record) => `${record.node}-${record.started_at}`}
        columns={columns}
        dataSource={metrics}
        pagination={false}
        summary={() => (
          <Table.Summary fixed>
            <Table.Summary.Row>
              <Table.Summary.Cell index={0}>
                <strong>合计</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={1} align="right">
                <strong>{formatDuration(totalDuration)}</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={2} align="right">
                <strong>{totalInput.toLocaleString()}</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={3} align="right">
                <strong>{totalOutput.toLocaleString()}</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={4} align="right">
                <strong>{totalTokens.toLocaleString()}</strong>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={5} align="right">
                <strong>{totalCalls}</strong>
              </Table.Summary.Cell>
            </Table.Summary.Row>
          </Table.Summary>
        )}
      />

      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        注：仅统计 AI 计算节点的耗时与 token；人工选题 / 审核的等待时间不计入。
        配图生成为文生图调用，无 token 消耗。
      </Typography.Text>
    </Card>
  );
}
