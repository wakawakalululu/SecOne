# SecOne v1.0.0-rc1 测试报告

- 报告日期：2026-10-31
- 测试环境：Windows 10 x64（10.0.19044），Python 3.12.10（嵌入式 `.python`），PySide6 6.9.3，pytest 9.2.0，Nuitka 4.3.3，llama.cpp `b12017`（`0.8.0-dev`, commit `5047748f1`）
- 测试命令：`.\.python\python.exe -m pytest tests -o addopts="" -q`
- 测试结果：**98 passed，0 failed**（2026-10-31 复跑，92.33s）
- 实机验收（Qwen2.5-0.5B 验证模型）：`verify_runtime.py` **14/14**（10.9s）、`verify_ai_pipeline.py` **15/15**（153.4s）、`verify_ui_model_flow.py` **9/9**
- 实机验收（XuanmuSec-2.6B `Q6_K`）：`verify_runtime.py` **14/14**（19.4s，端口 18111）、`verify_ai_pipeline.py` **15/15**（61.9s，端口 18112）、`verify_ui_model_flow.py` **9/9**（端口 18105）；报告见 `artifacts/runtime_verification_xuanmusec.json` 与 `artifacts/ai_pipeline_verification_xuanmusec.json`

## 1. 测试分布

| 测试文件 | 用例数 | 覆盖内容 |
| --- | ---: | --- |
| `tests/test_flag_benchmark.py` | 7 | 占位符负例、XOR 正例、编码链、压缩包内证据、AI 线索回查、状态排序、19 正例/13 负例标注语料精确率与召回率 |
| `tests/test_flag_engine.py` | 10 | 直接匹配、Base64/Hex/ROT 递归解码、占位符过滤、去重与置信度、整段倒序、十六进制密文单字节 XOR、纯 Hex 无误报 |
| `tests/test_ingest.py` | 5 | 材料接入、ZIP 路径穿越、条目/体积限制、去重、归档来源标记 |
| `tests/test_llm_client.py` | 10 | 模拟 llama-server 的健康检查、问答成功、reasoning 回退、多段内容、HTTP 500、空内容、超时、服务未启动、模型列表、取消中断等待 |
| `tests/test_model_info.py` | 3 | 模型状态、GGUF 头校验、引擎描述 |
| `tests/test_model_label.py` | 8 | 模型标识显示、绝对路径脱敏、空标识回退、未知量化省略 |
| `tests/test_model_metadata.py` | 4 | GGUF v2+ 元数据解析、架构/上下文/对话模板、截断文件、缺失模板提示、GGUF v1 说明 |
| `tests/test_package_model.py` | 11 | GGUF 头校验、SHA256 清单、模型许可强制、Apache/LFM 许可随包、运行组件许可、模型发现、非拉丁 display_name 的回退命名 |
| `tests/test_model_accuracy.py` | 9 | 标准答案基准离线回归：严格提取去重、畸形 flag 识别（含未闭合/嵌套重复输出与 runaway 嵌套）、生产语料结构、重复 ID 拒绝、非 flag 答案拒绝、缓存须匹配模型/prompt 版本/token 预算、v4 语料结构与生成器输出一致 |
| `tests/test_bundle_audit.py` | 9 | 部署依赖静态审计：必需组件缺失、VC++ 运行库缺失、配置与 EXE 中的开发机路径、首次启动目录被写入、模型权重误入程序目录、按模型包布局要求 `runtime/llama-server.exe`、bundle 根目录缺失 |
| `tests/test_pipeline.py` | 4 | 无 AI 端到端流水线、报告输出、结果结构、取消事件落库为 `cancelled` |
| `tests/test_ui_interaction.py` | 11 | 素材接入/去重/符号链接拒绝、拖拽信号、移除与清空、空输入守卫、忙碌锁定、进度、完成渲染、报告导出、失败恢复、取消任务状态机 |
| `tests/test_ui_smoke.py` | 3 | 主窗口结果渲染与页面构造冒烟 |
| `tests/test_ui_dpi.py` | 4 | 100%/125%/150%/200% 缩放下独立子进程构建主窗口：设备像素比、抓图尺寸与逻辑尺寸一致、三页均可光栅化、无零尺寸可见控件、五入口按钮文字不被裁剪 |

## 2. 验收项对应结果

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 字面量 `flag{...}` 占位符不得成为有效 Flag | DONE | `test_flag_benchmark.py` 负例通过 |
| 已知 XOR 样本恢复正确 Flag | DONE | `test_flag_benchmark.py` XOR 正例通过 |
| 编码/压缩样本定位原始证据（来源、偏移、解码链） | DONE | Flag benchmark 与 ingest 用例通过 |
| 无证据的模型输出不得标记为已发现 | DONE | AI 线索回查用例通过，状态保持 `candidate` |
| 误报/漏报可重复回归 | DONE | 13 个 Flag 相关用例全部通过 |
| 规则级标注语料精确率/召回率（19 正例 / 13 负例） | DONE | `test_labeled_rule_corpus_precision_and_recall`：precision 1.0、recall 1.0、无负例误报；仅度量规则与解码器，不代表模型准确率 |
| 确定性解码器在 60 条标准答案语料上的覆盖率 | DONE（基线） | `scripts/verify_decoder_accuracy.py`（不加载模型）：32/60 命中标准答案（53.3%），32/60 无多余候选，全语料仅 1 个多余候选项；报告 `artifacts/decoder_coverage_v4.json`；仅度量解码器，不代表模型准确率 |
| GGUF 元数据、架构、Tokenizer、对话模板解析 | DONE | `test_model_metadata.py` 4 项通过 |
| 推理客户端成功/错误/超时/空内容路径 | DONE | `test_llm_client.py` 10 项通过（本地 mock HTTP 服务） |
| 真实 XuanmuSec GGUF 加载与连续生成 | DONE | XuanmuSec-2.6B `Q6_K`（`lfm2`，30 层，131072 上下文，2.07 GiB）实机通过：`verify_runtime.py` 14/14（19.4s）、`verify_ai_pipeline.py` 15/15（61.9s）、`verify_ui_model_flow.py` 9/9；覆盖对话模板、结构化输出、停服与连续生成 |
| 真实模型推理质量/CTF 准确率回归 | PARTIAL | 已建立 60 条标准答案语料（v4）并用真实 XuanmuSec GGUF 实测：**3/60 精确命中（5.0%）**，命中为明文、源码注释（答案字面出现在材料中）与 URL 百分号编码（模型自行解码）；15 条异常输出（畸形 flag 形态与格式合法但答案错误），多条用例在 512 token 上限内未收敛；766.08s 完成（24 条复用 v3 缓存）。样本仍属内部小样本，不代表正式准确率。见第 3 节 |
| 标准答案基准 harness 的解析与缓存逻辑 | DONE | `test_model_accuracy.py` 9 项通过（离线，不加载模型）：严格提取去重、畸形 flag 识别（含未闭合/嵌套重复输出）、语料结构、重复 ID 拒绝、非 flag 答案拒绝、缓存须匹配模型/prompt 版本/token 预算 |
| llama-server 真实启动/健康/对话/停服 | DONE | `verify_runtime.py` 14/14 |
| 全流水线接入真实模型并导出报告 | DONE | `verify_ai_pipeline.py` 15/15 |
| 界面配置模型→保存→启动→推理 | DONE | `verify_ui_model_flow.py` 9/9 |
| 模型 id 不泄漏本机路径 | DONE | `test_model_label.py` 8 项；实机 `engine='SecOne 本地引擎 · Q6_K · 2.1 GB'` |
| 模型包许可完整性（Apache 全文 + LFM + llama.cpp MIT） | DONE | `test_package_model.py` 10 项；实测包含 5 个许可/说明文件 |
| 版本号一致性（配置、界面、日志、EXE 元数据） | DONE | 配置与界面统一为 `1.0.0-rc1`，EXE 元数据 `1.0.0.0`；启动日志实测输出 `SecOne 1.0.0-rc1 started` |
| Nuitka EXE 实际构建 | DONE | 构建 exit 0，产物、启动冒烟与哈希见第 3 节 |
| Inno Setup 安装包构建 | DONE | Inno Setup 6.7.4 编译 exit 0，产物、隔离安装/启动/卸载验证见第 3 节 |
| 干净 Windows 离线安装 | BLOCKED | 无干净虚拟机/物理机；本机 `Containers-DisposableClientVM` 为 Disabled、`WindowsSandbox.exe` 不存在，启用需管理员权限与重启 |
| 工作台交互：素材接入/去重/符号链接拒绝、拖拽信号、忙碌锁定、进度、完成与失败渲染、报告导出 | DONE | `test_ui_interaction.py` 11 项通过（offscreen Qt，信号级 StubWorker） |
| 长任务取消：按钮状态机、输入保留、任务落库 `cancelled` | DONE | UI 取消用例 + `test_pipeline.py` 取消落库 + `test_llm_client.py` 取消中断等待 |
| 高 DPI 与多分辨率布局 | DONE（offscreen） | `test_ui_dpi.py` 4 项通过：100%/125%/150%/200% 各自独立进程启动，`devicePixelRatioF()` 与 `QT_SCALE_FACTOR` 一致，1280×800/1600×900/1920×1080 三种尺寸下抓图尺寸等于逻辑尺寸×比率、三页均可光栅化且颜色非单色、无零尺寸可见控件、五入口按钮宽度不小于文字所需宽度 |
| 真实鼠标拖拽（物理指针、系统 DPI 缩放） | PARTIAL | 拖拽事件以 Qt 信号级用例覆盖；物理鼠标在多显示器/系统缩放下的人工验收尚未执行 |

## 3. 构建与启动验证

- Nuitka standalone 构建成功（exit 0）：`dist/SecOne/SecOne.exe` 为 32,806,912 字节（SHA256 `babfc00a72129c62c7a2c5d34642e2f1a5913a43ac787ad9f0cb773ce083c5fb`）；便携目录共 138 个文件、118,192,459 字节（约 112.7 MiB）；EXE 元数据为 `FileVersion=1.0.0.0`、`ProductVersion=1.0.0.0`、`ProductName=SecOne`。
- 构建命令：`powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1 -SkipTests`，日志见 `nuitka-build.log`。
- 启动冒烟：直接运行 `dist/SecOne/SecOne.exe`，进程持续运行 15 秒未退出；首次启动创建 `data/history.db`（含 WAL/SHM）与 `logs/secone.log`，日志记录 `SecOne 1.0.0-rc1 started`，随后由测试脚本正常终止。冒烟产生的任务库与日志已移出交付目录，发布包保持首次启动状态。
- 便携目录包含 `python312.dll` 与 PySide6 运行时，不依赖开发机的系统 Python。
- 便携包：`dist/packages/SecOne-1.0.0-rc1-portable-win64.zip`，46,901,540 字节（SHA256 `afd838ec78b365f7ecfb0510c9fda045d1acda80fe88bf764bc66855cba83a74`），含 138 个程序文件，`data/`、`logs/` 为空目录，首次启动才会写入运行期数据。
- 校验清单：`dist/SHA256SUMS` 覆盖 138 个便携目录文件、便携 ZIP、安装包与模型资源包，共 141 条；已逐条重算 SHA256 并核对，无缺失、无不一致。
- 发布包解压冒烟：将 ZIP 解压到临时目录（验证后已清理），把 `PATH` 缩减为 `C:\Windows\system32;C:\Windows` 并清除 `PYTHONHOME`/`PYTHONPATH` 后启动 `SecOne.exe`（`QT_QPA_PLATFORM=offscreen`），进程 12 秒未退出，首次启动自动创建 `data/history.db` 与 `logs/secone.log`，日志输出 `SecOne 1.0.0-rc1 started`。该验证证明发布包不依赖开发机 Python，但仍在同一台构建机上执行，不等同于干净 Windows 验收。
- 安装包：`dist/installer/SecOne-1.0.0-rc1-setup.exe` 由 Inno Setup 6.7.4 编译（exit 0，44.1s），32,140,884 字节（SHA256 `49e380b78edef48ed5f9a2245b1e79c75f265c5ff6e383a4ab59c84b7dd46e09`）。在临时隔离目录（验证后已清理）静默安装：145 个文件落盘，安装后的 `SecOne.exe` 与 `dist/SecOne/SecOne.exe` 字节一致（32,806,912 字节，SHA256 `babfc00a…c5fb`）；以最小 `PATH` 启动并记录 `SecOne 1.0.0-rc1 started`；模型缺失时按设计弹出提示。静默卸载后 145 个程序文件与注册项全部移除，`data/`（含用户任务标记）与 `logs/` 按 `uninsneveruninstall` 保留。未在无 Python、无网络的干净 Windows 上实测，仍属 BLOCKED。
- 安装包桌面快捷方式链路：`/VERYSILENT /MERGETASKS=desktopicon "/DIR=<临时目录>"` 安装 exit 0，`SecOne.exe` 为 32,806,912 字节，桌面生成 `SecOne.lnk`（1,304 B）；解析出的 `TARGET` 指向临时安装目录下的 `SecOne.exe`、`WORKDIR` 为安装目录。通过 `.lnk` 启动（offscreen）12 秒后进程仍存活，首次启动创建 `data/history.db` 与 `logs/secone.log`，日志记录 `SecOne 1.0.0-rc1 started`。静默卸载 exit 0 后快捷方式被移除，`data/`、`logs/`、`models/`、`output/`、`runtime/`、`workspace/` 按 `uninsneveruninstall` 保留；临时安装目录与快捷方式均已清理，未触碰用户既有文件。
- 一键离线安装验收脚本：新增 `scripts/verify_offline_install.ps1`，把安装→快捷方式→首启→可选模型包→卸载链路收敛为一条命令。本机自检（非干净机）9 个步骤全部 DONE：安装包 SHA256 校验、`PATH` 无 Python 前置检查、静默安装（141 个文件，递归计数）、载荷哈希与 `dist/SecOne/SecOne.exe` 一致、卸载注册项存在、`SecOne.lnk` 的 `TARGET`/`WORKDIR` 正确、最小 `PATH` 经快捷方式启动 12s 存活并生成 `data/history.db` 与 `logs/secone.log`、静默卸载后程序文件/快捷方式/注册项移除且 `data/`、`logs/` 保留。报告：`artifacts/offline_install_report.json`（`scope=acceptance-harness-run`）。该运行只证明脚本可用；干净机验收仍需以 `-CleanMachine` 实跑。
- 真实模型实机验收（XuanmuSec-2.6B `Q6_K`）：`models/XuanmuSec-v2-Q6_K.gguf`（2,221,614,464 字节，SHA256 `bfaf475c…8098`，`lfm2`，30 层，131072 上下文，gpt2 分词器，含对话模板）。`verify_runtime.py --gguf models\XuanmuSec-v2-Q6_K.gguf` 14/14 通过（19.4s，端口 18111）；`verify_ai_pipeline.py --gguf models\XuanmuSec-v2-Q6_K.gguf` 15/15 通过（61.9s，端口 18112），防幻觉拒绝编造 Flag、真实材料 Flag 保持 `candidate`，9 个材料 / 7 个 Flag / 10 条发现，任务完成且报告落盘；`verify_ui_model_flow.py --gguf models\XuanmuSec-v2-Q6_K.gguf` 9/9 通过（端口 18105）。以上证明加载、模板、推理与证据链路，不代表解题准确率。
- 标准答案 CTF 回归（真实模型 + 确定性解码器，PARTIAL）：`benchmarks/ctf_accuracy_v4.json` 共 60 条 / 41 类，v3 的 24 条原样保留，新增 36 条程序化用例（Base64URL、Base32 无填充、大写冒号 Hex、Base85、UTF-16LE、gzip/zlib、HTML 实体、Unicode 转义、quoted-printable、JS 字符串拼接、字符码列表、凯撒 +7、仿射密码、XOR 0x13 等，答案均不以字面形式出现在材料中）。`scripts/verify_model_accuracy.py --port 18106` 使用真实 XuanmuSec-2.6B（独立解题提示词，max_tokens=512、temperature=0），766.08s 完成（24 条复用 v3 缓存），结果 **3/60 精确命中（5.0%）**：命中为明文、源码注释与 URL 百分号编码。15 条异常输出计入 `hallucinations`：8 条包含格式合法但答案错误的 flag（如 `flag{Hello World! This is the flag}`），8 条包含畸形 flag 形态（嵌套重复 `flag{flag{…`、未闭合 `Flag{HeXTo…`、乱码），其中 1 条同时具备两类；多条在 512 token 处仍未收敛。报告：`artifacts/model_accuracy_xuanmusec_v4.json`。同语料用 `scripts/verify_decoder_accuracy.py` 只跑 `FlagEngine`（不加载模型）：**32/60 命中标准答案（53.3%）**，32/60 无多余候选，全语料仅 1 个多余候选项；本轮新增“整段倒序”与“十六进制密文单字节 XOR”两个解码族，报告 `artifacts/decoder_coverage_v4.json`。说明：两项均为内部小样本测量，不代表正式准确率；对比说明机械解码应由确定性引擎负责，模型输出必须回到证据中逐字命中才保留为 `candidate`。
- 模型包：`scripts/package_model.py` 的 GGUF 头校验、SHA256 清单、许可文件强制检查与
  运行组件许可已由 11 个用例覆盖。用真实 XuanmuSec-2.6B `Q6_K` 权重 + `runtime/` 实测生成
  `dist/packages/SecOne-model-XuanmuSec-2.6B-Q6_K/`（`models/` 权重、`runtime/` 53 个文件、
  `licenses/` 含 `LICENSE-XuanmuSec.txt`、`Apache-2.0.txt`、`LICENSE-LFM1.0.txt`、
  `LICENSE-llama.cpp.txt` 与 `licenses/README.md`，`THIRD_PARTY_NOTICES.md`、`INSTALL.txt`），
  62 条 SHA256 清单，ZIP 完整性校验通过。
  许可状态仍为 PARTIAL：`LICENSE-XuanmuSec.txt` 只记录发布方的 Apache-2.0 许可选择，
  发布方自己的版权/NOTICE 声明尚未取得，正式对外分发前需补齐。

### 3.1 部署依赖静态审计（`dist/SecOne`）

干净 Windows 机器不可得，因此补做一层可重复的静态依赖审计：`scripts/audit_bundle.py`
（默认检查 `dist/SecOne`，`--expect-runtime` 用于模型包布局）。本机实测 23 项检查全通过
（0 failed、0 warnings），输出如下（2026-10-31）：

| 检查项 | 实测结果 |
| --- | --- |
| 程序目录规模 | 138 个文件，118,192,459 字节 |
| 主程序 | `SecOne.exe` 32,806,912 字节 |
| 内嵌解释器 | `python312.dll` 6,945,272 字节、`python3.dll` 70,376 字节 |
| Qt 平台插件 | `PySide6/qt-plugins/platforms/qwindows.dll` 925,920 字节（Nuitka 布局，不是 `PySide6/plugins/`） |
| Qt 核心库 | `qt6core.dll` / `qt6gui.dll` / `qt6widgets.dll` 均在目录根 |
| VC++ 运行库 | `msvcp140.dll` 557,728、`msvcp140_1.dll` 35,952、`msvcp140_2.dll` 280,200、`vcruntime140.dll` 120,400、`vcruntime140_1.dll` 49,776 字节；**无需安装 VC++ Redistributable**。`ucrtbase.dll` 未随包，属 Windows 10/11 系统组件 |
| 发布配置 | `config/app.yaml` 1,042 字节、`config/prompts.yaml` 1,561 字节 |
| 许可文件 | `LICENSE-XuanmuSec.txt`、`LICENSE-LFM1.0.txt`、`Apache-2.0.txt`、`LICENSE-llama.cpp.txt` 均在 `licenses/` |
| 首次启动状态 | `data/`、`logs/`、`output/`、`workspace/` 均为空目录 |
| 模型权重 | `models/` 仅 `README.md` 与 `model.json`，无 `.gguf`（符合“模型独立分包”设计） |
| llama.cpp 运行组件 | **`runtime/` 仅含 `README.md`（2,000 字节），未随程序包分发** |
| 开发机路径泄漏 | 文本文件（`.yaml`/`.json`/`.md`/`.txt` 等）与 `SecOne.exe`、`python312.dll`、`pyside6.abi3.dll` 中均未出现 `X:\Users\<name>` 形态路径 |

结论与边界：

- 程序包自身不依赖系统 Python、不依赖系统 VC++ Redistributable，Qt 平台插件路径正确，发布前状态干净，未泄漏开发机路径。
- 该审计**只覆盖静态文件构成**，不能证明在干净机器上能成功启动、渲染界面或写盘，因此“干净 Windows 离线验收”仍为 **BLOCKED**。
- `runtime/` 不含 `llama-server.exe` 是已知设计（`docs/OFFLINE_INSTALL.md` 第 3、4 节）：新装用户要使用 AI 推理，必须额外安装模型资源包，其中的 `runtime/` 与 `licenses/LICENSE-llama.cpp.txt` 会一并分发。缺少模型或 runtime 时界面应显示“模型未安装 / 尚未完成实机推理验证”，静态分析与 Flag 引擎不受影响。


## 4. 未覆盖与限制

- 未安装 `pytest-timeout`，超时路径通过客户端自身的 `timeout` 参数验证，而非用例级超时插件。
- 标注语料基准只度量规则匹配与解码器行为（19 正例 / 13 负例，precision 1.0、recall 1.0），不代表真实模型解题准确率。
- 模型解题准确率已做一次内部小样本实测（60 条，3/60 精确命中，见第 3 节），但样本量仍不足以形成正式准确率结论，故状态为 PARTIAL 而非 DONE。
- 基准 harness 的严格/宽松 flag 提取、语料校验与缓存键（模型 + prompt 版本 + token 预算）已由 `test_model_accuracy.py` 7 项离线用例覆盖，但真实模型本身的解题能力仍需更大规模标注语料验证；确定性解码器覆盖率已用同一 60 条语料测得 32/60（`artifacts/decoder_coverage_v4.json`），可重复但仅代表解码器能力。
- UI 交互测试在 offscreen Qt 下使用信号级 `StubWorker`，覆盖素材接入、拖拽信号、忙碌锁定、进度、完成/失败渲染、报告导出与取消任务状态机。高 DPI 布局已由 `test_ui_dpi.py` 在 100%/125%/150%/200% 与三种分辨率下自动回归（真实 Qt 缩放与光栅化，非物理显示器）；物理鼠标拖拽、真实多显示器与系统级缩放的观感仍需人工验收。
- 取消链路由三层用例覆盖：`test_pipeline.py` 验证取消后任务落库为 `cancelled`，`test_ui_interaction.py` 验证按钮状态机与输入保留，`test_llm_client.py` 验证取消事件能中断进行中的 HTTP 等待。
- 模拟 llama-server 只用于协议与错误路径回归；LFM2 架构、对话模板与真实生成已由 XuanmuSec-2.6B 实机验收覆盖，但该验收只证明链路可用，不构成生成质量或解题准确率结论。
- 未做性能、内存与长时间稳定性测试。
- 未在无 Python、无网络的干净 Windows 上执行安装验收：本机无干净虚拟机/物理机，Windows Sandbox 功能（`Containers-DisposableClientVM`）处于 Disabled 且 `WindowsSandbox.exe` 不存在，启用需管理员权限与重启，本轮未执行。已用 `scripts/audit_bundle.py` 做静态依赖审计（23 项全通过，见 3.1 节），但静态审计不能替代真实启动、渲染与写盘验证。

## 5. 复现

```powershell
.\.python\python.exe -m pytest tests -q
.\.python\python.exe -m pytest tests --collect-only -q
.\.python\python.exe scripts\audit_bundle.py
.\.python\python.exe scripts\verify_model_accuracy.py --port 18106 --no-reuse
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1 -SkipTests
powershell -Command "Compress-Archive -Path dist\SecOne -DestinationPath dist\packages\SecOne-1.0.0-rc1-portable-win64.zip -Force"
```
