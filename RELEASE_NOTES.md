这是 galact-byte Fork 的维护版本，主要修复旧启动器与新版 llama.cpp 的启动参数兼容问题，沿用原有界面和配置格式。

## 新版 llama.cpp 启动修复

- 正确识别 `version: 1.0.0-dev (build 12633, ...)` 中的构建编号，不再误判为版本 1。
- 根据后端实际支持的参数启用 Flash Attention，新版使用 `-fa on`，旧版保留原有用法。
- 勾选禁用内存映射时，新版后端使用 `--load-mode none`，仍支持旧版的 `--no-mmap`。
- 如果后端参数检测失败，会在日志中说明并跳过可选参数，避免因为猜测参数而无法启动。

## 预设操作修复

修复设置页面长按“上移”将预设置顶时报错的问题，并适配新版 PySide6 的表格项交换方式，保留预设内容与原有排序方式。

## 下载与升级

Windows 用户下载 `.exe`；macOS 用户下载 `macOS` 压缩包。启动器不包含模型、llama.cpp 或 CUDA 运行库，这些文件仍需单独准备。

升级前退出旧启动器，保留原来的 `sakura-launcher_config.json`、模型和 `llama` 文件夹，再将新版启动器放入原目录使用。不需要重新下载模型，也不需要修改已经正常工作的 XUnity 或 Luna 接口地址。

新版参数在 Windows CUDA 12.4 的 llama.cpp b12633 上验证过；旧版参数分支有自动化回归测试。macOS 产物由 GitHub Actions 构建，未做实机运行验证；其他显卡和后端组合不作已验证承诺。
