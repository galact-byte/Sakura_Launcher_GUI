from dataclasses import dataclass
from enum import Enum
import logging
import os
import json
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
)

from .common import CURRENT_DIR, get_resource_path, GHPROXY_URL
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


class DownloadThread(QThread):
    sig_progress = Signal(int)
    sig_success = Signal()
    sig_error = Signal(str)

    def __init__(self, url, filename):
        super().__init__()
        self.url = url
        self.filename = filename
        self._is_finished = False

    def run(self):
        try:
            logging.info(f"开始下载: {self.url} => {self.filename}")
            response = requests.get(self.url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            block_size = 1024  # 1 KB
            downloaded_size = 0

            file_path = os.path.join(CURRENT_DIR, self.filename)
            with open(file_path, "wb") as file:
                for data in response.iter_content(block_size):
                    size = file.write(data)
                    downloaded_size += size
                    if total_size > 0:
                        progress = int((downloaded_size / total_size) * 100)
                        self.sig_progress.emit(progress)

            logging.info(f"下载完成: {self.filename}")

            if not self._is_finished:
                self._is_finished = True
                self.sig_success.emit()
        except requests.RequestException as e:
            error_msg = f"下载出错: {str(e)}"
            logging.info(error_msg)
            self.sig_error.emit(error_msg)
        except IOError as e:
            error_msg = f"文件写入错误: {str(e)}"
            logging.info(error_msg)
            self.sig_error.emit(error_msg)
        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            logging.info(error_msg)
            self.sig_error.emit(error_msg)

    def safe_disconnect(self):
        logging.info("正在断开下载线程的所有信号连接")
        try:
            self.sig_progress.disconnect()
            logging.info("断开 progress 信号")
        except TypeError:
            pass
        try:
            self.sig_success.disconnect()
            logging.info("断开 finished 信号")
        except TypeError:
            pass
        try:
            self.sig_error.disconnect()
            logging.info("断开 error 信号")
        except TypeError:
            pass
        logging.info("下载线程的所有信号已断开")

    def stop(self):
        logging.info("正在停止下载线程")
        self.terminate()
        self.wait()
        self._is_finished = True
        logging.info("下载线程已停止")


class DownloadSection(QFrame):
    llamacpp_download_src = LLAMACPP_LIST.DOWNLOAD_SRC[0]
    sakura_download_src = SAKURA_LIST.DOWNLOAD_SRC[0]
    download_tasks: List[DownloadTask] = []
    download_threads: List[QThread] = []

    def __init__(self, title):
        super().__init__()
        self.setObjectName(title.replace(" ", "-"))
        self.refresh_buttons = []
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
        <p>您可以在这里下载不同版本的模型，模型会保存到启动器所在的目录。如果启动器无法下载，您也可以手动从<a href="https://huggingface.co/SakuraLLM/">Hugging Face镜像站</a>下载模型，将下载的gguf文件放到启动器所在文件夹下即可。</p>
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
        下载后会安装到启动器目录下的 llama 文件夹，可能覆盖旧版，请先停止服务。CUDA 版本会同时下载对应版本的运行库。
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
                return

        self.download_tasks.append(new_task)

        progress_bar = ProgressBar()
        self.download_progress_layout.insertLayout(
            0,
            UiCol(
                QLabel(f"<b>{new_task.name}</b>"),
                QLabel(new_task.filename),
                progress_bar,
            ),
        )

        def on_error(error_message):
            new_task.state = DownloadTaskState.ERROR
            logging.error(f"下载失败 {error_message}")
            QApplication.processEvents()  # 确保UI更新
            UiInfoBarError(self, f"{new_task.name}下载失败", content=f"{error_message}")

        thread = DownloadThread(new_task.url, new_task.filename)
        thread.sig_progress.connect(progress_bar.setValue)
        thread.sig_success.connect(on_finish)
        thread.sig_error.connect(on_error)
        thread.start()

        self.download_threads.append(thread)

        logging.info(f"开始下载: URL={new_task.url}, 文件名={new_task.filename}")
        UiInfoBarSuccess(self, f"{new_task.name}开始下载，请在下载进度页面查看进度")

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
        )

        def on_download_sakura_finish():
            file_path = os.path.join(CURRENT_DIR, task.filename)
            if sakura.check_sha256(file_path):
                task.state = DownloadTaskState.SUCCESS
                UiInfoBarSuccess(self, f"{task.name}下载成功")
            else:
                task.state = DownloadTaskState.ERROR
                UiInfoBarError(self, f"{task.name}校验失败")
                os.remove(file_path)  # 删除校验失败的文件

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
            file_path = os.path.join(CURRENT_DIR, task.filename)
            try:
                task.state = DownloadTaskState.SUCCESS
                unzip_llamacpp(CURRENT_DIR, task.filename)
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
            file_path = os.path.join(CURRENT_DIR, task.filename)
            try:
                task.state = DownloadTaskState.SUCCESS
                unzip_llamacpp(CURRENT_DIR, task.filename)
                UiInfoBarSuccess(self, f"{task.name}下载成功")
                self._update_current_llamacpp_version()
            except Exception as e:
                task.state = DownloadTaskState.ERROR
                UiInfoBarError(self, f"{task.name}解压失败", content=str(e))
            finally:
                # 无论解压是否成功，都删除原始zip文件
                if os.path.exists(file_path):
                    os.remove(file_path)

        self._start_download_task(task, on_finish=on_download_llamacpp_finish)

        if llamacpp.require_cuda:
            self.start_download_cudart(llamacpp.cudart)

    def start_download_launcher(self, version: str):
        filename = f"Sakura_Launcher_GUI_{version}.exe"
        url = f"https://github.com/PiDanShouRouZhouXD/Sakura_Launcher_GUI/releases/download/{version}/{filename}"
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
