# SecOne v1.0.0-rc1 发布说明

**版本名称：** SecOne v1.0.0-rc1 — Local Intelligence Workstation
**发布日期：** 2026-10-31
**定位：** 发布候选版（RC1），用于离线安装验收和真实模型实机验证。

## 1. 版本重点

RC1 不新增业务大模块，重点是把已有 MVP 收口为可验收的交付候选：

### Flag 引擎可信度

- 占位符（`flag{...}`、`flag{your_flag_here}` 等）不会进入有效结果。
- 单字节 XOR、Base64/Base32/Hex/URL/ROT13/ROT47 递归解码命中均可回溯。
- 每个候选保留来源文件、字节偏移、解码链、证据和置信度。
- 状态严格区分 `found` / `verified` / `candidate` / `none`；AI 提出的 Flag 只有逐字出现在证据中才会保留，且仍是候选。
- 新增 Flag 回归用例 17 个（含整段倒序与十六进制密文 XOR 回归），覆盖正例、负例和边界；标注语料基准含 19 个正例（直接、Base64/Base32/Hex/URL/ROT、双层编码、JS 注释、大写、长 Flag、XOR 二进制）与 13 个负例（占位符、格式文档、良性源码/文本/二进制），规则级 precision 1.0、recall 1.0。
- 标注语料只度量规则匹配与解码器，不代表真实模型解题准确率；真实模型解题准确率已做 60 条小样本实测（3/60 精确命中，5.0%），同语料确定性解码器 32/60，状态均为 PARTIAL，见下文。

### 本地模型诊断

- GGUF v2+ 元数据解析：架构、上下文长度、层数、Tokenizer、对话模板。
- `ModelInfo` 暴露 `chat_template_present`、`runtime_verified` 和诊断摘要。
- 设置页显示“缺少对话模板”“尚未完成实机推理验证”等明确状态，不伪造“已就绪”。
- 推理客户端增加 mock llama-server 协议测试：成功、HTTP 错误、超时、空内容、reasoning 回退、模型列表。

### 任务取消

- 工作台新增“取消”按钮：运行期可见可点，取消后按钮禁用并提示“正在取消分析任务”，完成后隐藏。
- 取消采用协作式 `threading.Event`：流水线在每个插件与进度检查点、模型请求等待期间都会响应。
- 取消后任务在 SQLite 中落库为 `cancelled`，界面解锁全部输入并保留已录入材料与文本框内容。
- 三层用例覆盖：`test_pipeline.py`（落库状态）、`test_ui_interaction.py`（按钮状态机与输入保留）、`test_llm_client.py`（中断进行中的 HTTP 等待）。

### 交付与许可

- 版本号统一到 `1.0.0-rc1` / `1.0.0.0`，`config/app.yaml`、启动日志、侧边栏和 EXE 元数据保持一致。
- `licenses/LICENSE-LFM1.0.txt`：LFM Open License v1.0 上游原文（10,574 字节，取自
  `https://huggingface.co/LiquidAI/LFM2-2.6B/blob/main/LICENSE`，逐字保存）。
- `licenses/LICENSE-XuanmuSec.txt`：Apache-2.0 许可选择声明，含叠加适用、商标、免责与出处小节。
- 模型打包脚本在缺少上述两份文件时拒绝生成模型包；新增两条更严格的随包门禁：
  `Apache-2.0.txt` 始终随包（`LICENSE-XuanmuSec.txt` 引用它），
  分发 llama.cpp 二进制时必须附带 `LICENSE-llama.cpp.txt`。
- 新增 `requirements.lock`、离线安装文档、测试报告和本发布说明。
- 新增便携 ZIP 包、Inno Setup 安装包与 SHA256 发布清单，三种分发形态均可独立核验。

### 实机推理验证（本轮新增）

- 取得 llama.cpp `b12017`（`0.8.0-dev`, commit `5047748f1`）Windows x64 CPU 版，
  装入 `runtime/`，`llama-server --version` 可执行。
- 取得 Qwen2.5-0.5B-Instruct `q4_k_m`（468.6 MB，`qwen2` 架构）作为链路验证模型。
- `scripts/verify_runtime.py`：14/14 通过——启动、`/health`、`/v1/models`、
  对话、`temperature=0` 结构化输出、日志落盘、停服释放端口。
- `scripts/verify_ai_pipeline.py`：15/15 通过——防幻觉三项、全流水线、
  DB 回读、三格式报告、工作区产物、引擎标识不含本机路径。
- `scripts/verify_ui_model_flow.py`：9/9 通过——在隔离沙箱内走
  “扫描发现 → 选中 → 保存 → 顶栏就绪 → 启动 → 推理”完整界面路径。
- `scripts/verify_model_accuracy.py`：使用真实 XuanmuSec-2.6B 跑 60 条标准答案 CTF 小样本
  （`benchmarks/ctf_accuracy_v4.json`：v3 的 24 条原样保留，新增 36 条程序化用例，覆盖
  Base64URL / Base32 无填充 / 大写冒号 Hex / Base85 / UTF-16LE / gzip / zlib / HTML 实体 /
  Unicode 转义 / quoted-printable / JS 字符串拼接 / 字符码列表 / 凯撒 +7 / 仿射密码 / XOR 0x13 等；
  独立解题提示词，max_tokens=512、temperature=0），766.08s 完成（24 条复用 v3 缓存），
  **3/60 精确命中（5.0%）**：命中为明文、URL 编码、源码注释，答案均以可读形式出现在材料中；
  15 条异常输出计入 `hallucinations`，包含 8 条格式合法但答案错误的 flag 与 8 条畸形 flag
  形态（嵌套重复、未闭合、乱码），其中 1 条同时具备两类。报告：
  `artifacts/model_accuracy_xuanmusec_v4.json`。
- 新增 `scripts/verify_decoder_accuracy.py`：同一 60 条材料只交给确定性 `FlagEngine`（不加载
  模型），**32/60 命中标准答案（53.3%）**，32/60 无多余候选，全语料仅 1 个多余候选项；本轮
  新增“整段倒序”与“十六进制密文单字节 XOR”两个解码族，报告
  `artifacts/decoder_coverage_v4.json`。两项均为内部小样本测量，不代表正式准确率。

### 部署依赖静态审计（本轮新增）

- 新增 `scripts/audit_bundle.py`：对 `dist/SecOne` 做可重复的静态依赖审计，覆盖主程序、内嵌解释器、
  Qt 平台插件（`PySide6/qt-plugins/platforms/qwindows.dll`）、Qt 核心库、VC++ 运行库、
  发布配置、四份许可、首次启动目录是否为空、模型权重是否误入程序目录、开发机路径泄漏。
- 本机实测 23 项检查全部通过（0 failed、0 warnings）：138 个文件、118,192,459 字节；
  `msvcp140*.dll` 与 `vcruntime140*.dll` 已随包，因此**不需要安装 VC++ Redistributable**；
  `data/`、`logs/`、`output/`、`workspace/` 为空；文本配置与 `SecOne.exe`、`python312.dll`、
  `pyside6.abi3.dll` 中均无 `X:\Users\<name>` 路径。
- 审计确认 `runtime/` 只含 `README.md`：程序包不分发 `llama-server.exe`，新装用户要使用 AI 推理
  必须额外安装模型资源包（包内 `runtime/` 与 `licenses/LICENSE-llama.cpp.txt` 会一并提供）。
  缺少模型或运行组件时界面显示未就绪，静态分析与 Flag 引擎不受影响。
- 该审计只证明文件构成正确，不能替代干净机器上的启动、渲染与写盘验证，因此
  “干净 Windows 离线安装”仍为 **BLOCKED**。

### 本轮修复

| 问题 | 处理 |
| --- | --- |
| llama-server 把 GGUF 绝对路径当作 model id 返回，泄漏进报告与界面 | `LLMClient._model_label` 归一为配置显示名；`LlamaServerManager.display_label()` 只从配置派生 |
| 配置的模型文件名不存在时界面死锁在“模型文件未安装” | 新增 `LlamaServerManager.discover_models()` 与设置页“扫描 models/ 中的 GGUF”下拉框 |
| 打包只带两份模型许可，未带其引用的 Apache 全文与 llama.cpp MIT | `ALWAYS_BUNDLED_LICENSES` / `RUNTIME_LICENSES` 门禁 |
| 打包测试把“许可缺失”写死，许可补齐后误报失败 | 改为 monkeypatch `REQUIRED_LICENSES`，并新增许可证真实性用例 |
| 工作台先 `resolve()` 再判断符号链接，导致符号链接拒绝分支永远不可达 | 调整 `add_paths` 顺序：先拒绝符号链接，再解析与去重；新增回归用例 |
| 取消事件在首个进度回调前触发时，任务状态停留在 `running` | 将首个进度检查点移入 `try` 块，确保 `PipelineCancelled` 被捕获并落库为 `cancelled` |

## 2. 产物与验证状态

| 交付项 | 状态 | 说明 |
| --- | --- | --- |
| 源码与测试 | DONE | 98 项测试通过，0 失败（含 9 项部署依赖静态审计与 4 项高 DPI 缩放用例） |
| Flag 引擎回归 | DONE | 占位符、XOR、编码、归档证据、AI 回查、标注语料，共 14 项；规则级 precision 1.0、recall 1.0 |
| GGUF 元数据解析 | DONE | 合成样本 + 真实 Qwen2.5 GGUF（`qwen2`/24 层/32768/含模板） |
| 推理客户端（mock） | DONE | 本地 HTTP mock 覆盖协议与错误路径及取消中断，10 项 |
| **实机 llama-server 链路** | **DONE** | `scripts/verify_runtime.py` 14/14 |
| **实机全流水线 + 防幻觉** | **DONE** | `scripts/verify_ai_pipeline.py` 15/15 |
| **界面配置→推理链路** | **DONE** | `scripts/verify_ui_model_flow.py` 9/9 |
| Nuitka standalone EXE | DONE | `dist/SecOne/SecOne.exe`；启动冒烟存活并记录 `SecOne 1.0.0-rc1 started`；EXE 元数据 1.0.0.0 |
| 部署依赖静态审计 | DONE | `scripts/audit_bundle.py` 对 `dist/SecOne` 23 项检查全通过：内嵌解释器、Qt 平台插件路径、VC++ 运行库、许可、首次启动目录、路径泄漏；`runtime/` 无 `llama-server.exe` 属设计（模型包提供） |
| 便携 ZIP 包 | DONE | `dist/packages/SecOne-1.0.0-rc1-portable-win64.zip`，46,901,540 字节，SHA256 `afd838ec…ba83a74`，138 个程序文件；解压后以最小 PATH 启动冒烟通过，首次启动创建 `data/`、`logs/` |
| SHA256 发布清单 | DONE | `dist/SHA256SUMS`，141 条（含便携 ZIP、安装包与模型资源包），已逐条重算核对无偏差 |
| 模型资源包 | DONE（内部验收） | `dist/packages/SecOne-model-XuanmuSec-2.6B-Q6_K.zip`，2,246,914,836 字节，SHA256 `eb77aecd…8e87`；62 条内部清单、ZIP 完整性通过；发布方 NOTICE 未补齐前不得对外正式分发 |
| Inno Setup 安装包 | DONE | `dist/installer/SecOne-1.0.0-rc1-setup.exe`，32,140,884 字节，SHA256 `49e380b7…46e09`，Inno Setup 6.7.4 编译；隔离目录静默安装 145 文件，安装后 EXE 与 `dist/SecOne` 字节一致；缺失模型提示按设计出现；卸载后 `data/`、`logs/` 保留；`scripts/verify_offline_install.ps1` 一键验收本机自检 9/9 通过 |
| 真实 XuanmuSec-2.6B GGUF 加载/对话/流水线 | DONE | `lfm2`、30 层、131072 上下文、含对话模板；`verify_runtime.py` 14/14、`verify_ai_pipeline.py` 15/15、`verify_ui_model_flow.py` 9/9 |
| 真实 XuanmuSec-2.6B 推理质量与解题准确率 | PARTIAL | 已用 60 条标准答案 CTF 小样本实测，3/60 精确命中（5.0%），15 条异常输出（含畸形 flag 与答案错误），多条在 512 token 上限内未收敛；样本仍属内部小样本，不代表正式准确率 |
| 确定性解码器覆盖率（同语料对照） | DONE（基线） | `scripts/verify_decoder_accuracy.py` 不加载模型：32/60 命中（53.3%），32/60 无多余候选，仅度量解码器能力 |
| 干净 Windows 离线安装 | BLOCKED | 无无 Python、无网络的干净测试机 |
| UI 交互自动化 | DONE | `test_ui_interaction.py` 11 项：素材接入/去重/符号链接拒绝、拖拽信号、忙碌锁定、进度、完成/失败渲染、报告导出、取消状态机 |
| 长任务取消 | DONE | 工作台取消按钮 + 协作式取消事件；取消后任务落库为 `cancelled`，输入保留，`test_pipeline.py` / `test_llm_client.py` / `test_ui_interaction.py` 三层覆盖 |
| 高 DPI 布局自动化 | DONE | `test_ui_dpi.py` 4 项：100%/125%/150%/200% 独立子进程启动，像素比匹配，1280×800/1600×900/1920×1080 抓图尺寸等于逻辑尺寸×比率，三页可光栅化，无零尺寸可见控件，五入口按钮不裁剪 |
| 真实鼠标拖拽与物理多显示器 | PARTIAL | 拖拽以 Qt 信号级用例覆盖；物理指针拖拽、真实多显示器与系统级缩放观感尚未人工验收 |
| Flag 规则级准确率 | DONE | 19 正例 / 13 负例标注语料，precision 1.0、recall 1.0；仅覆盖规则与解码器 |
| 真实模型解题准确率 | PARTIAL | `benchmarks/ctf_accuracy_v4.json` 60 条标准答案实测 3/60（5.0%）；内部小样本，不代表正式准确率，需扩大样本后复测 |

## 3. 已知问题

1. **XuanmuSec-2.6B 的解题能力尚无正式结论**：真实权重（`lfm2`，30 层，131072 上下文，
   Q6_K）已完成引擎、全流水线和界面链路实机验收（14/14、15/15、9/9）；60 条标准答案小样本
   只解出 3 条（明文、源码注释为答案字面可见，URL 百分号编码由模型自行解码），其余
   编码、古典密码、进制 ASCII、Base58/Base85、压缩、组合变换与 XOR 均未成功，并出现
   15 条畸形或答案错误的输出。样本仍属内部小样本，不能据此给出正式准确率；同语料确定性
   解码器命中 32/60，产品因此依赖确定性解码器与证据回查，模型输出必须回到证据中逐字命中
   才保留为 `candidate`。
2. **安装包未在干净环境验收**：`dist/installer/SecOne-1.0.0-rc1-setup.exe` 已由 Inno Setup 6.7.4 构建，并在本机隔离目录完成安装/启动/卸载验证；但尚未在无 Python、无网络的干净 Windows 上实测（与“干净 Windows 离线安装”同属 BLOCKED）。
3. **模型许可仍缺发布方 NOTICE**：`LICENSE-XuanmuSec.txt` 只记录 Apache-2.0 许可选择；正式分发权重前需取得发布方的版权/NOTICE 文件。
4. **RAR 不支持**：仅保留原文件并提示，需要外部组件。
5. **部分 UI 交互未做自动化**：素材接入、拖拽信号、忙碌锁定、进度、完成/失败渲染与取消状态机已由 11 项用例覆盖；高 DPI 布局已由 4 项子进程用例自动回归（100%/125%/150%/200% × 三种分辨率）；真实鼠标拖拽、真实多显示器与系统级缩放观感仍需人工验收。
6. **“已验证”状态不会自动升级**：当前没有自动验证器，`verified` 预留给人工或后续流程。

## 3.1 模型包分发注意

- 分发模型包时 `licenses/` 应同时包含 `LICENSE-XuanmuSec.txt`、`Apache-2.0.txt`
  与 `LICENSE-LFM1.0.txt`；打包脚本会强制检查，缺一即终止。
- 若同时分发 `runtime/` 中的 llama.cpp 二进制，必须附带 `LICENSE-llama.cpp.txt`（MIT），
  并注明构建来源与版本（当前为 `b12017` / `0.8.0-dev` / commit `5047748f1`）。
- 模型与运行组件体积较大（XuanmuSec-2.6B Q6_K 权重 2.07 GiB，`runtime/` 53 个文件约 40 MB），
  应作为独立下载项。
- 已实测生成 `dist/packages/SecOne-model-XuanmuSec-2.6B-Q6_K/` 与同名 ZIP：包含权重、
  `runtime/`、四份许可/说明文本、`THIRD_PARTY_NOTICES.md`、`INSTALL.txt` 与 62 条
  `SHA256SUMS.txt`。发布方 NOTICE 补齐前，该包仅可用于内部验收，不得对外正式分发。

## 4. 升级与数据保护

- 任务库、工作区、证据与报告位于 `data/`、`workspace/`、`output/`；安装脚本将这些目录标记为卸载不删除。
- 升级覆盖程序文件和 `config/` 默认配置；用户配置保存在运行期配置中，升级前建议备份。
- 模型与 runtime 始终独立于主程序包，升级主程序不会触碰模型资源。

## 5. 验收建议

1. 将 `dist/installer/SecOne-1.0.0-rc1-setup.exe` 复制到无 Python、无网络的干净 Windows，执行 `docs/OFFLINE_INSTALL.md` 的验收清单。
2. 用真实 GGUF 与固定版本 llama-server 完成启动、问答、连续生成和异常恢复测试，并记录到测试报告。
3. 用带标准答案的 CTF 样本做 Flag 准确率回归，区分“规则命中”和“模型建议”。
4. 人工回归真实鼠标拖拽、多显示器、长路径与中文文件名（100%/125%/150%/200% 缩放已自动化）。
