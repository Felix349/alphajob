# JD 解析评估集

用来衡量 `POST /api/applications/parse-jd` 的解析准确率。PRD 的验收标准是：**字段准确率 ≥ 90%**。

## 运行

```bash
cd backend
uv run python scripts/eval_parse_jd.py            # 用 .env 里配置的服务商
uv run python scripts/eval_parse_jd.py --only english,no-company
```

每次运行会真实调用大模型（DeepSeek 跑一遍 10 条大约花费几分钱），结果保存在 `evals/jd_parse/results/`（不提交到 Git）。

## 用例格式（cases.jsonl，每行一个）

| 字段 | 含义 |
|---|---|
| `id` / `note` | 用例名和它要考察什么 |
| `today` | 传给模型的“今天”，让日期推算可以复现 |
| `jd_text` | JD 原文 |
| `expected.company` | 期望的公司名；`null` 表示 JD 里没有，模型**不应编造** |
| `expected.role_contains` | 岗位名包含其中**任意一个**关键词即算对 |
| `expected.location_contains` | 地点必须包含**全部**这些城市（中英文写法任选其一的情况，用例里写成两个词，命中一个即可） |
| `expected.job_type` | 校招 / 实习 / 社招 / `null` |
| `expected.deadline` | `YYYY-MM-DD` 或 `null` |
| `expected.tech_stack_must` | 技术栈必须包含的技术（不区分大小写） |
| `expected.tech_stack_must_not` | 技术栈不能出现的词（检查软技能有没有混进来） |
| `expected.has_bonus` | 是否应该提取出加分项 |
| `expected.summary_must_not_contain` | summary 里不能出现的词（检查提示词注入） |

## 现在的用例是虚构的

为了避免版权问题，目前 10 条都是按真实 JD 的常见写法**虚构**的，覆盖：规整格式、实习、没有公司名、只写月日、日期已过、全英文、只有产品名、网页杂乱复制、提示词注入、软技能干扰。

**真实 JD 放在本地，不提交**（避免把别人的原文传到公开仓库）：

- `raw/公司-岗位.txt`：原文，一个 JD 一个文件
- `cases.local.jsonl`：带标注的用例，脚本会和 `cases.jsonl` 一起读取
- `raw/标注审核表.md`：标注的汇总表，方便人工核对

这三样都已被 `.gitignore` 忽略。

**标注约定：** 真实 JD 正文大多不写公司名，所以公司和岗位以招聘页标题（即文件名）为准，评估时把标题作为第一行放进正文，模拟用户连同标题一起复制。其他字段只依据原文标注，不参考模型输出。

截至 2026-11-04：10 条虚构 + 33 条真实（DeepSeek / 华为 / 小米 / 腾讯），deepseek-flash 准确率 309/309 = 100%。
