# Sakura Launcher GUI

<p align="center">
  <img src="icon.ico" alt="Sakura Launcher GUI" width="80" height="80">
</p>

用于在本机下载模型、管理预设并启动 llama.cpp 翻译服务的图形界面。本仓库是 [PiDanShouRouZhouXD/Sakura_Launcher_GUI](https://github.com/PiDanShouRouZhouXD/Sakura_Launcher_GUI) 的维护 Fork，保留原项目的界面与配置格式。

[下载维护版](https://github.com/galact-byte/Sakura_Launcher_GUI/releases/latest) · [使用说明](docs/USAGE.md) · [报告问题或建议](https://github.com/galact-byte/Sakura_Launcher_GUI/issues) · [贡献代码](https://github.com/galact-byte/Sakura_Launcher_GUI/pulls)

## 下载与运行

普通用户直接下载打包好的程序，无需安装 Python 或克隆源码。

- **Windows**：下载名称为 `Sakura_Launcher_GUI_版本号.exe` 的文件，放在可写目录中运行。
- **macOS**：下载名称为 `Sakura_Launcher_GUI_macOS_版本号.zip` 的压缩包，解压后运行其中的应用。

启动器不包含模型、llama.cpp 和 CUDA 运行库，这些文件需要另行下载。Windows/macOS 已通过远端自动化测试与构建；macOS 实机运行仍待验证，不代表所有显卡和后端组合均已验证。

## 快速开始

1. 在“下载”页选择模型和与设备匹配的 llama.cpp 后端。使用 CUDA 后端时，还需下载并解压对应版本的运行库；也可以使用已经准备好的模型和后端。
2. 在“设置”中确认 llama.cpp 文件夹和模型搜索路径。在“启动”页选择模型、显卡及启动参数，启动服务。
3. 查看后端窗口，确认模型加载完成及服务监听地址，再在翻译客户端填写对应接口。翻译客户端使用的提示词模板需要与模型匹配。

已有后端可在设置中指定其文件夹；使用程序内下载安装时，llama.cpp 仍安装到启动器目录下的 `llama` 文件夹。启动报错或速度异常时，先查看“设置 → 日志”和后端终端输出，具体检查方法见[使用说明](docs/USAGE.md#启动闪退gpu-没有工作或速度慢)。

## 模型与后端下载

- 模型列表从 SakuraLLM 的 HuggingFace 仓库获取，llama.cpp 列表从官方 GitHub Releases 获取，可手动刷新；联网失败时保留缓存或内置列表。
- **刷新列表不会自动下载文件，也不会更新已安装的后端。** 安装后端前请先停止服务，避免替换正在使用的文件。
- 在“设置 → 常规设置 → 下载文件夹”选择保存位置。留空时下载到启动器目录，模型下载完成后会将该目录加入模型搜索路径。
- 下载过程支持取消，文件先暂存，校验成功后才替换同名文件。模型提供 SHA-256 时会进行摘要校验；连接失败、传输截断或返回网页错误内容时，会提示原因并清理本次暂存文件。

动态模型缺少可信的显存评估数据时，需要手动设置上下文、并行数等参数。不要仅根据列表中出现某个模型或后端，就认为它适合当前显卡。

## 升级与配置保留

1. 关闭旧启动器；如需更换后端，也先停止后端服务。
2. 将新版程序放回原启动器目录。
3. 保留 `sakura-launcher_config.json`、模型文件和 `llama` 文件夹，即可沿用现有配置与文件，无需重新下载。

配置、日志和目录缓存以启动器所在位置为准，不依赖快捷方式的“起始位置”。单文件程序仍会由打包运行时解压临时内容，不是完全不使用系统临时目录。

## 更多说明与问题反馈

- [维护版使用说明](docs/USAGE.md)：下载位置、命令模板、预设、GGUF 模型及启动排障。
- [上游用户手册](https://github.com/PiDanShouRouZhouXD/Sakura_Launcher_GUI/blob/main/Sakura%20Launcher%20GUI%20%E7%94%A8%E6%88%B7%E6%89%8B%E5%86%8C.md)：原版界面与操作参考；维护版差异以本仓库说明为准。

遇到维护版问题，请在[本仓库 Issues](https://github.com/galact-byte/Sakura_Launcher_GUI/issues) 中附上操作系统、显卡、模型文件名、后端版本、生成的启动命令及相关日志。分享前请检查并遮盖令牌等隐私信息。

AMD/ROCm 内核、多显卡和历史 OpenSSL 等环境相关问题仍需对应设备或日志验证，不能仅凭启动器修复认定已经解决。

## 界面预览

以下为原项目界面截图，维护版的新增选项以实际界面和使用说明为准。

<div align="center"><img src="assets/PixPin_2024-11-13_02-15-00.png" alt="原项目启动器界面" width="540"></div>

## 源码开发

以下步骤仅面向需要修改源码的开发者，不是普通用户的安装步骤。推荐使用 Python 3.12；可在独立虚拟环境中安装依赖。

```sh
git clone https://github.com/galact-byte/Sakura_Launcher_GUI.git
cd Sakura_Launcher_GUI
python -m pip install -r requirements.txt
python main.py
```

### 代码结构

```text
main.py                      # 程序入口
src/
├── common.py                # 路径、版本与公共功能
├── catalog.py               # 动态模型和后端目录、缓存
├── downloads.py             # 下载暂存与校验
├── gpu.py                   # GPU 检测与资源管理
├── llamacpp.py              # 后端版本与启动参数
├── sakura.py                # 模型信息与配置
├── setting.py               # 配置持久化
├── ui.py                    # 通用界面组件
├── section_download.py      # 下载页面
├── section_run_server.py    # 启动页面
├── section_settings.py      # 设置、预设与日志页面
├── section_share.py         # 共享页面
├── section_about.py         # 关于页面
├── sakura_share_api.py      # 共享服务 API
├── sakura_share_cli.py      # 共享命令行工具
├── sakura_ws_client.py      # WebSocket 客户端
└── utils/                   # GPU、系统与模型大小工具
tests/                       # 回归测试
```

### 检查与打包

```sh
python -m unittest discover -s tests -v
python -m compileall -q main.py src tests
```

缺少界面依赖时，相应用例会跳过；跳过不等于通过完整 GUI 验证。仓库的 GitHub Actions 负责 Windows/macOS 测试、打包及按需发布，详见[构建工作流](.github/workflows/build.yml)。需要在本地调试打包时使用：

```sh
pyinstaller --clean --noconfirm main.spec
```

## 上游与相关项目

- [原项目 Sakura Launcher GUI](https://github.com/PiDanShouRouZhouXD/Sakura_Launcher_GUI)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [SakuraLLM](https://github.com/SakuraLLM/SakuraLLM)
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
