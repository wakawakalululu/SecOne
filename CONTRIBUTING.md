# 贡献指南

感谢关注 SecOne。提交改动前请先阅读本指南与 [SECURITY.md](SECURITY.md) 的设计红线。

## 开发环境

要求：Windows 10/11 x64，Python 3.11–3.13（项目使用 3.12）。

```powershell
python -m venv .python
.\.python\Scripts\activate
pip install -r requirements.txt
.\.python\python.exe run_secone.py
```

## 提交改动前

1. **运行完整测试**（113+ 项，必须全部通过）：
   ```powershell
   .\.python\python.exe -m pytest tests -q
   ```
2. **遵守离线优先红线**：不接受给程序增加联网下载、遥测、公网扫描或样本执行的功能；模型推理只允许本机 `127.0.0.1`。
3. **保持证据链完整**：Flag 引擎相关改动不得削弱「候选必须逐字回查证据、保留来源与偏移」的机制；占位符过滤不能放松。
4. UI 改动请在 offscreen 下自测（`tests/test_ui_smoke.py`、`test_ui_dpi.py` 已有基线），涉及布局的改动请在 100%/125%/150%/200% 缩放下检查。
5. 新增解码路径请同步补充 `tests/test_flag_engine.py` 正例/负例/边界用例，并跑一遍 `scripts/verify_decoder_accuracy.py` 确认语料回归不回退。

## 提交规范

使用 Conventional Commits：

```text
feat(flags): 新增 Base58 解码路径
fix(ingest): 修复符号链接拒绝分支不可达
docs: 更新候选模型清单
test: 补充凯撒全位移边界用例
```

## Wiki 维护

文档中心以 `docs/wiki/` 为唯一事实来源（随主仓库版本化）。修改页面后，用同步脚本推送到 GitHub Wiki 页签：

```powershell
.\.python\python.exe scripts\sync_wiki.py --push          # 同步、提交并推送
.\.python\python.exe scripts\sync_wiki.py --dry-run      # 只预览将变更的文件
```

## Pull Request

- 一个 PR 聚焦一件事，说明动机与验证方式；
- 关联 Issue（如有）；
- 若改动影响「结果状态语义」（`found`/`verified`/`candidate`/`none`）或打包门禁，请在描述中明确说明，这类改动需要维护者重点评审。

## 报告问题

普通缺陷与功能建议用 Issue 模板提交；安全问题见 [SECURITY.md](SECURITY.md)，不要公开披露。
