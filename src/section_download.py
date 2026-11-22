from dataclasses import dataclass
from enum import Enum
import logging
import os
import json
import sys
import threading
import requests
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QFrame,
    QHeaderView,
    QTableWidgetItem,
)
from qfluentwidgets import (
    FluentIcon as FIF,
    TableWidget,
    TransparentPushButton,
    ProgressBar,
    InfoBar,
    MessageBox,
)

from .common import CURRENT_DIR, get_resource_path, GHPROXY_URL, LAUNCHER_REPOSITORY
from .downloads import download_file
from .setting import SETTING
from .llamacpp import *
from .sakura import SAKURA_LIST, Sakura
from .catalog import read_cache, refresh_catalog, write_cache
from .ui import *


def UiDescription(html):
    description = QLabel()
    description.setText(html)
    description.setTextFormat(Qt.RichText)
    description.setWordWrap(True)
    description.setOpenExternalLinks(True)
    description.setMargin(4)
    description.setTextInteractionFlags(
        Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
    )
    return description


def UiTable(columns):
    table = TableWidget()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    vh = table.verticalHeader()
    hh = table.horizontalHeader()
    vh.hide()
    vh.setSectionResizeMode(QHeaderView.ResizeToContents)
    hh.setSectionResizeMode(QHeaderView.ResizeToContents)
    hh.setStretchLastSection(True)
    return table


def UiTableLabel(text):
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled)
    return item


def UiDownloadButton(on_click):
    download_button = TransparentPushButton(FIF.DOWNLOAD, "下载")
    download_button.clicked.connect(on_click)
    return download_button


class LoadDataThread(QObject):
    sig_loaded = Signal(dict, str)
    finished = Signal()

    def __init__(self, previous, cache_path, parent=None):
        super().__init__(parent)
        self.previous = previous
        self.cache_path = cache_path
        self.cancelled = threading.Event()
        self.worker = None
        QApplication.instance().aboutToQuit.connect(self.cancel)

    def cancel(self):
        self.cancelled.set()

    def start(self):
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def isRunning(self):
        return self.worker is not None and self.worker.is_alive()

    def run(self):
        # 网络线程不持有 Qt 原生线程生命周期，关窗不会触发 QThread 析构崩溃。
        try:
            data, messages = refresh_catalog(self.previous, cancelled=self.cancelled.is_set)
            if self.cancelled.is_set():
                return
            try:
                write_cache(self.cache_path, data)
            except OSError as exc:
                messages.append(f"无法写入目录缓存：{exc}")
            for message in messages:
                logging.warning(message)
            status = "官方列表已更新" if not messages else "部分来源更新失败，已保留缓存；详情见日志"
            self.sig_loaded.emit(data, status)
        except Exception:
            logging.exception("下载目录刷新异常")
            if not self.cancelled.is_set():
                try:
                    self.sig_loaded.emit(self.previous, "列表刷新失败，已保留原列表；详情见日志")
                except RuntimeError:
                    pass
        finally:
            try:
                self.finished.emit()
            except RuntimeError:
                pass  # 窗口销毁后不再投递完成通知。


class DownloadTaskState(Enum):
    RUNNING = 1
    SUCCESS = 2
    ERROR = 3


@dataclass
class DownloadTask:
    name: str
    url: str
    filename: str
    state: DownloadTaskState = DownloadTaskState.RUNNING
    directory: str = ""
    expected_sha256: str = ""

    @property
    def path(self):
        return os.path.join(self.directory or CURRENT_DIR, self.filename)


class DownloadThread(QObject):
    sig_progress = Signal(int)
    sig_success = Signal()
    sig_error = Signal(str)

    def __init__(self, url, filename, expected_sha256=""):
        super().__init__()
        self.url = url
        self.filename = filename
        self.expected_sha256 = expected_sha256
        self.cancelled = threading.Event()
        self.worker = None
        QApplication.instance().aboutToQuit.connect(self.stop)

    def start(self):
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def run(self):
        try:
            download_file(self.url, self.filename, self.sig_progress.emit,
                          self.expected_sha256, self.cancelled.is_set)
            if not self.cancelled.is_set():
                self.sig_success.emit()
        except Exception as exc:
            logging.error("下载失败 %s: %s", self.filename, exc)
            if not self.cancelled.is_set():
                try:
                    self.sig_error.emit(str(exc))
                except RuntimeError:
                    pass

    def stop(self):
        self.cancelled.set()


class DownloadSection(QFrame):
    llamacpp_download_src = LLAMACPP_LIST.DOWNLOAD_SRC[0]
    sakura_download_src = SAKURA_LIST.DOWNLOAD_SRC[0]
    download_tasks: List[DownloadTask] = []
    download_threads: List[QThread] = []

    def __init__(self, title):
        super().__init__()
        self.setObjectName(title.replace(" ", "-"))
        self.refresh_buttons = []
        self.download_tasks = []
        self.download_threads = []
        self.catalog_labels = []
        self.catalog_thread = None
        self.cache_path = os.path.join(CURRENT_DIR, "download-catalog.json")
        with open(get_resource_path("data.json"), encoding="utf-8") as stream:
            bundled = json.load(stream)
        self.catalog_data = read_cache(self.cache_path, bundled)
        self.init_ui()

    def _catalog_controls(self):
        label = QLabel("正在加载下载列表")
        button = TransparentPushButton(FIF.SYNC, "刷新列表")
        button.clicked.connect(self.start_catalog_refresh)
        self.catalog_labels.append(label)
        self.refresh_buttons.append(button)
        return UiRow(label, None, button)

    def apply_catalog(self, data, status):
        self.catalog_data = data
        SAKURA_LIST.update_sakura_list(data)
        LLAMACPP_LIST.update_llamacpp_list(data)
        for label in self.catalog_labels:
            label.setText(status)

    def start_catalog_refresh(self):
        if self.catalog_thread is not None and self.catalog_thread.isRunning():
            return
        for button in self.refresh_buttons:
            button.setEnabled(False)
        for label in self.catalog_labels:
            label.setText("正在查询官方列表，当前条目仍可使用…")
        self.catalog_thread = LoadDataThread(self.catalog_data, self.cache_path, self)
        self.catalog_thread.sig_loaded.connect(self.apply_catalog)
        self.catalog_thread.finished.connect(self._catalog_finished)
        self.catalog_thread.finished.connect(self.catalog_thread.deleteLater)
        self.catalog_thread.start()

    def _catalog_finished(self):
        self.catalog_thread = None
        for button in self.refresh_buttons:
            button.setEnabled(True)

    def init_ui(self):
        self.setLayout(
            UiStackedWidget(
                ("Sakura模型下载", self._create_sakura_download_section()),
                ("llama.cpp下载", self._create_llamacpp_download_section()),
                ("下载进度", self._create_download_progress_section()),
            ),
        )
        self.apply_catalog(self.catalog_data, "已加载缓存或内置列表")
        self.start_catalog_refresh()

    def refresh_sakura_table(self, sakura_list):
        table = self.sakura_table

        def create_button(sakura: Sakura):
            download_fn = lambda: self.start_download_sakura(sakura)
            button = UiDownloadButton(download_fn)
            return button

        table.clearContents()
        table.setRowCount(len(sakura_list))
        for row, sakura in enumerate(sakura_list):
            table.setItem(row, 0, UiTableLabel(sakura.filename))
            table.setItem(row, 1, UiTableLabel(f"{sakura.size}GB"))
            table.setCellWidget(row, 2, create_button(sakura))

    def _create_sakura_download_section(self):
        def on_src_change(text):
            self.sakura_download_src = text

        comboBox = UiRow(
            QLabel("下载源"),
            None,
            UiComboBox(SAKURA_LIST.DOWNLOAD_SRC, on_src_change),
        )

        self.sakura_table = UiTable(["名称", "大小", "操作"])
        SAKURA_LIST.changed.connect(self.refresh_sakura_table)

        description = UiDescription(
            """
        <p>您可以在这里下载不同版本的模型，模型保存到设置中的下载文件夹，留空时保存到启动器目录。新下载目录会自动加入模型搜索路径。也可从<a href="https://huggingface.co/SakuraLLM/">Hugging Face镜像站</a>下载模型，将下载的gguf文件放到启动器所在文件夹下即可。</p>
        <p>列表从 SakuraLLM 官方仓库刷新，仅列出具有校验值的单文件 GGUF；断网时使用缓存或内置列表。模型规模、量化和上下文都会影响显存占用，请按模型说明选择，刷新不会自动下载文件。</p>
        """
        )

        return UiCol(
            description,
            UiHLine(),
            comboBox,
            self._catalog_controls(),
            self.sakura_table,
        )

    def refresh_llamacpp_table(self):
        table = self.llamacpp_table

        def create_button(llamacpp: Llamacpp):
            download_fn = lambda: self.start_download_llamacpp(llamacpp)
            button = UiDownloadButton(download_fn)
            button.setEnabled(self.llamacpp_download_src in llamacpp.download_links)
            return button

        table.clearContents()
        rows = list(LLAMACPP_LIST)
        table.setRowCount(len(rows))
        for row, llamacpp in enumerate(rows):
            table.setItem(row, 0, UiTableLabel(llamacpp.version))
            table.setItem(row, 1, UiTableLabel(llamacpp.gpu))
            table.setCellWidget(row, 2, create_button(llamacpp=llamacpp))

    def _create_llamacpp_download_section(self):
        self.llamacpp_table = UiTable(["版本", "适合显卡", "下载"])
        self.refresh_llamacpp_table()

        LLAMACPP_LIST.changed.connect(self.refresh_llamacpp_table)

        def on_src_change(text):
            self.llamacpp_download_src = text
            self.refresh_llamacpp_table()

        select_download_src = UiRow(
            QLabel("下载源"),
            None,
            UiComboBox(LLAMACPP_LIST.DOWNLOAD_SRC, on_src_change),
        )

        self.label_current_llamacpp_version = QLabel()
        self._update_current_llamacpp_version()
        current_version_hint = UiRow(
            QLabel("当前版本"),
            (self.label_current_llamacpp_version, 0),
        )

        description = UiDescription(
            """
        <p>
        列表从<a href="https://github.com/ggml-org/llama.cpp/releases">llama.cpp 官方发行页</a>刷新，仅显示匹配当前系统和架构的已识别包；每日构建会明确标注预发布。
        下载文件夹可在设置中更改；后端仍安装到启动器目录下的 llama 文件夹，可能覆盖旧版，请先停止服务。CUDA 版本会同时下载对应版本的运行库。
        刷新列表不会自动安装后端；显卡、驱动与量化兼容范围请以对应发行说明为准。
        </p>
        """
        )

        return UiCol(
            description,
            UiHLine(),
            select_download_src,
            current_version_hint,
            self._catalog_controls(),
            self.llamacpp_table,
        )

    def _create_download_progress_section(self):
        self.download_progress_layout = UiCol()
        self.download_progress_layout.addStretch()
        return self.download_progress_layout

    def _start_download_task(self, new_task: DownloadTask, on_finish):
        for task in self.download_tasks:
            if task.state == DownloadTaskState.RUNNING and task.name == new_task.name:
                InfoBar.warning(
                    title=f"{new_task.filename}已在下载中",
                    content="",
                    parent=self,
                )
                return False

        new_task.directory = os.path.abspath(SETTING.download_path or CURRENT_DIR)
        if os.path.exists(new_task.path):
            if not MessageBox("替换已有文件", f"下载并校验成功后将替换：\n{new_task.path}", self).exec():
                return False
        self.download_tasks.append(new_task)

        progress_bar = ProgressBar()
        status_label = QLabel("下载中")
        cancel_button = PushButton("取消下载")
        self.download_progress_layout.insertLayout(
            0,
            UiCol(
                QLabel(f"<b>{new_task.name}</b>"),
                QLabel(new_task.path),
                progress_bar,
                UiRow(status_label, None, (cancel_button, 0)),
            ),
        )

        def on_error(error_message):
            new_task.state = DownloadTaskState.ERROR
            status_label.setText("下载失败")
            cancel_button.setEnabled(False)
            logging.error(f"下载失败 {error_message}")
            QApplication.processEvents()  # 确保UI更新
            UiInfoBarError(self, f"{new_task.name}下载失败", content=f"{error_message}")

        def on_success():
            cancel_button.setEnabled(False)
            on_finish()
            status_label.setText("完成" if new_task.state == DownloadTaskState.SUCCESS else "处理失败")

        def on_cancel():
            thread.stop()
            new_task.state = DownloadTaskState.ERROR
            status_label.setText("已取消")
            cancel_button.setEnabled(False)

        thread = DownloadThread(new_task.url, new_task.path, new_task.expected_sha256)
        thread.sig_progress.connect(progress_bar.setValue)
        thread.sig_success.connect(on_success)
        thread.sig_error.connect(on_error)
        cancel_button.clicked.connect(on_cancel)
        thread.start()

        self.download_threads.append(thread)

        logging.info(f"开始下载: URL={new_task.url}, 文件名={new_task.filename}")
        UiInfoBarSuccess(self, f"{new_task.name}开始下载，请在下载进度页面查看进度")
        return True

    def _update_current_llamacpp_version(self):
        version = get_llamacpp_version(os.path.join(CURRENT_DIR, "llama"))
        if version:
            self.label_current_llamacpp_version.setText(f"b{version}")
        else:
            self.label_current_llamacpp_version.setText("未检测到")

    def start_download_sakura(self, sakura: Sakura):
        src = self.sakura_download_src
        task = DownloadTask(
            name="Sakura模型",
            url=sakura.download_links[src],
            filename=sakura.filename,
            expected_sha256=sakura.sha256,
        )

        def on_download_sakura_finish():
            task.state = DownloadTaskState.SUCCESS
            paths = [path.strip() for path in SETTING.model_search_paths.splitlines() if path.strip()]
            if task.directory != CURRENT_DIR and task.directory not in paths:
                SETTING.set_value("model_search_paths", "\n".join(paths + [task.directory]))
            UiInfoBarSuccess(self, f"{task.name}下载并校验成功")

        self._start_download_task(task, on_finish=on_download_sakura_finish)

    def start_download_cudart(self, cudart=None):
        src = self.llamacpp_download_src
        cudart = cudart or LLAMACPP_LIST.CUDART
        task = DownloadTask(
            name="CUDA-RT",
            url=cudart["download_links"][src],
            filename=cudart["filename"],
        )

        def on_download_cudart_finish():
            file_path = task.path
            try:
                unzip_llamacpp(CURRENT_DIR, file_path)
                task.state = DownloadTaskState.SUCCESS
                UiInfoBarSuccess(self, f"{task.name}下载成功")
            except Exception as e:
                task.state = DownloadTaskState.ERROR
                UiInfoBarError(self, f"{task.name}解压失败", content=str(e))
            finally:
                # 无论解压是否成功，都删除原始zip文件
                if os.path.exists(file_path):
                    os.remove(file_path)

        self._start_download_task(task, on_finish=on_download_cudart_finish)

    def start_download_llamacpp(self, llamacpp: Llamacpp):
        src = self.llamacpp_download_src
        task = DownloadTask(
            name="Llamacpp",
            url=llamacpp.download_links[src],
            filename=llamacpp.filename,
        )

        def on_download_llamacpp_finish():
            file_path = task.path
            try:
                unzip_llamacpp(CURRENT_DIR, file_path)
                task.state = DownloadTaskState.SUCCESS
                UiInfoBarSuccess(self, f"{task.name}下载成功")
                self._update_current_llamacpp_version()
            except Exception as e:
                task.state = DownloadTaskState.ERROR
                UiInfoBarError(self, f"{task.name}解压失败", content=str(e))
            finally:
                # 无论解压是否成功，都删除原始zip文件
                if os.path.exists(file_path):
                    os.remove(file_path)

        started = self._start_download_task(task, on_finish=on_download_llamacpp_finish)

        if started is not False and llamacpp.require_cuda:
            self.start_download_cudart(llamacpp.cudart)

    def start_download_launcher(self, version: str):
        filename = (f"Sakura_Launcher_GUI_macOS_{version}.zip" if sys.platform == "darwin"
                    else f"Sakura_Launcher_GUI_{version}.exe")
        url = f"https://github.com/{LAUNCHER_REPOSITORY}/releases/download/{version}/{filename}"
        if self.llamacpp_download_src == "GHProxy":
            url = f"https://{GHPROXY_URL}/" + url

        task = DownloadTask(
            name="Sakura启动器",
            url=url,
            filename=filename,
        )

        def on_finish():
            task.state = DownloadTaskState.SUCCESS
            UiInfoBarSuccess(self, f"{task.name}下载成功")

        self._start_download_task(task, on_finish=on_finish)
