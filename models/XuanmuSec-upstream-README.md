# XuanmuSec-2.6B

> 玄幕安全团队出品的端侧安全 Agent 模型，基于 LFM2.5-2.6B 经过 CPT + SFT 双阶段微调，专精 CTF 竞赛解题与渗透测试分析。

**当前版本：v2.0** — 修复了 v1.0 的代码格式问题，优化了 SFT 数据质量，CTF 能力显著提升。

## 模型简介

XuanmuSec-2.6B 是在 [LiquidAI/LFM2.5-2.6B](https://www.modelscope.cn/models/LiquidAI/LFM2.5-2.6B) 基座上，通过两阶段微调打造的安全领域垂直模型：

1. **CPT（Continued Pre-Training）**：使用 CTF-SKILL + hack-skills 共 215 篇高质量安全知识文本（269 万字符），注入漏洞原理、攻击链、利用技术等安全领域知识
2. **SFT（Supervised Fine-Tuning）**：使用精选的 921 条 CTF 真实比赛 writeup（7 类均衡分布），训练 CTF 解题思维和结构化输出能力

### 核心特性

- **深度安全知识**：覆盖 Web/Pwn/Crypto/Reverse/Misc/Blockchain/Cloud 七大安全方向
- **CTF 解题能力**：经过真实比赛 writeup 训练，掌握常见漏洞分析与利用思路
- **Agent 兼容**：保留 LFM2.5 的 tool calling 能力，可接入 Agent 框架作为安全工具节点
- **主动行动**：CPT 训练使模型从"被动分析"转为"主动尝试利用"，更适合 Agent 场景
- **端侧部署**：2.6B 参数量，GGUF 格式，笔记本即可运行，适合线下比赛无网络环境

### v2.0 更新

- 修复了 v1.0 的代码格式问题（代码块换行丢失）
- 修复了"只思考不输出"问题
- SFT 数据从 15,430 条精简为 921 条精选数据（LIMA 方法论）
- 7 类均衡分布，每类约 150 条高质量样本
- CPT 知识与 SFT 风格联合训练，解题深度提升

## 训练详情

### 阶段一：CPT（安全知识注入）

| 项目 | 详情 |
|------|------|
| 基座模型 | LiquidAI/LFM2.5-2.6B |
| 训练方法 | QLoRA (4-bit NF4) |
| LoRA rank | 16, alpha 16 |
| Target modules | q_proj, k_proj, v_proj, out_proj, in_proj, w1, w2, w3 |
| CPT 数据 | CTF-SKILL (57 篇) + hack-skills (158 篇) |
| 数据总量 | 269 万字符，215 个安全知识文件 |
| 训练轮数 | 5 epochs，选用 epoch-4 |
| 学习率 | 5e-5 |

### 阶段二：SFT（解题风格训练）

| 项目 | 详情 |
|------|------|
| 基座模型 | CPT 合并后的 LFM2.5-2.6B |
| 训练方法 | QLoRA (4-bit NF4) |
| LoRA rank | 16, alpha 16 |
| SFT 数据 | 921 条精选 CTFtime writeup |
| 数据量 | 921 条（LIMA 方法论：贵精不贵多） |
| 训练轮数 | 1 epoch |
| 学习率 | 2e-4 |
| 数据特点 | 7 类均衡分布、100% 带 thinking 分析、0% 格式错误 |

## 数据来源

### CPT 数据

| 来源 | 文件数 | 内容 |
|------|--------|------|
| [CTF-SKILL](https://github.com/guaidao2/CTF-SKILL) | 57 | Web/Pwn/Crypto/Reverse/Misc/Blockchain/Cloud 攻击知识 |
| [hack-skills](https://github.com/yaklang/hack-skills) | 158 | 14 个安全领域的渗透测试知识 + 高阶利用技术 |

### SFT 数据

| 来源 | 数量 | 内容 |
|------|------|------|
| [CTFtime](https://hf-mirror.com/datasets/justinwangx/CTFtime) | 921（精选） | DEFCON/Plaid CTF/Google CTF/Hack.lu 等比赛真实 writeup |

## 快速使用

### Python (Transformers)

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "guaidao2/XuanmuSec-2.6B"
tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_id, device_map="auto", trust_remote_code=True, dtype="bfloat16"
)

messages = [
    {"role": "system", "content": "You are an expert CTF solver and pentest agent with tools. Solve challenges step by step with exploit code."},
    {"role": "user", "content": "Solve this CTF web challenge: ..."},
]

text = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
input_ids = tokenizer(text, return_tensors="pt").input_ids.to(model.device)

output = model.generate(input_ids=input_ids, max_new_tokens=2048, temperature=0.1, top_k=50)
response = tokenizer.decode(output[0][input_ids.shape[-1]:], skip_special_tokens=True)
print(response)
```

### LM Studio / llama.cpp (GGUF)

本仓库提供三种量化版本：

| 文件 | 大小 | 精度 | 适用场景 |
|------|------|------|----------|
| `XuanmuSec-v2-f16.gguf` | 5.1 GB | 无损 | 最高质量 |
| `XuanmuSec-v2-Q8_0.gguf` | 2.7 GB | 几乎无损 | **推荐** |
| `XuanmuSec-v2-Q6_K.gguf` | 2.1 GB | 轻微损失 | 低内存设备 |

1. 下载对应版本的 `.gguf` 文件
2. 在 LM Studio 中导入模型文件
3. 使用以下 System Prompt：

```
You are an expert CTF solver and pentest agent with tools.
You have access to: nmap, sqlmap, curl, python3, gdb, pwntools.
Solve challenges step by step. Always provide working exploit code.
```

## 推荐 System Prompt

### CTF 解题模式

```
You are an expert CTF solver. Solve challenges across Web, Pwn, Crypto, Reverse Engineering, Forensics, and Misc categories. Provide detailed, step-by-step solutions with code examples.
```

### 渗透测试 Agent 模式

```
You are an expert CTF solver and pentest agent with tools.
You have access to: nmap, sqlmap, curl, python3, gdb, pwntools.
Use tools to verify and exploit. Solve challenges step by step.
```

### 安全编码审计模式

```
You are a security code reviewer. Analyze the given code for vulnerabilities, explain the attack vectors, and provide fix recommendations with secure code examples.
```

## 模型能力

### 三模型对比（Base vs v1.0 vs v2.0）

以下对比基于相同测试题目，在 LFM2.5-2.6B 基座、LFM2.5-2.6B-For-CTF（v1.0 纯 SFT）、XuanmuSec-2.6B v2.0（CPT+SFT 联合训练）三种配置下测试得出。

| 测试维度 | Base (LFM2.5-2.6B) | LFM2.5-2.6B-For-CTF (v1.0) | XuanmuSec v2.0 (CPT+SFT) |
|---------|-------------------|--------|---------------------|
| **路径遍历绕过** | 纠结不出答案 | 自信给出答案（但有误） | ✅ 分析准确，有完整步骤 |
| **堆利用 (glibc 2.27)** | 不认识 tcache/unsorted bin | 泛泛而谈 | ✅ 识别 tcache list head、unsorted bin 交互 |
| **RSA close primes** | 不确定攻击方法 | ✅ 识别 Fermat 分解 | ✅ 完整推导 p = (√(4n+k²) - k) / 2 |
| **SQLi + XFF 绕过** | 没提到 XFF | 提到但分析浅 | ✅ 完整攻击链推理 |
| **输出格式** | 通用助手风格 | 结构化 CTF 分析 | ✅ 结构化 + thinking + 正文 |
| **代码格式** | 正常 | ❌ 代码块格式损坏 | ✅ 格式规范 |
| **正文输出** | 正常 | ❌ 有时只思考不输出 | ✅ 始终有正文 |
| **tool_call** | 幻觉调用（无工具时） | 无 tool_call | Agent 模式下正确调用工具 |

### 关键结论

1. **SFT 带来最大的质变**：从"不知道怎么回答"到"学会 CTF 选手的思考框架"
2. **CPT 带来深度提升**：从"泛泛而谈"到"识别具体技术细节"（tcache list head、Fermat 推导等）
3. **v2.0 修复了 v1.0 的格式问题**：干净数据训练消除了代码格式损坏和"只思考不输出"
4. **通用能力保留**：全程 LoRA 微调，基座权重未修改，通用能力不受影响

### v2.0 已验证能力

- SQL 注入分析与利用（绕过 WAF、UNION 注入、盲注、嵌套绕过）
- 常见 Web 漏洞识别（XSS、SSRF、文件包含、反序列化、XFF 绕过）
- 二进制漏洞分析（tcache 攻击、unsorted bin、堆利用思路）
- 密码学攻击（RSA Fermat/差值分解、对称密码分析、Miller-Rabin 素性检验）
- 渗透测试方法论（侦察→漏洞评估→利用→报告）
- Agent 行为（接入框架时能正确调用工具执行命令）
- 结构化输出（分析→思路→payload→验证，代码格式规范）

### 待提升能力

- Crypto 高级攻击（格密码、椭圆曲线）需要更多训练数据
- 复杂多步推理题可能需要更大模型
- 取证和逆向方向覆盖较少

## 模型架构

LFM2.5-2.6B 采用 Liquid AI 的混合架构：

- **30 层**：22 个卷积块 (ShortConv) + 8 个 GQA 注意力块
- **隐藏维度**：2048
- **注意力头**：32 (GQA: 8 key-value heads)
- **上下文窗口**：131,072 tokens
- **词表大小**：128,000

## 后续计划

- [ ] 补充密码学专项数据（RSA/AES/格密码攻击）
- [ ] 补充逆向工程与取证数据
- [ ] 更多轮次 CPT 增强领域知识
- [ ] DPO/GRPO 对齐训练

## 许可证

本模型基于 [Apache License 2.0](./LICENSE) 开源发布。

基座模型 [LiquidAI/LFM2.5-2.6B](https://www.modelscope.cn/models/LiquidAI/LFM2.5-2.6B) 遵循 [LFM1.0 License](https://www.modelscope.cn/models/LiquidAI/LFM2.5-2.6B)，使用时请遵守其条款。

## 关于我们

**玄幕安全团队**（XuanMu Security Team）是一个专注于网络安全研究与 CTF 竞赛的安全团队。本项目是我们在 AI + 安全交叉领域的探索之一——打造可在离线环境下运行的端侧安全助手模型。

- ModelScope：[guaidao2](https://www.modelscope.cn/guaidao2)
- GitHub：[guaidao2/CTF-SKILL](https://github.com/guaidao2/CTF-SKILL)

## 致谢

- [Liquid AI](https://www.liquid.ai/) - LFM2.5 基座模型
- [CTFtime](https://ctftime.org/) - CTF 比赛与 writeup 社区
- [guaidao2/CTF-SKILL](https://github.com/guaidao2/CTF-SKILL) - 玄幕安全团队 CTF 知识库
- [yaklang/hack-skills](https://github.com/yaklang/hack-skills) - 渗透测试 Agent 知识库
- [justinwangx/CTFtime](https://hf-mirror.com/datasets/justinwangx/CTFtime) - 训练数据集
- HuggingFace Transformers, PEFT, TRL - 训练框架
