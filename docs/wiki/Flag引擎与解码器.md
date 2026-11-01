# Flag 引擎与解码器

Flag 引擎（`src/secone/core/flag_engine.py`）是 SecOne 的还原核心：规则匹配产生 `found`，确定性解码产生 `candidate`，全部结果保留证据并可回查。

## 解码族清单（当前版本）

| 类别 | 覆盖 |
| --- | --- |
| 编码递归解码 | Base64（含 Base64URL、无填充）、Base32、Hex（含大写冒号分隔）、URL 百分号编码、ROT13、ROT47 |
| 古典密码 | 凯撒（全位移扫描）、Atbash、仿射密码（互质密钥全扫描） |
| 进制与字符码 | 二进制串（连续/空白分隔）、八进制、十进制字符码列表、Unicode 码点 |
| 高级编码 | Base58、Base85（ASCII85/Z85 形态） |
| 文本层变换 | HTML 实体（十进制/十六进制）、Unicode 转义（`\uXXXX`）、Quoted-Printable、UTF-16LE、JS 字符串拼接与数组 `join` 还原、整段倒序 |
| 压缩 | gzip（`\x1f\x8b` 头）、zlib（`\x78` 头）解压 |
| 二进制 | 单字节 XOR 全扫描（含十六进制密文形态） |

递归解码默认深度 3、结果上限 80（`config/app.yaml` 的 `analysis.decode_depth` / `max_decode_results`）。

## 还原率

60 条标准答案语料（`benchmarks/ctf_accuracy_v4.json`，41 类，答案均不以字面形式出现在材料中）：

- **解码族扩展后：60/60 命中标准答案（100%）**，60/60 无多余候选，全语料 0 个多余候选项（报告 `artifacts/decoder_coverage_v5.json`）；
- 扩展前基线为 32/60（53.3%），见 `artifacts/decoder_coverage_v4.json`。

该数字只度量确定性解码器能力，与模型解题准确率无关（对照见 [基准与评估](基准与评估.md)）。

## 防幻觉机制

1. **逐字回查**：模型提出的 Flag 只有逐字出现在材料原文、已提取 Flag 或静态发现证据中才会进入候选列表，并始终标记 `candidate`。
2. **占位符过滤**：`flag{...}`、`flag{your_flag_here}` 等占位形态不进入有效结果（强占位符表 + 弱词表）。
3. **跨来源去重**：同一 Flag 串从多条路径命中时合并，保留最优证据链。
4. **提示词硬性规则**：`config/prompts.yaml` 约束模型不得编造文件内容、命令输出、偏移地址或 flag，不得声称执行了未执行的工具。
5. **证据保留**：每个候选记录来源文件、字节偏移、提取方法、解码链与证据原文。

## Flag 正则

默认支持 `flag{...}`、`ctf{...}`、`secone{...}`、`flag(...)` 四种形态（大小写不敏感，长度 1–200），可在 `config/app.yaml` 的 `flags.patterns` 与 `flags.custom_prefixes` 扩展自定义前缀。

## 规则级质量

19 正例 / 13 负例标注语料（直接、Base64/Base32/Hex/URL/ROT、双层编码、JS 注释、大写、长 Flag、XOR 二进制；负例含占位符、格式文档、良性源码/文本/二进制）上，规则级 **precision 1.0、recall 1.0**。语料只度量规则匹配与解码器，不代表真实模型解题准确率。
