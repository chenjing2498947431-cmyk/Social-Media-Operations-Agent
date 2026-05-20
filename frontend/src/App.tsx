import { Layout, Typography } from 'antd';
import { Link, Route, Routes } from 'react-router-dom';
import CampaignListPage from './pages/CampaignListPage';
import CampaignDetailPage from './pages/CampaignDetailPage';

const { Header, Content } = Layout;

export default function App() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center' }}>
        <Link to="/">
          <Typography.Title level={4} style={{ color: '#fff', margin: 0 }}>
            金融自媒体运营 Agent
          </Typography.Title>
        </Link>
      </Header>
      <Content
        style={{ padding: 24, width: '100%', maxWidth: 1080, margin: '0 auto' }}
      >
        <Routes>
          <Route path="/" element={<CampaignListPage />} />
          <Route path="/campaigns/:id" element={<CampaignDetailPage />} />
        </Routes>
      </Content>
    </Layout>
  );
}
