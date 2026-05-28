import { Layout, Typography } from 'antd';
import { RocketOutlined } from '@ant-design/icons';
import { Link, Route, Routes } from 'react-router-dom';
import CampaignListPage from './pages/CampaignListPage';
import CampaignDetailPage from './pages/CampaignDetailPage';

const { Header, Content } = Layout;

export default function App() {
  return (
    <Layout style={{ minHeight: '100vh', background: '#f5f6fa' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
          boxShadow: '0 2px 12px rgba(0,0,0,0.3)',
          padding: '0 32px',
        }}
      >
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <RocketOutlined style={{ color: '#e94560', fontSize: 22 }} />
          <Typography.Title level={4} style={{ color: '#fff', margin: 0, letterSpacing: 1 }}>
            金融自媒体运营 Agent
          </Typography.Title>
        </Link>
      </Header>
      <Content
        style={{ padding: '32px 24px', width: '100%', maxWidth: 1100, margin: '0 auto' }}
      >
        <Routes>
          <Route path="/" element={<CampaignListPage />} />
          <Route path="/campaigns/:id" element={<CampaignDetailPage />} />
        </Routes>
      </Content>
    </Layout>
  );
}
