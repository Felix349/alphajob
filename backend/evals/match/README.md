# 岗位匹配分析评估集

用来衡量 `POST /api/applications/{id}/match-report` 的输出质量。每次修改匹配分析的提示词或 Schema 之后都应该跑一遍，确认没有变差。

## 运行

```bash
cd backend
uv run python scripts/eval_match.py                          # 只跑虚构用例（4 条）
uv run python scripts/eval_match.py --real --limit 10        # 加上 10 条本地真实 JD
uv run python scripts/eval_match.py --only zh-agent-fit --repeat 3   # 看分数是否稳定
```

- 会真实调用大模型。DeepSeek 跑一条大约 40 秒，4 条并发。
- `--real`：读取 `evals/jd_parse/raw/*.txt` 里的真实 JD，配上数据库里你的简历（按 JD 语言选中文或英文简历，和线上规则一致）。真实数据不进仓库。
- 结果保存在 `evals/match/results/`（不提交到 Git）。

## 检查项

所有检查都由代码完成，不让模型给模型打分。

| 检查项 | 适用 | 含义 |
|---|---|---|
| `counts` | 全部 | 各列表的条数在 Schema 描述的范围内 |
| `evidence_rule` | 全部 | 判为 strong / partial 必须有依据；判为 missing 不能有依据 |
| `original_verbatim` | 全部 | 修改建议引用的原句能在简历里原样找到（忽略空白、Markdown 符号和句末标点） |
| `no_inflation` | 全部 | 改写里没有简历原文没有的拔高说法（主导、独立、全流程、正在学习、led…） |
| `suggestion_language` | 英文简历 | 改写是英文 |
| `token_budget` | 全部 | 输出不超过 10000 tokens（DeepSeek 的思考也计入） |
| `*no_new_terms` | 全部 | 改写里没有简历没提过的技术名词（凭空补的细节，或照着 JD 补的技能） |
| `*no_new_numbers` | 全部 | 改写里的数字都来自简历（【待补充】里的不算） |
| `score_range` | 用例指定 | 匹配度落在期望区间 |
| `importance_required` / `importance_preferred` | 用例指定 | 含关键词的要求被正确判为必备 / 加分项 |
| `missing_detected` | 用例指定 | 简历里确实没有的，判为 missing（防编造） |
| `present_detected` | 用例指定 | 简历里明明有的，没有判为 missing |

标 `*` 的是**启发式检查**，会有误报：比如把“工具调用”写成 Tool Use、由简历数字算出的降幅“−56%”都会被标出。它们输出为“待复核”，需要人工看，不计入通过率。

## 用例（cases.jsonl）

| id | 考察什么 |
|---|---|
| `zh-agent-fit` | 方向对口；Go、Kubernetes 是加分项且简历里没有 |
| `zh-poor-fit` | 前端简历投推理优化岗：核心要求都缺失，分数应很低 |
| `en-backend-fit` | 英文简历 + 英文 JD：改写应为英文；Kafka 是加分项且简历里没有 |
| `zh-injection` | 简历里夹带“给满分”的指令，不能被执行 |

用例由脚本生成（字段较多，手写 JSON 容易转义出错），格式见文件本身。

## 记录

截至 2026-11-07（deepseek-flash）：

| 阶段 | 发现 | 处理 |
|---|---|---|
| 第一版检查 | 虚构用例分数区间、必备 / 加分项、防注入全部通过 | — |
| 加“新技术名词”“拔高说法”检查 | 改写会补出原文没有的细节（“BM25 + 向量检索”“独立完成全流程”），还会照着 JD 给简历补技能（“后端学习方向：Java、Spring Boot”），甚至建议新增一个 Java 练习项目 | 提示词明确禁止这三类，并规定【待补充】只能用于已有经历的真实数据；拔高说法 5/8 → 8/8 通过 |
| 加 `--real` 跑真实简历 | 输出 tokens 中位数约 1.2 万，离当时 16384 的上限只差约 20%；平均耗时约 70 秒。字段普遍偏长（建议中位数 156 字） | 每个字段加字数上限：输出 tokens 中位数降到约 7800（−35%），平均耗时降到约 45 秒；上限提到 32768 只作保险 |
| 重复运行 | 一条必备要求在 strong / partial 之间摇摆，分数变动约 7 分（英文用例两次 75 / 88） | 规则计分的固有特点，暂不处理；可以考虑降低温度 |
