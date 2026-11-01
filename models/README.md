# 模型目录

模型权重不随仓库分发（`.gitignore` 排除 `models/*.gguf`），但本机 `models/` 已实际装载权重。
SecOne 的 AI 能力由**本地引擎**提供：引擎 = llama.cpp `llama-server` + 一个 GGUF 权重，
两者都不绑定具体模型品牌，换模型只需替换权重并在设置页选用，不需要改代码或重新编译。

默认模型文件名为：

```text
models/XuanmuSec-v2-Q6_K.gguf
```

如果文件名或量化版本不同，请在 SecOne 的“模型与设置”页修改路径（写入 `config/app.yaml` 的 `engine:` 段），
无需重新编译程序。也可以点“扫描 models/ 中的 GGUF”，直接从下拉框选用本目录已存在的模型。

## 本机已装载的权重

上游 `guaidao2/XuanmuSec-2.6B`（玄幕安全团队，基座 LiquidAI/LFM2.5-2.6B，Apache-2.0 + LFM1.0 叠加）
提供的三种量化，本机已取回两种；`f16` 因磁盘余量不足暂未下载。

| 文件 | 大小（字节） | SHA256 | 说明 |
| --- | --- | --- | --- |
| `XuanmuSec-v2-Q6_K.gguf` | 2,221,614,464 | `bfaf475c740d699adea22bd3ff7cd2832fa6e09b7a1e642a1397e2ef1d458098` | 默认装载，低内存可用 |
| `XuanmuSec-v2-Q8_0.gguf` | 2,874,779,008 | `caecb0e9542b442ec2333910ed6e52393810a450fd5e00eac255e1fbf8257d38` | 上游推荐精度 |
| `XuanmuSec-v2-f16.gguf` | 5,403,157,888 | 未下载 | 无损，需约 5.1 GB 余量 |

两者 GGUF 头校验均为 `lfm2`、30 层、原生上下文 131072、含对话模板。重新获取：

```powershell
curl.exe -L -C - -o models\XuanmuSec-v2-Q8_0.gguf `
  https://www.modelscope.cn/models/guaidao2/XuanmuSec-2.6B/resolve/master/XuanmuSec-v2-Q8_0.gguf
```

切换权重只需改 `engine.gguf`（或在设置页选用），`engine.display_name` 保持中性的
“SecOne 本地引擎”，报告与界面不会把品牌名当成引擎身份。

## 已完成的实机验证

真实 GGUF + 真实 llama-server 的端到端链路已跑通，验证用模型为：

| 项 | 值 |
| --- | --- |
| 文件 | `verify-qwen2.5-0.5b-instruct-q4_k_m.gguf` |
| 大小 | 468.6 MB（491,400,032 字节） |
| 架构 | `qwen2`，24 层，原生上下文 32768，含 chat template |
| 来源 | `https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF` |
| 用途 | 仅用于验证推理链路，不作为默认模型分发 |

该文件同样被 `.gitignore` 的 `models/*.gguf` 排除。重新获取：

```powershell
curl.exe -L -o models\verify-qwen2.5-0.5b-instruct-q4_k_m.gguf `
  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

验证命令与覆盖范围：

```powershell
.\.python\python.exe scripts\verify_runtime.py      # 引擎启停、健康检查、对话、结构化输出
.\.python\python.exe scripts\verify_ai_pipeline.py  # 全流水线 + 防幻觉 + 报告导出
```

XuanmuSec-2.6B 权重已就位，`scripts/verify_runtime.py`（14/14）、
`scripts/verify_ai_pipeline.py`（15/15）与 `scripts/verify_ui_model_flow.py`（9/9）已用该权重
实机通过，覆盖加载、对话模板、连续生成和证据链路；解题准确率仍缺带标准答案的语料，
不能用“能回答”替代“能解对”。

## 放置与校验

1. 从上游发行方获取 GGUF 文件，确认下载完整。
2. 启动 SecOne，模型状态应显示“模型已就绪”，而不是“模型文件无效”。
3. 点击“启动本地引擎”；只有 `/health` 检查通过后才进入 AI 分析阶段。
4. 建议同时记录 SHA256 与文件大小，填入 `model.json`，便于发行校验。

`model.json` 是说明性清单，不是强校验；程序仍会读取 GGUF 文件头验证 magic 与版本，
并解析 `general.architecture`、`block_count`、`tokenizer.ggml.model` 与
`tokenizer.chat_template`。缺少对话模板时设置页会明确提示，而不是静默失败。

## 许可提醒

XuanmuSec-2.6B 涉及 XuanmuSec 自身的 Apache-2.0 声明与基座模型 LFM1.0
License 的叠加关系。分发权重前必须：

- 阅读并保留两套许可、版权与 NOTICE 文本；
- 确认量化/转换产物是否附带额外条款；
- 把上游许可文件放入 `licenses/`；
- 使用 `scripts/package_model.py` 生成带 `model.json`、许可文件与
  `SHA256SUMS.txt` 的独立模型包。

不要因为主程序以 Apache-2.0 发布就忽略基座模型条款。
