import { useCallback, useState } from 'react';
import type { NodeEvent, NodeRun, ToolCallEvent, ToolCallRun } from '../types';

/**
 * 把流式 SSE 的节点事件和工具调用事件累积成可展示的「节点运行过程」列表。
 *
 * - node phase=start：追加一条 running 节点记录
 * - node phase=end：把对应节点标记为 done，补上耗时 / token
 * - tool_call phase=start：在当前最后一个 running 节点下追加 running 工具调用
 * - tool_call phase=end：把对应工具调用标记为 done，补上结果数量
 */
export function useNodeRuns() {
  const [runs, setRuns] = useState<NodeRun[]>([]);

  const onNode = useCallback((evt: NodeEvent) => {
    setRuns((prev) => {
      if (evt.phase === 'start') {
        return [...prev, { node: evt.node, label: evt.label, status: 'running', toolCalls: [] }];
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

  const onToolCall = useCallback((evt: ToolCallEvent) => {
    setRuns((prev) => {
      // 找到最后一个 running 节点，工具调用挂在它下面
      const lastRunningIdx = [...prev].reduce(
        (found, r, i) => (r.status === 'running' ? i : found),
        -1,
      );
      if (lastRunningIdx < 0) return prev;

      const next = [...prev];
      const node = { ...next[lastRunningIdx] };
      const toolCalls: ToolCallRun[] = [...(node.toolCalls ?? [])];

      if (evt.phase === 'start') {
        toolCalls.push({ tool: evt.tool, label: evt.label, args: evt.args, status: 'running' });
      } else {
        for (let i = toolCalls.length - 1; i >= 0; i--) {
          if (toolCalls[i].tool === evt.tool && toolCalls[i].status === 'running') {
            toolCalls[i] = { ...toolCalls[i], status: 'done', resultCount: evt.result_count };
            break;
          }
        }
      }
      node.toolCalls = toolCalls;
      next[lastRunningIdx] = node;
      return next;
    });
  }, []);

  const reset = useCallback(() => setRuns([]), []);

  return { runs, onNode, onToolCall, reset };
}
