# 修改记录 — Sakura Launcher GUI

## 2026-11-23 — v1.2.1：新版后端兼容与预设置顶修复

### 背景与目标
- llama.cpp b12633 的版本输出为 `version: 1.0.0-dev (build 12633, ...)`，原解析会误识别为构建号 1。
- 新后端的 Flash Attention 需要显式值，禁用内存映射改用 `--load-mode none`；旧参数会导致启动失败。

### 影响与兼容性
- 同时支持旧式数字版本和新版输出中的 build 编号，并读取 stdout/stderr。
- 启动时根据实际 `--help` 输出选择可选参数，不猜测加载模式参数变更的版本阈值。
- 保留旧后端的 `-fa` 和 `--no-mmap` 行为；两项未勾选时不添加参数。
- 参数检测失败或超时会记录警告并省略可选参数，不阻止使用后端默认设置。
- 修复预设长按置顶时多传一个参数导致的异常；不调整界面样式、已有配置结构、模型、SakuraTranslator 或正在运行的服务。
- GitHub Actions 在打包前运行回归测试；推送、PR 和手动构建均上传产物，手动选择发布时创建 Release，正文来自 `RELEASE_NOTES.md`。
- macOS 应用先打包为 ZIP 再上传，保留应用包结构。
- 回滚可还原 `main.py` 与 `src/llamacpp.py` 的本次修改，无数据迁移。

### 文件与实现
| 操作 | 路径 | 说明 |
|---|---|---|
| 修改 | `src/llamacpp.py` | 修复构建号识别并检测可选参数能力 |
| 修改 | `main.py` | 将两项开关接入能力检测，移除原有版本阈值分支 |
| 新增 | `tests/test_llamacpp.py` | 覆盖新旧版本、参数、输出流与失败路径 |
| 修改 | `src/section_settings.py` | 修复预设置顶的错误参数 |
| 修改 | `src/common.py` | 版本更新为 v1.2.1 |
| 修改 | `.github/workflows/build.yml` | 增加回归测试、手动构建产物和 Release 发布 |
| 修改 | `.gitignore` | 追加本地 AI 配置与测试缓存忽略项 |
| 新增 | `tests/test_presets.py` | 隔离 Qt 表格边界验证源码排序方法 |
| 新增 | `tests/test_gui_presets.py` | 在远端完整 Qt 环境模拟长按上移，核对排序与预设内容 |
| 新增 | `RELEASE_NOTES.md` | 面向用户的发布说明 |
| 新增 | `CHANGES.md` | 记录兼容性变化与验证边界 |

### 验证
- 修改前 `python -m unittest discover -s tests -v`：版本相关出现 4 个断言失败；可选参数测试因待实现函数不存在而报错。
- 修改后 `python -m unittest discover -s tests -v`：12 项测试通过。
- 完成预设修复后，`python -m unittest discover -s tests -v`：16 项中 15 项通过，完整 Qt 测试因本地缺依赖跳过 1 项。
- `python -m pytest -q`：15 passed, 1 skipped, 7 subtests passed。
- `python -m compileall -q main.py src tests` 与 `git diff --check`：通过。
- 对本机 b12633 实测：构建号识别为 12633；两项均启用时生成 `-fa on --load-mode none`，真实 `llama-server.exe` 参数解析返回码为 0。

### 已知限制与后续
- 当前 Python 环境缺少项目已有的 `qfluentwidgets`、`wmi` 依赖；不在本机安装新依赖，完整 Qt 交互测试和打包交由 GitHub Actions 执行。
- 首轮远端完整 Qt 测试发现新版 PySide6 不接受 `QTableWidgetItem(existing_item)`，已改为交换原始表格项，避免复制构造异常；该失败通过真实长按测试捕获。
- 本地完整 Qt 交互测试会标记跳过，不能把它计为本机通过；发布以远端测试和构建成功为前提。
- 现用 `Sakura_Launcher_GUI_v1.2.0-beta.exe` 不会因修改源码自动更新，需要下载 Release 资产后替换。
- 旧后端分支通过回归测试覆盖，未重新下载旧二进制进行实机加载测试。
