# SecOne 离线安装与部署（v1.0.0-rc1）

本文档面向拿到 RC1 交付物的使用者。SecOne 的运行不依赖 Python，也不依赖互联网；模型权重和 llama.cpp 运行组件作为独立资源包分发。

## 1. 交付物

| 文件 | 说明 |
| --- | --- |
| `SecOne-1.0.0-rc1-portable-win64.zip` | 便携包（推荐当前使用）：解压即运行，内含 Nuitka standalone 程序、Qt 运行时与 python312.dll |
| `SecOne/` | Nuitka standalone 主程序目录，可直接整体复制运行 |
| `SecOne-1.0.0-rc1-setup.exe` | 主程序安装包（Inno Setup 6.7.4 构建）：当前用户安装到 `%LOCALAPPDATA%\Programs\SecOne`，无需管理员权限 |
| `SecOne-model-*.zip` | 模型资源包：GGUF、`model.json`、可选的 `runtime/`、许可文件与 `SHA256SUMS.txt` |
| `SHA256SUMS` | 发布物整体校验清单（138 个程序文件 + 1 个便携 ZIP + 1 个安装包 + 1 个模型资源包，共 141 条） |

主程序包（便携 ZIP 或安装包）不含模型权重和 llama.cpp 二进制。缺少模型时，文件摄入、静态分析、Flag 引擎和报告仍可使用，界面会显示“模型未安装 / 尚未完成实机推理验证”。

## 2. 系统要求

- Windows 10/11 x64。
- 当前用户权限即可，不需要管理员权限。使用安装包时默认安装到 `%LOCALAPPDATA%\Programs\SecOne`；便携包解压到任意可写目录即可。
- 磁盘空间：便携包约 113 MB（解压后），模型包建议预留 5 GB 以上，取决于量化版本。
- 完全离线运行；推理只监听 `127.0.0.1:18080`。

## 3. 安装主程序

### 3.1 使用便携 ZIP（当前推荐）

便携 ZIP 解压即用，无需安装；安装包提供开始菜单与卸载入口，两者任选其一：

1. 校验 ZIP：
   ```cmd
   certutil -hashfile SecOne-1.0.0-rc1-portable-win64.zip SHA256
   ```
   与发布清单 `SHA256SUMS` 对照。
2. 解压到任意可写目录，例如 `D:\SecOne`。
3. 运行 `D:\SecOne\SecOne.exe`。程序不依赖系统 Python，`python312.dll` 与 Qt 运行时已包含在目录内。
4. 首次启动会在程序目录下创建 `data/`、`workspace/`、`output/`、`logs/`。

> 便携包中的 `models/`、`runtime/` 仅含占位清单（`model.json`、`README.md`）。模型与 llama-server 需按第 4 节单独安装。

### 3.2 使用安装包（可选）

RC1 已由 Inno Setup 6.7.4 生成 `dist/installer/SecOne-1.0.0-rc1-setup.exe`（32,140,884 字节，SHA256 `49e380b78edef48ed5f9a2245b1e79c75f265c5ff6e383a4ab59c84b7dd46e09`）：

1. 校验安装包：
   ```cmd
   certutil -hashfile SecOne-1.0.0-rc1-setup.exe SHA256
   ```
2. 双击运行，按向导安装；默认安装到 `%LOCALAPPDATA%\Programs\SecOne`，当前用户权限即可。
3. 模型或 `runtime/` 缺失时，安装向导结束时会明确提示，安装完成后仍可正常启动静态分析功能。
4. 卸载不会删除 `models/`、`runtime/`、`data/`、`workspace/`、`output/`、`logs/`。

如需重新编译：编译前必须存在 `dist\SecOne\`，在装有 Inno Setup 6 的机器上执行：

```cmd
iscc packaging\SecOne.iss
```

## 4. 安装模型与推理引擎

1. 校验模型包：
   ```cmd
   certutil -hashfile SecOne-model-*.zip SHA256
   ```
2. 解压模型包，把其中的 `models/`、`runtime/`、`licenses/` 合并到 SecOne 程序目录（便携包为解压目录，安装包为 `%LOCALAPPDATA%\Programs\SecOne`）：
   ```text
   <SecOne 程序目录>\models\XuanmuSec-v2-Q6_K.gguf
   <SecOne 程序目录>\runtime\llama-server.exe
   ```
3. 模型包内的 `SHA256SUMS.txt` 可用于逐个文件核验。
4. 启动 SecOne，进入“模型与设置”：
   - 模型状态应显示“模型已就绪”或明确说明缺失项；
   - 如果默认文件名与实际文件不一致，点“扫描 models/ 中的 GGUF”，
     从下拉框选中实际存在的模型（选中即写入路径），再点“保存并生效”；
   - “推理服务”显示未启动属于正常状态；
   - 点击“启动本地引擎”，等待健康检查通过；
   - 点击“测试连接”确认可以返回文本。

> 模型路径、运行时路径、端口、上下文长度、GPU 层数和线程数都可以在设置页修改，不需要重新编译。

## 5. 首次离线验收清单

在无网络、未安装 Python 的干净 Windows 机器上执行：

1. 断开网络（禁用网卡或拔掉网线）。
2. 确认系统中不存在 Python：`where python` 应失败。
3. 解压便携包并启动 `SecOne.exe`，或安装安装包后从开始菜单启动。
4. 拖入一个 ZIP 压缩包和一份文本，确认能识别材料数量。
5. 运行“一键梭哈”，确认进度条推进且界面不冻结。
6. 确认结果页显示 Flag 候选或“未发现可靠 Flag”，且每个候选能查看来源文件与偏移。
7. 导出 Markdown / JSON 报告，确认文件写入 `output/`。
8. 安装模型包后启动本地引擎，运行一次问答。
9. 关闭程序，确认 `logs/` 中有本次运行日志。

## 6. 校验与排障

- **模型状态“缺少对话模板”**：GGUF 元数据里没有 `tokenizer.chat_template`，请换用模型发布方提供的完整版本。
- **模型状态“尚未完成实机推理验证”**：文件头有效但本次会话尚未成功调用推理服务；启动引擎并测试连接后才会显示在线。
- **端口被占用**：设置页更换端口，默认 `18080`。
- **llama-server 提前退出**：查看 `logs/llama-server.log`，确认运行组件版本与 GGUF 架构匹配。
- **杀毒软件拦截**：Nuitka 打包产物可能被启发式误报，请核对发布清单中的 SHA256 后再决定是否放行。
- **卸载后重新安装**：任务库、工作区、报告位于保留目录，不会被自动删除。

## 7. 当前 RC1 的验证边界

- 本仓库不附带 XuanmuSec GGUF；llama.cpp 运行组件已验证可用的构建为 `b12017`
  （`0.8.0-dev`），可从上游发行页获取后放入 `runtime/`。
- 模型包打包会强制检查 `licenses/LICENSE-XuanmuSec.txt`、`Apache-2.0.txt` 与
  `licenses/LICENSE-LFM1.0.txt`；分发 `runtime/` 时还会强制要求
  `LICENSE-llama.cpp.txt`（MIT）。缺少时拒绝打包。
- `LICENSE-XuanmuSec.txt` 记录发布方声明的 Apache-2.0 许可选择；正式分发权重前仍需取得发布方自己的 NOTICE/版权声明。
- 已实际构建并通过启动冒烟：Nuitka standalone `dist/SecOne/SecOne.exe`、便携 ZIP 与 `dist/SHA256SUMS`。
- 推理链路已实机验证：`verify_runtime.py` 14/14、`verify_ai_pipeline.py` 15/15、
  `verify_ui_model_flow.py` 9/9（llama.cpp `b12017` + Qwen2.5-0.5B-Instruct `q4_k_m`）。
- 安装包已由 Inno Setup 6.7.4 构建并在本机隔离目录完成静默安装（145 个文件）、最小 `PATH` 启动与静默卸载验证：安装后 EXE 与 `dist/SecOne/SecOne.exe` 字节一致，卸载保留 `data/`、`logs/`。尚未在无 Python、无网络的干净 Windows 上执行。
- `scripts/audit_bundle.py` 对 `dist/SecOne` 完成 23 项部署依赖静态审计并全部通过：
  内嵌 `python312.dll`/`python3.dll`、Nuitka 布局下的 `PySide6/qt-plugins/platforms/qwindows.dll`、
  Qt 核心/GUI/Widgets DLL、VC++ 运行库（随包携带，目标机无需安装 Redistributable）、
  四份许可文本、首次启动目录为空、`SecOne.exe` 与配置文件中无开发机路径泄漏。
  审计同时确认 `runtime/` 只含 `README.md`，属于设计：推理引擎随模型资源包分发。
  该审计是静态证据，不能替代第 5 节在干净机器上的真实启动、渲染与写盘验证。
- 尚未在无 Python、无网络的干净 Windows 机器上执行第 5 节验收清单，状态为 BLOCKED。
- 模型包若包含 `runtime/`，接收方应核对其中的 `licenses/LICENSE-llama.cpp.txt`
  与包内 `SHA256SUMS.txt`。

## 8. 一键离线安装验收脚本

`scripts/verify_offline_install.ps1` 把第 5 节的安装验收收敛为一条命令，供干净 Windows 机器执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_offline_install.ps1 -CleanMachine

# 需要同时验收模型包时追加：
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_offline_install.ps1 -CleanMachine `
  -ModelPackage dist\packages\SecOne-model-XuanmuSec-2.6B-Q6_K.zip
```

脚本按顺序检查：安装包存在性与 SHA256 → 干净机前置条件（`PATH` 上无 `python`/`python3`/`py`）→ 桌面快捷方式未被占用 → 静默安装（`/MERGETASKS=desktopicon`，独立临时目录）→ 安装后 EXE 与 `dist\SecOne\SecOne.exe` 哈希一致 → 卸载注册项 → 快捷方式 `TARGET`/`WORKDIR` 解析 → 经快捷方式、最小 `PATH`、无 Python 环境启动并检查首启产物 → 可选模型包部署 → 静默卸载并确认程序文件/快捷方式/注册项移除且 `data\`、`logs\` 保留。任一步失败即非零退出，并写出 `artifacts\offline_install_report.json`。

- `-CleanMachine` 只在报告 `scope` 字段记录“由操作者声明为干净机”；脚本本身无法证明机器干净。
- 本机自检（非干净机）已跑通全部 9 个步骤，安装后递归计数 141 个文件（含 `unins000.exe`/`.dat`）；首次启动生成 `history.db`、`-wal`、`-shm` 与 `secone.log` 后为 145 个，与既有记录一致。
- 该自检证明脚本可用，**不**构成干净机验收；干净机上的 `-CleanMachine` 运行才会把第 7 节的 BLOCKED 项转为 DONE。
- 脚本不覆盖的 UI 项仍需人工执行：真实拖拽材料、一键梭哈、报告导出、模型缺失提示对话框（静默模式不显示对话框）。
