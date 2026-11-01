<!-- 标题使用 Conventional Commits，如 feat(flags): ... -->

## 动机

<!-- 为什么做这个改动，关联 Issue 用 Fixes #123 -->

## 改动内容

-

## 验证

- [ ] `.\.python\python.exe -m pytest tests -q` 全部通过
- [ ] 涉及 Flag 引擎时：`scripts/verify_decoder_accuracy.py` 语料回归不回退
- [ ] 涉及 UI 时：offscreen 冒烟通过；布局改动在 100%/125%/150%/200% 缩放下检查过
- [ ] 涉及打包时：`scripts/audit_bundle.py` 通过

## 边界自检

- [ ] 未引入联网上传、遥测或公网扫描
- [ ] 未引入样本执行或动态调试
- [ ] 未削弱证据链（候选来源、偏移、逐字回查）与占位符过滤
- [ ] 未改变结果状态语义（如改动请在「动机」中重点说明）
