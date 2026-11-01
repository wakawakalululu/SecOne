# SecOne v1.0.0 RC1 — 工程交付报告

- 版本目标：SecOne v1.0.0 RC1 — XuanmuSec Offline Security Workstation
- 报告日期：2026-10-31
- 报告角色：Team Lead（集成、验收与文档收口）
- 测试环境：Windows 10 x64 10.0.19044，嵌入式 Python 3.12.10（`.python/python.exe`），PySide6 6.9.3，pytest 9.2.0，Nuitka 4.3.3，llama.cpp `b12017`（`0.8.0-dev`, commit `5047748f1`），Inno Setup 6.7.4
- 真实模型：`models/XuanmuSec-v2-Q6_K.gguf`（`lfm2`，30 层，131072 上下文，gpt2 分词器，含对话模板，2,221,614,464 字节，SHA256 `bfaf475c…8098`）
- 状态标记：DONE = 已实现并通过验收；PARTIAL = 已实现但未完全验证；BLOCKED = 受资源/环境限制无法完成；FAILED = 已实测但未通过。本文档不把 PARTIAL/BLOCKED 记为 DONE。

## 1. 本轮总体完成情况

| 验收目标 | 优先级 | 状态 | 结论 |
| --- | --- | --- | --- |
| Flag 引擎误报/漏报修复与回归体系 | P0 | DONE | 占位符误报、XOR 漏检、倒序/编码链遗漏均已修复并有自动化用例；98 项测试全绿 |
| 真实 GGUF 模型接入与实机推理 | P0 | DONE | 真实 XuanmuSec-2.6B `Q6_K` 完成启动/健康/对话/连续生成/停服与全流水线实机验收 |
| 真实模型解题准确性回归 | P0（新增要求） | PARTIAL | 60 条标准答案语料实测 3/60（5.0%），15 条异常输出；内部小样本，不构成正式准确率 |
| 确定性解码器覆盖率（同语料对照） | P0（新增要求） | DONE（基线） | `FlagEngine` 单独 32/60（53.3%），32/60 无多余候选 |
| Nuitka EXE 与 Inno Setup 安装包实际构建 | P0 | DONE | 真实产物已构建、启动冒烟、隔离目录安装/卸载验证通过 |
| 干净 Windows 离线安装验收 | P1 | BLOCKED | 无无 Python、无网络的干净测试机；以解压冒烟 + 23 项静态依赖审计做补偿验证 |
| 完整发布材料 | P1 | DONE（许可 PARTIAL） | 便携 ZIP、安装包、模型资源包、141 条 SHA256 清单、测试报告、发布说明、离线安装文档、第三方许可清单 |

一句话结论：**可在授权的 Windows 10/11 离线机器上安装并运行，确定性分析链路已实测可用，本地模型的解题能力仍不足以作为答案来源，必须依赖确定性解码器与证据回查。**

## 2. 各 Agent 目标完成情况

| 角色 | 目标 | 结果 |
| --- | --- | --- |
| Agent A（Flag 引擎） | 占位符误报、XOR 漏检、编码链、证据回溯、评分与状态、防幻觉 | DONE：`src/secone/core/flag_engine.py` 递归解码（深度 3、节点预算 800、结果上限 80），19 正例/13 负例标注语料 precision 1.0 / recall 1.0；AI 候选必须逐字命中材料否则拒绝 |
| Agent B（模型与推理） | GGUF 元数据、llama-server 生命周期、OpenAI 兼容客户端、超时/取消/诊断、Mock 测试 | DONE：`src/secone/llm/server.py`、`src/secone/llm/client.py`；实机 14/14、15/15、9/9；10 项 mock 用例覆盖错误路径与取消 |
| Agent C（桌面端） | 工作台、拖拽、进度、取消、结果与证据渲染、设置/历史/诊断、布局 | DONE（交互与高 DPI DONE，真实鼠标 PARTIAL）：`src/secone/ui/**`；11 项交互用例 + 3 项冒烟用例 + 4 项高 DPI 缩放用例通过 |
| Agent D（打包交付） | EXE、安装器、模型分包、依赖审计、SHA256、离线文档、卸载数据保护 | DONE（干净机验收 BLOCKED）：`packaging/build_exe.ps1`、`packaging/SecOne.iss`、`scripts/package_model.py`、`scripts/audit_bundle.py` |
| Team Lead | 接口统一、并行协调、冲突处理、全量测试、文档与最终验收 | DONE：全部模块接口一致，无跨模块冲突，98 项测试 0 失败，文档与产物哈希已对齐 |

## 3. 修改和新增的文件清单

应用代码：

- `src/secone/core/flag_engine.py` — 整段倒序解码、Hex 字节单字节 XOR 解码族、占位符过滤、去重与状态排序、AI 候选证据回查
- `src/secone/core/ingest.py`、`workspace.py`、`fileio.py`、`classify.py` — 安全摄入、路径穿越/符号链接拒绝、解包限额、去重、题型识别
- `src/secone/core/pipeline.py`、`report.py` — 一键流水线、协作式取消、结构化报告与导出
- `src/secone/core/plugins/{base,crypto,forensics,web_audit,binary,misc}.py` — Crypto / 取证 / Web / Pwn / Reverse / Misc 静态分析
- `src/secone/llm/{server,client}.py` — llama-server 管理器、健康检查、显示名归一、客户端超时与取消
- `src/secone/ui/{main_window,worker,theme,widgets,context,app}.py`、`src/secone/ui/pages/{workbench,settings,history}.py` — 工作台、模型设置与扫描、诊断、任务历史
- `src/secone/{config,paths,db,domain}.py`、`src/secone/__main__.py`、`run_secone.py` — 配置、路径、SQLite、领域模型、启动入口

测试（1 个 conftest + 14 个测试文件，98 用例）：

- `tests/{conftest,test_flag_engine,test_flag_benchmark,test_ingest,test_pipeline,test_llm_client,test_model_info,test_model_label,test_model_metadata,test_model_accuracy,test_package_model,test_bundle_audit,test_ui_interaction,test_ui_smoke,test_ui_dpi}.py`（`tests/_dpi_probe.py` 为高 DPI 子进程探针，不被 pytest 直接收集）

脚本与基准：

- `scripts/verify_runtime.py`、`verify_ai_pipeline.py`、`verify_ui_model_flow.py` — 实机验收
- `scripts/verify_model_accuracy.py`、`verify_decoder_accuracy.py`、`make_accuracy_corpus.py` — 准确性基准与语料生成
- `scripts/package_model.py`、`audit_bundle.py`、`collect_licenses.py`、`make_icon.py`、`dev_demo.py`、`dev_preview*.py`
- `benchmarks/ctf_accuracy_v1.json` … `v4.json`（v4 为 60 条 / 41 类）
- `artifacts/`：`runtime_verification*.json`、`ai_pipeline_verification*.json`、`model_accuracy_xuanmusec_v4.json`、`decoder_coverage_v4.json`、`accuracy_v3_run.log`、`accuracy_v4_run.log`

打包与发布材料：

- `packaging/build_exe.ps1`（Nuitka）、`packaging/SecOne.iss`（Inno Setup）
- `licenses/`：Apache-2.0、LICENSE-LFM1.0、LICENSE-llama.cpp、LICENSE-XuanmuSec、LICENSE-XuanmuSec-upstream、PSF-2.0、LGPL、第三方依赖许可
- `THIRD_PARTY_NOTICES.md`、`NOTICE.md`、`LICENSE`、`requirements.txt`、`requirements.lock`、`pyproject.toml`、`.gitignore`
- `docs/OFFLINE_INSTALL.md`、`docs/TEST_REPORT.md`、`docs/RELEASE_NOTES.md`、`README.md`、本报告

## 4. 修复的问题

| 问题 | 影响 | 处理 | 验证 |
| --- | --- | --- | --- |
| 字面量 `flag{...}` 占位符被当成有效 Flag | 核心可信度 | `_looks_like_known_flag` 占位符过滤 + 负例语料 | `test_flag_engine`、`test_flag_benchmark` 负例 |
| 已知 XOR 样本漏检 | 核心可信度 | 文本/二进制单字节 XOR 扫描，Hex 解码后继续 XOR 扫描（移除提前 `continue`） | XOR 正例 + Hex 密文 XOR 用例 |
| 整段倒序密文无法恢复 | 漏报 | `_decode_once` 增加“整段倒序”解码族 | `test_whole_text_reversal_is_recovered` |
| 模型输出可凭空产生 Flag | 防幻觉 | AI 候选必须为材料逐字子串，否则计入 rejected | `test_ai_candidates_require_exact_material_evidence` |
| llama-server 把 GGUF 绝对路径当 model id 返回，泄漏本机路径 | 隐私/报告 | `LLMClient._model_label` 归一为显示名，`display_label()` 只从配置派生 | `test_model_label.py` 8 项 |
| 配置的模型文件不存在时界面卡在“模型文件未安装” | 可用性 | `discover_models()` + 设置页“扫描 models/ 中的 GGUF” | 设置页实机验证 |
| 打包只带两份模型许可，未带 Apache 全文与 llama.cpp MIT | 合规 | `ALWAYS_BUNDLED_LICENSES` / `RUNTIME_LICENSES` 门禁 | `test_package_model.py` |
| 打包测试把“许可缺失”写死，补齐后误报失败 | 测试稳定性 | monkeypatch `REQUIRED_LICENSES`，新增许可真实性用例 | 全套测试 |
| 符号链接拒绝分支因先 `resolve()` 而不可达 | 安全 | `add_paths` 先拒绝符号链接再解析去重 | `test_ingest`、`test_ui_interaction` |
| 取消事件在首个进度回调前触发时任务停留 `running` | 状态一致性 | 首个进度检查点移入 `try`，确保 `PipelineCancelled` 落库 | `test_pipeline`、`test_llm_client`、`test_ui_interaction` |
| 标准答案基准把畸形/嵌套 flag 计为命中 | 度量失真 | 严格 `flag\{[^{}\r\n]{1,200}\}` 提取、去重、畸形识别、非 flag 答案拒绝 | `test_model_accuracy.py` 7 项 |
| 基准缓存跨模型/提示词/预算复用导致结果不可比 | 度量失真 | 缓存键 = 模型路径 + prompt_version + max_tokens | `test_model_accuracy.py` |

## 5. 新增的功能

- **Flag 引擎**：整段倒序、Hex 字节单字节 XOR、Base64/Base32/Hex/URL/ROT13/ROT47 递归解码链、字符串打印路径与 XOR 扫描、文件偏移与解码链证据、四态（found/verified/candidate/rejected）与置信度排序。
- **AI 防幻觉**：模型 Flag 只有在材料中逐字出现才保留为 `candidate`，并保留来源、偏移、方法、证据上下文。
- **模型接入**：GGUF 元数据解析（架构/层数/上下文/模板）、模型发现与显示名、llama-server 启停、健康检查、OpenAI 兼容调用、超时/取消/错误诊断、无模型明确提示。
- **桌面工作台**：拖拽/多文件/文件夹/文本接入、去重、符号链接拒绝、进度、取消、完成/失败渲染、报告导出、历史、设置、诊断。
- **基准体系**：60 条 / 41 类标准答案语料（v4）、真实模型准确性基准（缓存、分类统计、异常输出计数、`formal=false` 标记）、确定性解码器覆盖率基准。
- **交付体系**：Nuitka standalone EXE、便携 ZIP、Inno Setup 安装包、独立模型资源包（GGUF 头校验、SHA256 清单、许可门禁）、141 条 SHA256 发布清单、23 项部署依赖静态审计、离线安装文档、第三方许可清单。

## 6. 自动化测试结果

- 命令：`.\.python\python.exe -m pytest tests -o addopts="" -q`
- 结果：**98 passed，0 failed**（2026-10-31 复跑，92.33s）

| 测试文件 | 用例 | 覆盖 |
| --- | ---: | --- |
| `test_flag_engine.py` | 10 | 直接匹配、递归编码、占位符过滤、去重置信度、倒序、Hex 密文 XOR、纯 Hex 无误报、AI 证据回查 |
| `test_flag_benchmark.py` | 7 | 负例、XOR、编码链、归档证据、AI 回查、状态排序、19/13 标注语料 P/R |
| `test_model_accuracy.py` | 9 | 严格提取、畸形与 runaway 嵌套识别、语料结构、重复 ID、非 flag 答案、缓存键校验、v4 语料与生成器一致 |
| `test_ingest.py` | 5 | 接入、路径穿越、限额、去重、归档来源 |
| `test_llm_client.py` | 10 | 健康、问答、reasoning 回退、多段、500、空内容、超时、未启动、模型列表、取消 |
| `test_model_metadata.py` | 4 | GGUF v2+ 元数据、架构/上下文/模板、截断、v1 说明 |
| `test_model_info.py` | 3 | 模型状态、GGUF 头、引擎描述 |
| `test_model_label.py` | 8 | 显示名、路径脱敏、空标识、量化省略 |
| `test_package_model.py` | 11 | 头校验、清单、许可强制、随包许可、发现、回退命名 |
| `test_bundle_audit.py` | 9 | 依赖组件、VC++ 运行库、路径泄漏、首启目录、权重误入、模型包布局 |
| `test_pipeline.py` | 4 | 无 AI 端到端、报告、结果结构、取消落库 |
| `test_ui_interaction.py` | 11 | 接入/去重/符号链接、拖拽信号、移除清空、空输入、忙碌锁定、进度、渲染、导出、失败恢复、取消状态机 |
| `test_ui_smoke.py` | 3 | 主窗口渲染与页面构造 |
| `test_ui_dpi.py` | 4 | 100%/125%/150%/200% 缩放下主窗口构建、像素比、抓图尺寸、三页光栅化、无零尺寸控件、五入口按钮不裁剪 |

## 7. 实际模型运行测试结果

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| llama-server 启动/健康/对话/连续生成/停服 | DONE 14/14（19.4s，端口 18111） | `artifacts/runtime_verification_xuanmusec.json` |
| 全流水线 + 防幻觉 + 报告落盘 | DONE 15/15（61.9s，端口 18112）；9 材料 / 7 Flag / 10 发现 | `artifacts/ai_pipeline_verification_xuanmusec.json` |
| 界面配置模型→保存→启动→推理 | DONE 9/9（端口 18105） | `artifacts/verify_ai_pipeline_engine_rename.json` 等 |
| 解题准确性（60 条标准答案） | **3/60 精确命中（5.0%）**，15 条异常输出，766.08s | `artifacts/model_accuracy_xuanmusec_v4.json` |
| 同语料确定性解码器 | **32/60（53.3%）**，32/60 无多余候选，全语料仅 1 个多余候选 | `artifacts/decoder_coverage_v4.json` |

命中的 3 条为明文、URL 百分号编码、源码注释——答案以可读形式出现或只需一步机械解码。其余 39 类（Base64/Base32/Hex/ROT13/ROT47/倒序/双层编码/Caesar/Atbash/进制 ASCII/Base58/组合变换/XOR/gzip/zlib/UTF-16LE 等）均未解出；15 条异常输出中 8 条为格式合法但答案错误，8 条为畸形形态（嵌套重复、未闭合、乱码），1 条重叠。多条在 512 token 上限内未收敛。

**该结果标记为 PARTIAL 且 `formal=false`**：样本量不足以给出正式准确率，只能说明当前样本下模型不具备可靠的机械解码能力。产品据此确立设计原则——机械解码由确定性引擎负责，模型输出必须回到证据中逐字命中才保留为 `candidate`，`verified` 不自动升级。

## 8. EXE 构建结果

- 命令：`powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1 -SkipTests`，日志 `nuitka-build.log`，exit 0
- `dist/SecOne/SecOne.exe`：32,806,912 字节，SHA256 `babfc00a72129c62c7a2c5d34642e2f1a5913a43ac787ad9f0cb773ce083c5fb`
- EXE 元数据：`FileVersion=1.0.0.0`、`ProductVersion=1.0.0.0`、`ProductName=SecOne`
- 便携目录：138 个文件，118,192,459 字节（约 112.7 MiB），含 `python312.dll` 与 PySide6 运行时，不依赖开发机 Python
- 启动冒烟：运行 15 秒未退出，首次启动创建 `data/history.db`（含 WAL/SHM）与 `logs/secone.log`，日志记录 `SecOne 1.0.0-rc1 started`
- 便携 ZIP：`dist/packages/SecOne-1.0.0-rc1-portable-win64.zip`，46,901,540 字节，SHA256 `afd838ec78b365f7ecfb0510c9fda045d1acda80fe88bf764bc66855cba83a74`

## 9. 安装程序构建结果

- 工具：Inno Setup 6.7.4，脚本 `packaging/SecOne.iss`，编译 exit 0（44.1s）
- 产物：`dist/installer/SecOne-1.0.0-rc1-setup.exe`，32,140,884 字节，SHA256 `49e380b78edef48ed5f9a2245b1e79c75f265c5ff6e383a4ab59c84b7dd46e09`
- 隔离目录静默安装：145 个文件落盘；安装后 `SecOne.exe` 与 `dist/SecOne/SecOne.exe` 字节一致；以最小 `PATH` 启动并记录 `SecOne 1.0.0-rc1 started`；模型缺失时按设计弹出提示
- 静默卸载：145 个程序文件与注册项全部移除，`data/`（含用户任务标记）与 `logs/` 按 `uninsneveruninstall` 保留
- 桌面快捷方式链路（`/MERGETASKS=desktopicon`）：安装 exit 0，桌面生成 `SecOne.lnk`（1,304 B），`TARGET` 指向安装目录 `SecOne.exe`、`WORKDIR` 为安装目录；通过快捷方式启动（offscreen）12 秒后进程存活，首启创建 `data/history.db` 与 `logs/secone.log`，日志记录 `SecOne 1.0.0-rc1 started`；静默卸载 exit 0 后快捷方式移除，`data/`、`logs/`、`models/`、`output/`、`runtime/`、`workspace/` 保留
- 一键验收：`scripts/verify_offline_install.ps1` 把安装→快捷方式→首启→可选模型包→卸载链路收敛为单条命令，本机自检 9/9 步骤 DONE，报告 `artifacts/offline_install_report.json`（详见第 10 节）
- 限制：仍在构建机上执行，未在无 Python、无网络的干净 Windows 上实测（见第 10 节）
- 已知偏差：安装包内附带的 `README.md` 是 2026-10-31 10:29 编译时的快照，之后仓库内 README/报告的数量与链接更新未回灌到安装包；Inno Setup 6.7.4 当前已不在本机，重新编译需重新安装该编译器。权威文档以仓库内 `README.md` 与 `docs/` 为准，本项不影响程序功能

## 10. 离线环境测试结果

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| 便携 ZIP 解压冒烟（最小 `PATH`，清除 `PYTHONHOME`/`PYTHONPATH`，offscreen） | DONE | 12 秒未退出，首启创建 `data/history.db`、`logs/secone.log`，输出 `SecOne 1.0.0-rc1 started` |
| 部署依赖静态审计（`scripts/audit_bundle.py`，23 项） | DONE | 内嵌解释器、Qt 平台插件、VC++ 运行库、许可、首启目录、开发机路径泄漏全部通过 |
| 安装包离线安装/启动/卸载 | DONE（本机隔离目录） | 第 9 节 |
| 桌面快捷方式安装→启动→卸载 | DONE（本机隔离目录） | 第 9 节：`SecOne.lnk` 目标正确、经快捷方式启动存活、卸载移除快捷方式且保留用户数据 |
| 一键离线安装验收脚本（`scripts/verify_offline_install.ps1`） | DONE（本机自检；干净机待跑） | 9 个步骤全部 DONE：安装包 SHA256、无 Python 前置检查、静默安装（141 文件）、载荷哈希一致、注册项、快捷方式解析、最小 `PATH` 经快捷方式启动、卸载保留数据；报告 `artifacts/offline_install_report.json` |
| 干净 Windows（无 Python、无网络）完整安装 | **BLOCKED** | 本机 `Containers-DisposableClientVM` 为 Disabled、`WindowsSandbox.exe` 不存在；启用需管理员权限并重启，当前环境不具备 |

补偿措施已尽量做实：发布包 PATH 缩减验证证明不依赖开发机 Python；静态审计覆盖运行时依赖与路径泄漏；但两者均不等同于干净机器验收，因此该项保持 BLOCKED，不计入 DONE。

## 11. 尚未解决的问题

1. **模型解题能力无正式结论**（PARTIAL）：60 条内部小样本 3/60，5.0%；不能外推为正式准确率。
2. **安装包未在干净环境验收**（BLOCKED）：验收已收敛为 `scripts/verify_offline_install.ps1 -CleanMachine` 单条命令并在本机自检通过，但仍需在干净 VM/物理机上实跑；与第 10 节同一阻塞。
3. **模型发布方版权/NOTICE 缺失**（PARTIAL）：`LICENSE-XuanmuSec.txt` 只记录 Apache-2.0 许可选择，正式对外分发权重前必须补齐。
4. **RAR 不支持**：仅保留原文件并提示，需要外部组件。
5. **真实鼠标拖拽与物理多显示器验收缺失**（PARTIAL）：高 DPI 布局已自动化——`test_ui_dpi.py` 在 100%/125%/150%/200% 与 1280×800/1600×900/1920×1080 下验证像素比、抓图尺寸与三页光栅化；物理指针拖拽、真实多显示器与系统级缩放观感仍需人工验收。
6. **“已验证”状态不会自动升级**：当前无自动验证器，`verified` 预留给人工或后续流程。
7. **模型提示词与 token 预算未调优**：多条用例在 512 token 内输出未收敛，属于工程取舍而非缺陷，但影响可用性。
8. **安装包内文档快照过期**（PARTIAL）：安装包内的 `README.md` 停留在编译时版本；Inno Setup 已不在本机，需重新安装后重编才能同步。程序代码与 EXE 不受影响。

## 12. 资源缺失和外部依赖

| 缺失项 | 影响 | 解除条件 |
| --- | --- | --- |
| 干净 Windows 测试机（无 Python、无网络） | 无法完成 P1 离线安装验收 | 提供干净 VM/物理机（或启用 Windows Sandbox，需管理员 + 重启）后执行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_offline_install.ps1 -CleanMachine` |
| 模型发布方版权/NOTICE 声明 | 模型资源包不得对外正式分发 | 由发布方提供 NOTICE/版权文件，放入 `licenses/` 后重打包 |
| RAR 解压组件（7-Zip 等） | RAR 材料只能保留原文件 | 随包分发可离线部署的解压组件并纳入许可清单 |
| 代码签名证书（可选） | 安装包无数字签名，可能触发 SmartScreen 提示 | 取得证书后在 Inno Setup 中签名 |
| 更大规模标准答案语料 | 准确率结论不具统计意义 | 扩充至 200+ 条并邀请人工标注 |

## 13. 下一阶段建议

1. **干净环境验收闭环**：优先在 Windows Sandbox/VM 上复跑安装→首启→接入材料→模型包安装→推理→卸载全链路，形成 DONE。
2. **补齐发布方 NOTICE**：在模型资源包内加入版权/NOTICE 后再对外分发；这是当前唯一阻断“正式发布”的合规项。
3. **模型能力路线**：不指望 2.6B 模型独立完成机械解码；改为“确定性解码器 + 模型做语义归纳/下一步建议 + 证据回查”的分工，并在提示词中要求模型引用候选 ID 而非直接给 Flag。
4. **基准扩样与固化**：把 v4 的 60 条扩到 200+ 条，输出可复现的 `formal` 报告（含置信区间），并纳入 CI 定期回归。
5. **交互补测**：真实鼠标拖拽、多显示器、长路径、中文文件名回归（100%/125%/150%/200% 高 DPI 缩放已由 `test_ui_dpi.py` 自动化）。
6. **发布工程化**：版本号/哈希/清单生成纳入单一脚本，避免手工同步；接入代码签名；为安装包增加“仅用户级安装”路径。
7. **可观测性**：把流水线各阶段耗时与失败原因结构化写入任务库，便于现场排障。

## 14. 最终交付文件及实际路径

| 交付物 | 实际路径 | 大小 | SHA256 |
| --- | --- | ---: | --- |
| 主程序目录 | `dist/SecOne/`（138 文件） | 118,192,459 B | 见 `dist/SHA256SUMS` |
| 主程序 EXE | `dist/SecOne/SecOne.exe` | 32,806,912 B | `babfc00a…c5fb` |
| 便携包 | `dist/packages/SecOne-1.0.0-rc1-portable-win64.zip` | 46,901,540 B | `afd838ec…a83a74` |
| 安装包 | `dist/installer/SecOne-1.0.0-rc1-setup.exe` | 32,140,884 B | `49e380b7…46e09` |
| 模型资源包 | `dist/packages/SecOne-model-XuanmuSec-2.6B-Q6_K.zip` | 2,246,914,836 B | `eb77aecd…8e87` |
| 模型资源目录 | `dist/packages/SecOne-model-XuanmuSec-2.6B-Q6_K/`（62 条清单） | — | 见包内清单 |
| 发布哈希清单 | `dist/SHA256SUMS`（141 条，已逐条重算核对） | 14,270 B | — |
| 模型权重 | `models/XuanmuSec-v2-Q6_K.gguf` | 2,221,614,464 B | `bfaf475c…8098` |
| 运行组件 | `runtime/`（llama-server 及其他，模型包提供） | — | 见模型包清单 |
| 基准语料 | `benchmarks/ctf_accuracy_v4.json`（60 条 / 41 类） | 25,983 B | — |
| 模型准确性报告 | `artifacts/model_accuracy_xuanmusec_v4.json` | 47,098 B | — |
| 解码器覆盖率报告 | `artifacts/decoder_coverage_v4.json` | 13,841 B | — |
| 实机验收报告 | `artifacts/runtime_verification_xuanmusec.json`、`ai_pipeline_verification_xuanmusec.json` | — | — |
| 一键离线安装验收脚本 | `scripts/verify_offline_install.ps1` | — | — |
| 离线安装验收报告（本机自检） | `artifacts/offline_install_report.json` | — | — |
| 测试报告 | `docs/TEST_REPORT.md` | — | — |
| 发布说明 | `docs/RELEASE_NOTES.md` | — | — |
| 离线安装文档 | `docs/OFFLINE_INSTALL.md` | — | — |
| 第三方许可清单 | `THIRD_PARTY_NOTICES.md`、`licenses/` | — | — |
| 构建脚本 | `packaging/build_exe.ps1`、`packaging/SecOne.iss` | — | — |
| 依赖锁定 | `requirements.lock`、`requirements.txt`、`pyproject.toml` | — | — |

关于“工具资源包”：本项目中所有分析插件（Crypto / 取证 / Web / Binary / Misc）与解码器均为纯 Python 模块，已由 Nuitka 编译进 `SecOne.exe` 与便携目录，不存在需要独立分发的工具运行组件；因此**未单独生成工具资源包**，这是有意设计而非漏交付。当前唯一可分离的运行期产物是模型资源包（GGUF + `runtime/` 下的 llama-server）。

五个核心入口已核对存在：一键梭哈、Crypto 分析、文件取证、代码审计、导出报告（`src/secone/ui/pages/workbench.py`）；`auto` 模式按 Crypto→取证→Web→Binary→Misc 顺序调度，`binary` 插件覆盖 ELF/PE，同时承担 Pwn 静态检查与 Reverse 静态分析。

### 交付结论

- 达到 RC1 可交付标准的部分：程序本体、确定性分析链、本地推理链、EXE、安装包、便携包、模型分包、哈希清单、测试与文档。
- 未达到正式发布门槛的部分：干净 Windows 离线验收（BLOCKED）、模型发布方 NOTICE（PARTIAL）、模型解题能力结论（PARTIAL）。三者解除后方可进入 v1.0.0 正式发布。
