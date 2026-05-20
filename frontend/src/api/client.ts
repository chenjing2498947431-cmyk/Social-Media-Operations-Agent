import axios from 'axios';

// baseURL 走相对路径 /api/v1，开发期由 Vite proxy 转发到 backend_api。
// timeout 设得很大：选题/写稿/出图都会同步等待真实大模型返回。
export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 200000,
});

/** 把后端 / 网络错误转换为可读的错误信息。 */
export function toErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (err.code === 'ECONNABORTED') return '请求超时，大模型生成时间过长，请稍后重试。';
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}
