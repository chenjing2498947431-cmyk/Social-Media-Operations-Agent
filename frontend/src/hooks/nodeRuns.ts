import { useCallback, useState } from 'react';
import type { NodeEvent, NodeRun } from '../types';

/**
 * 把流式 SSE 的节点事件累积成可展示的「节点运行过程」列表。
 *
 * - phase=start：追加一条 running 记录
 * - phase=end：把对应节点最近一条 running 记录标记为 done，并补上耗时 / token
 */
export function useNodeRuns() {
  const [runs, setRuns] = useState<NodeRun[]>([]);

  const onNode = useCallback((evt: NodeEvent) => {
    setRuns((prev) => {
      if (evt.phase === 'start') {
        return [...prev, { node: evt.node, label: evt.label, status: 'running' }];
      }
      const next = [...prev];
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].node === evt.node && next[i].status === 'running') {
          next[i] = {
            ...next[i],
            status: 'done',
            durationMs: evt.metric?.duration_ms,
            totalTokens: evt.metric?.total_tokens,
          };
          break;
        }
      }
      return next;
    });
  }, []);

  const reset = useCallback(() => setRuns([]), []);

  return { runs, onNode, reset };
}
