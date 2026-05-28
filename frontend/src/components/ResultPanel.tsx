import { Card, Empty, Image, Space, Tag, Typography } from 'antd';
import { RedEnvelopeOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import type { Campaign } from '../types';

export default function ResultPanel({ campaign }: { campaign: Campaign }) {
  const state = campaign.workflow_state?.state;
  const article = state?.draft_article ?? '';
  const images = state?.generated_images ?? [];
  const prompts = state?.image_prompts ?? [];
  const xhsCopy = state?.xhs_copy ?? '';

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="最终文案">
        <div className="markdown-body">
          <ReactMarkdown>{article}</ReactMarkdown>
        </div>
      </Card>

      <Card title={`配图（共 ${images.length} 张）`}>
        {images.length === 0 ? (
          <Empty description="暂无配图" />
        ) : (
          <Image.PreviewGroup>
            <Space size="large" wrap>
              {images.map((url, i) => (
                <Space key={url} direction="vertical" style={{ width: 240 }}>
                  <Image
                    src={url}
                    width={240}
                    height={240}
                    style={{ objectFit: 'cover', borderRadius: 8 }}
                  />
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {prompts[i] ?? ''}
                  </Typography.Text>
                </Space>
              ))}
            </Space>
          </Image.PreviewGroup>
        )}
      </Card>

      <Card
        title={
          <Space>
            <RedEnvelopeOutlined style={{ color: '#ff2442' }} />
            <span>小红书文案</span>
            <Tag color="red">可直接发布</Tag>
          </Space>
        }
      >
        {xhsCopy ? (
          <Typography.Paragraph
            copyable={{ text: xhsCopy, tooltips: ['复制文案', '已复制！'] }}
            style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, marginBottom: 0 }}
          >
            {xhsCopy}
          </Typography.Paragraph>
        ) : (
          <Empty description="文案生成中，请刷新页面…" />
        )}
      </Card>
    </Space>
  );
}
