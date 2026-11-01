# 推理运行目录

SecOne 通过本机 HTTP 管理 `llama-server`：

```text
runtime/llama-server.exe
```

## 当前已验证的版本

| 项 | 值 |
| --- | --- |
| 构建 | llama.cpp `b12017`（`version: 0.8.0-dev`，commit `5047748f1`） |
| 发行包 | `llama-b12017-bin-win-cpu-x64.zip` |
| 来源 | `https://github.com/ggml-org/llama.cpp/releases/tag/b12017` |
| 平台 | Windows x64，CPU 后端（含 `ggml-cpu-*.dll` 多架构分派） |
| 验证 | `scripts/verify_runtime.py` 全部通过（14 项） |

二进制文件不纳入版本库（见 `.gitignore`）。重新获取：

```powershell
curl.exe -L -o llama.zip `
  https://github.com/ggml-org/llama.cpp/releases/download/b12017/llama-b12017-bin-win-cpu-x64.zip
Expand-Archive llama.zip -DestinationPath runtime -Force
```

## 准备运行组件

1. 从 llama.cpp 官方发布或自行编译，得到 `llama-server.exe` 与依赖 DLL
   （`llama.dll`、`ggml*.dll`、运行库等）。
2. 将整套组件放入本目录，保持相对路径 `runtime/llama-server.exe`。
3. 在“模型与设置”页确认引擎状态，并启动服务。
4. 默认只绑定 `127.0.0.1:18080`，不访问公网。

## 版本与参数

SecOne 当前使用的启动参数：

```text
-m <GGUF> --host 127.0.0.1 --port 18080 -c 8192 -ngl 0
```

线程、GPU 层、端口与上下文可在设置页修改，额外参数可通过
`config/app.yaml` 的 `model.extra_args` 追加。

不同 llama.cpp 版本对模板、量化与采样参数的支持不同。升级运行组件后，
请用实际 GGUF 完成一次启动、健康检查和对话推理验证，并记录版本号：

```powershell
.\.python\python.exe scripts\verify_runtime.py --port 18099
```

## 许可

llama.cpp 以 MIT 许可发布。分发运行组件时保留上游许可文本
（`licenses/LICENSE-llama.cpp.txt`），并注明具体构建来源与版本。
`scripts/package_model.py --runtime-dir runtime` 会自动把该许可文本打进模型包，
缺失时终止打包。
