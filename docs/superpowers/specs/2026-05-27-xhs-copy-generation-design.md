# 小红书文案生成 设计文档

**日期：** 2026-05-27  
**状态：** 已批准，待实现

---

## 目标

在 LangGraph 工作流的最终阶段（图片生成之后）自动生成一篇小红书风格的发布文案，与已生成的配图一起写入最终 state，供运营人员直接复制发布，无需人工审核中断。

---

## 背景

当前工作流在 `generate_images` 后直接进入 `END`。`extract_image_content` 节点已生成 3 张配图的卡片文字（≤40 字/张），但没有完整的小红书帖子正文（标题 + 段落 + emoji + 话题标签）。

---

## 设计

### 工作流变更

```
... → extract_image_content → generate_images → generate_xhs_copy → END
```

仅在末尾追加一个节点，不修改任何已有节点或条件边。

### 新增字段

`AgentState` 新增：
```python
xhs_copy: Optional[str]   # 小红书帖子全文（标题 + 正文 + 话题标签）
```

### Prompt（xhs_copy_writer）

```yaml
xhs_copy_writer:
  system: |
    你是小红书爆款金融内容创作者，擅长把专业分析转化为普通投资者爱看的帖子。
    格式要求：
    - 第一行：抓眼球的标题（带 emoji，不超过 20 字）
    - 空一行后写正文：分 3-5 段，每段 2-4 句，语气轻松有温度
    - 适量使用 emoji（每段 1-2 个，不滥用）
    - 最后一行：5-8 个话题标签，# 开头，空格分隔
    - 总字数 250-450 字
  user_template: |
    选题：{selected_topic}

    参考长文（提炼精华，勿照搬原文）：
    {draft_article}

    请直接输出小红书帖子正文。
```

### 节点实现

- 文件：`ai_service/graph/nodes/image_node.py`（追加在现有两个节点之后）
- 调用：`llm.generate_xhs_copy(selected_topic, draft_article)`
- 返回：`{"xhs_copy": copy_text, "status": "completed"}`
- 错误处理：`@track_node` 装饰器统一捕获异常，写 `status: "failed"`

### LLMClient 新增方法

```python
async def generate_xhs_copy(self, selected_topic: str, draft_article: str) -> str:
    return await self._complete(
        "xhs_copy_writer",
        selected_topic=selected_topic,
        draft_article=draft_article,
    )
```

### 指标

`ai_service/core/metrics.py` 的 `NODE_LABELS` 新增：
```python
"generate_xhs_copy": "小红书文案生成",
```

---

## API 变化

无新 HTTP 端点。`GET /{thread_id}/state` 响应的 `state` 字段中新增 `xhs_copy` 字符串，`stage` 流转不变（最终仍为 `completed`）。

---

## 测试策略

| 文件 | 内容 |
|------|------|
| `tests/test_state.py` | 验证 `xhs_copy` 在 `AgentState.__annotations__` 中 |
| `tests/test_llm_client_xhs.py` | `generate_xhs_copy()` 正确拼接 prompt 并返回字符串 |
| `tests/test_xhs_node.py` | 节点正常写入 state；`selected_topic`/`draft_article` 缺失时传空字符串不报错 |

---

## 不在此次范围内

- 小红书文案的人工审核/重写循环（用户明确选择无需审核）
- 多版本文案生成
- 自动发布到小红书平台
