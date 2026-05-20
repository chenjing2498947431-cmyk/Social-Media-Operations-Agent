import { useState } from 'react';
import { Button, Card, Empty, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useCampaigns } from '../hooks/campaigns';
import { STATUS_META } from '../status';
import CreateCampaignModal from '../components/CreateCampaignModal';
import type { Campaign } from '../types';

export default function CampaignListPage() {
  const { data, isLoading, isFetching, refetch } = useCampaigns();
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();

  const columns: ColumnsType<Campaign> = [
    {
      title: '标题',
      dataIndex: 'title',
      render: (v: string | null) =>
        v || <Typography.Text type="secondary">未命名</Typography.Text>,
    },
    { title: '背景', dataIndex: 'context', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (s: Campaign['status']) => (
        <Tag color={STATUS_META[s].color}>{STATUS_META[s].label}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 190,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      width: 90,
      render: (_, row) => (
        <Button type="link" onClick={() => navigate(`/campaigns/${row.id}`)}>
          进入
        </Button>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          运营任务
        </Typography.Title>
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
      </div>
      <Card>
        <Table<Campaign>
          rowKey="id"
          loading={isLoading}
          dataSource={data ?? []}
          columns={columns}
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: <Empty description="还没有任务，点右上角「新建任务」" /> }}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
        />
      </Card>
      <CreateCampaignModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </Space>
  );
}
