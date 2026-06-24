import { Alert, Form, Input, Modal, Space } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useCreateCampaign } from '../hooks/campaigns';
import { toErrorMessage } from '../api/client';

interface Props {
  open: boolean;
  onClose: () => void;
}

interface FormValues {
  title?: string;
  context: string;
}

export default function CreateCampaignModal({ open, onClose }: Props) {
  const [form] = Form.useForm<FormValues>();
  const navigate = useNavigate();
  const mutation = useCreateCampaign();

  const handleOk = async () => {
    const values = await form.validateFields();
    const campaign = await mutation.mutateAsync({
      context: values.context,
      title: values.title || undefined,
    });
    form.resetFields();
    mutation.reset();
    onClose();
    navigate(`/campaigns/${campaign.id}`);
  };

  const handleCancel = () => {
    if (mutation.isPending) return;
    form.resetFields();
    mutation.reset();
    onClose();
  };

  return (
    <Modal
      title="新建营销编排任务"
      open={open}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={mutation.isPending}
      okText="创建并生成营销选题"
      cancelText="取消"
      maskClosable={false}
      destroyOnHidden
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Form form={form} layout="vertical" disabled={mutation.isPending}>
          <Form.Item name="title" label="任务标题（可选）">
            <Input placeholder="例：5月20日新品营销选题" maxLength={60} />
          </Form.Item>
          <Form.Item
            name="context"
            label="营销背景 / 当日热点"
            rules={[{ required: true, message: '请输入背景信息' }]}
          >
            <Input.TextArea
              rows={4}
              placeholder="例：新品即将发布，目标客群关注性价比与服务体验，近期社媒讨论热度上升…"
            />
          </Form.Item>
        </Form>
        {mutation.isPending && (
          <Alert
            type="info"
            showIcon
            message="正在调用大模型生成备选营销选题，约 10-20 秒，请勿关闭…"
          />
        )}
        {mutation.isError && (
          <Alert
            type="error"
            showIcon
            message="创建失败"
            description={toErrorMessage(mutation.error)}
          />
        )}
      </Space>
    </Modal>
  );
}
