相较 v1.2.1，本版更新模型与 llama.cpp 下载列表，并修复预设、日志和显卡识别中的多处问题。

## 下载列表与保存位置

模型列表改为从 SakuraLLM 的 HuggingFace 仓库刷新，llama.cpp 列表改为读取官方 Release，按当前系统和架构显示可用包，并匹配 CUDA 运行库。支持手动刷新、本地缓存和离线回退；刷新列表不会自动下载或覆盖已有模型和后端。

设置页新增下载文件夹选择。模型下载完成后，该目录会自动加入模型搜索路径。llama.cpp 压缩包仍解压到启动器目录下的 `llama` 文件夹，更新前请先停止后端。

下载增加连接与读取超时、内容和文件类型校验，失败时清理暂存文件并保留原有文件；可在进度页取消下载。提供摘要的模型还会验证 SHA-256。检查更新和启动器下载已指向本维护仓库。

## 预设、日志与显卡识别

修复预设保存后部分参数不能回读、删除后其他行按钮失效的问题。配置和资源位置不再依赖快捷方式的起始目录，日志页可显示当前运行日志。

修复 NVIDIA 设备索引、同名显卡匹配以及部分缺少 PCI ID 的适配器识别问题。这些修改不代表所有 AMD/ROCm、多显卡或驱动组合均已通过实机验证。

使用方法、命令模板和启动排障步骤见仓库的 [维护版使用说明](https://github.com/galact-byte/Sakura_Launcher_GUI/blob/main/docs/USAGE.md)。

## 下载与升级

Windows 用户下载 `Sakura_Launcher_GUI_v1.2.2.exe`；macOS 用户下载 `Sakura_Launcher_GUI_macOS_v1.2.2.zip`。启动器不包含模型、llama.cpp 或 CUDA 运行库。

升级前关闭旧启动器，将新版放入原启动器目录，保留 `sakura-launcher_config.json`、模型和 `llama` 文件夹。新增设置有默认值，可继续沿用原配置。

Windows/macOS 已通过远端自动化测试和构建；macOS 实机启动、特定 AMD/多 GPU 环境仍未验证。
