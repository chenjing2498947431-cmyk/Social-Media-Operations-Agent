import { useState } from 'react';
import {
  Button, Card, Col, Empty, Popconfirm, Row, Space, Statistic,
  Table, Tag, Tooltip, Typography, message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined, ClockCircleOutlined, DeleteOutlined,
  EnterOutlined, PlusOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useCampaigns, useDeleteCampaign } from '../hooks/campaigns';
import { STATUS_META } from '../status';
import CreateCampaignModal from '../components/CreateCampaignModal';
import type { Campaign } from '../types';

export default function CampaignListPage() {
  const { data, isLoading, isFetching, refetch } = useCampaigns();
  const deleteMutation = useDeleteCampaign();
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();

  const campaigns = data ?? [];
  const completedCount = campaigns.filter((c) => c.status === 'completed').length;
  const activeCount = campaigns.filter(
    (c) => c.status !== 'completed' && c.status !== 'failed',
  ).length;

  const handleDelete = async (id: string) => {
    try {
      await deleteMutation.mutateAsync(id);
      message.success('任务已删除');
    } catch {
      message.error('删除失败，请重试');
    }
  };

  const columns: ColumnsType<Campaign> = [
    {
      title: '任务标题',
      dataIndex: 'title',
      render: (v: string | null) =>
        v ? (
          <Typography.Text strong>{v}</Typography.Text>
        ) : (
          <Typography.Text type="secondary">未命名</Typography.Text>
        ),
    },
    {
      title: '背景摘要',
      dataIndex: 'context',
      ellipsis: true,
      render: (v: string) => (
        <Tooltip title={v} placement="topLeft">
          <Typography.Text type="secondary">{v}</Typography.Text>
        </Tooltip>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      align: 'center',
      render: (s: Campaign['status']) => (
        <Tag color={STATUS_META[s].color}>{STATUS_META[s].label}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 175,
      render: (v: string) => (
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          {new Date(v).toLocaleString('zh-CN')}
        </Typography.Text>
      ),
    },
    {
      title: '操作',
      width: 110,
      align: 'center',
      render: (_, row) => (
        <Space size={4}>
          <Tooltip title="进入任务">
            <Button
              type="primary"
              size="small"
              icon={<EnterOutlined />}
              onClick={() => navigate(`/campaigns/${row.id}`)}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除"
            description="此操作不可撤销，确定删除该任务吗？"
            onConfirm={() => handleDelete(row.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="删除任务">
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={deleteMutation.isPending && deleteMutation.variables === row.id}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 统计卡片 */}
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Card bordered={false} style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', borderRadius: 12 }}>
            <Statistic
              title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>总任务数</span>}
              value={campaigns.length}
              valueStyle={{ color: '#fff', fontWeight: 700 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card bordered={false} style={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', borderRadius: 12 }}>
            <Statistic
              title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>进行中</span>}
              value={activeCount}
              valueStyle={{ color: '#fff', fontWeight: 700 }}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card bordered={false} style={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)', borderRadius: 12 }}>
            <Statistic
              title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>已完成</span>}
              value={completedCount}
              valueStyle={{ color: '#fff', fontWeight: 700 }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* 列表区域 */}
      <Card
        bordered={false}
        style={{ borderRadius: 12, boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
        title={
          <Typography.Title level={5} style={{ margin: 0 }}>
            运营任务列表
          </Typography.Title>
        }
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              loading={isFetching}
              onClick={() => refetch()}
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setModalOpen(true)}
            >
              新建任务
            </Button>
          </Space>
        }
      >
        <Table<Campaign>
          rowKey="id"
          loading={isLoading}
          dataSource={campaigns}
          columns={columns}
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: <Empty description="暂无任务，点右上角「新建任务」开始" /> }}
          pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
          rowClassName={() => 'campaign-row'}
        />
      </Card>

      <CreateCampaignModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </Space>
  );
}
