import { Card, Empty, Image, Space, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import type { Campaign } from '../types';

export default function ResultPanel({ campaign }: { campaign: Campaign }) {
  const state = campaign.workflow_state?.state;
  const article = state?.draft_article ?? '';
  const images = state?.generated_images ?? [];
  const prompts = state?.image_prompts ?? [];

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
    </Space>
  );
}
