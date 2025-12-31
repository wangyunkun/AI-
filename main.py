import sys
import os
import json
import time
import re
import traceback
import ssl
from typing import Any, Dict, List, Optional, Tuple

# === Android 适配导入 ===
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QPointF, QRectF,
    QBuffer, QByteArray, QIODevice, QSize
)
from PyQt6.QtGui import (
    QPixmap, QColor, QAction, QPainter, QPen, QFont,
    QImage, QBrush, QIcon, QKeySequence
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QSplitter,
    QScrollArea, QFrame, QFileDialog, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QComboBox, QToolBar,
    QTabWidget, QTextEdit, QGroupBox, QDialogButtonBox, QInputDialog,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsTextItem, QGraphicsItem, QMenu
)

import httpx
from openai import OpenAI
import certifi # 解决 Android SSL 问题

# ================= 1. 全局配置与默认值 =================

APP_NAME = "AIHomeworkGrader"

# 默认提示词配置
DEFAULT_PROMPTS = {
    "📝 通用作业批改": """你是一位全科教师。请识别图片中的题目并批改。
要求：
1. 识别每一道题。
2. 判断对错 (Correct/Wrong)。
3. 若错，提供正确答案和简要解析。
4. **必须**返回纯 JSON 格式，不要包含 Markdown 标记。

JSON 格式示例：
[
  {
    "question_id": "1",
    "status": "Wrong",
    "student_answer": "...",
    "correct_answer": "...",
    "explanation": "...",
    "bbox": [xmin, ymin, xmax, ymax]
  }
]""",
    "🧮 理科 (数学/物理)": """你是一位理科专家。请检查图片中的计算过程和逻辑。
核心任务：
1. 识别题目和手写过程。
2. **一步步检查**运算是否正确。
3. 如果中间步骤错误，在 explanation 中指出具体哪一步错了。
4. **必须**返回纯 JSON 格式。
JSON 格式同上。bbox 为题目区域坐标。""",
    "🔤 英语 (语法/拼写)": """你是一位资深英语教师。请检查图片中的单词拼写和语法。
核心任务：
1. 识别填空、作文或句子。
2. 检查拼写错误、时态错误、语法错误。
3. 如果错误，correct_answer 给出修正后的完整单词或句子。
4. **必须**返回纯 JSON 格式。
JSON 格式同上。"""
}

DEFAULT_PROVIDER_PRESETS = {
    "阿里百炼 (Qwen-VL-Max)": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-vl-max"},
    "阿里百炼 (Qwen-VL-Plus)": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-vl-plus"},
    "OpenAI (GPT-4o)": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o"},
    "自定义 (Custom)": {"base_url": "", "model": ""}
}

# ================= 2. 核心逻辑与工具类 =================

class ConfigManager:
    # [修改] 使用类变量在内存中暂存配置，不写入文件
    _runtime_config = None

    @staticmethod
    def get_default_config():
        return {
            "current_provider": "阿里百炼 (Qwen-VL-Max)",
            "api_key": "",
            "last_prompt": list(DEFAULT_PROMPTS.keys())[0],
            "custom_provider_settings": {"base_url": "", "model": ""},
            "prompts": DEFAULT_PROMPTS.copy(),
        }

    @classmethod
    def load(cls):
        # [修改] 仅从内存加载，如果未初始化则返回默认值
        if cls._runtime_config is None:
            cls._runtime_config = cls.get_default_config()
        return cls._runtime_config

    @classmethod
    def save(cls, config):
        # [修改] 仅更新内存变量，不执行文件 I/O
        cls._runtime_config = config
        # print("Config updated in memory (not saved to file).")

class ImageUtils:
    @staticmethod
    def compress_image_to_base64(image_path, max_dim=1600, max_size_mb=3):
        img = QImage(image_path)
        if img.isNull(): return None, 1.0

        orig_w = img.width()
        scale_ratio = 1.0

        if img.width() > max_dim or img.height() > max_dim:
            img = img.scaled(max_dim, max_dim, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            scale_ratio = orig_w / img.width()

        quality = 90
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)

        while quality > 10:
            ba.clear()
            buf.seek(0)
            img.save(buf, "JPEG", quality)
            if ba.size() <= max_size_mb * 1024 * 1024:
                break
            quality -= 10

        return ba.toBase64().data().decode(), scale_ratio

def parse_ai_response(raw):
    try:
        text = raw.strip()
        match = re.search(r"```json(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        else:
            match = re.search(r"```(.*?)```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()
            elif text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]

        text = text.strip()
        text = text.replace("None", "null").replace("True", "true").replace("False", "false")
        data = json.loads(text)
        if isinstance(data, dict): data = [data]

        normalized = []
        for item in data:
            if not isinstance(item, dict): continue
            bbox = item.get("bbox")
            if bbox and isinstance(bbox, list) and len(bbox) == 4:
                try:
                    bbox = [float(x) for x in bbox]
                except:
                    bbox = None
            else:
                bbox = None

            normalized.append({
                "status": item.get("status", "Wrong"),
                "question_id": str(item.get("question_id", "")),
                "student_answer": str(item.get("student_answer", "")),
                "correct_answer": str(item.get("correct_answer", "")),
                "explanation": str(item.get("explanation", "")),
                "bbox": bbox
            })
        return normalized, None
    except json.JSONDecodeError as e:
        err_msg = str(e)
        if "Unterminated string" in err_msg or "Expecting value" in err_msg:
            return [], f"解析失败：AI 回复被截断。\n建议: 减少图片内容或检查 token 限制。\n错误: {err_msg}"
        return [], f"JSON 格式错误: {err_msg}\n片段: {raw[:100]}..."
    except Exception as e:
        return [], f"未知解析错误: {str(e)}"

# ================= 3. 画板组件 =================

class EditableTextItem(QGraphicsTextItem):
    def __init__(self, text, parent=None, callback=None):
        super().__init__(text, parent)
        self.callback = callback
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setDefaultTextColor(QColor("#D32F2F"))
        self.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            self.setFocus()
            super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        if self.callback: self.callback()
        super().focusOutEvent(event)

class AnnotatableImageView(QGraphicsView):
    annotation_changed = pyqtSignal()
    TOOL_NONE = "none"
    TOOL_RECT = "rect"
    TOOL_TEXT = "text"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self._pix_item = QGraphicsPixmapItem()
        self._pix_item.setZValue(-1000)
        self.scene.addItem(self._pix_item)

        self._temp_rect_item = QGraphicsRectItem()
        self._temp_rect_item.setPen(QPen(QColor("#2196F3"), 2, Qt.PenStyle.DashLine))
        self._temp_rect_item.setZValue(5000)
        self._temp_rect_item.hide()
        self.scene.addItem(self._temp_rect_item)

        self._highlight_item = QGraphicsRectItem()
        self._highlight_item.setPen(QPen(QColor("#FFEB3B"), 5, Qt.PenStyle.SolidLine))
        self._highlight_item.setBrush(QBrush(QColor(255, 235, 59, 50)))
        self._highlight_item.setZValue(9999)
        self._highlight_item.hide()
        self.scene.addItem(self._highlight_item)

        self._tool = self.TOOL_NONE
        self._dragging = False
        self._start_pt = None
        self._current_color = "#FF0000"

        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def set_image(self, path):
        if not path or not os.path.exists(path):
            self._pix_item.setPixmap(QPixmap())
            return
        image = QImage(path)
        if image.isNull(): return
        self._pix_item.setPixmap(QPixmap.fromImage(image))
        self.scene.setSceneRect(QRectF(0, 0, image.width(), image.height()))
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_tool(self, tool):
        self._tool = tool
        if tool == self.TOOL_NONE:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if isinstance(item, EditableTextItem):
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                super().mousePressEvent(event)
                return

            if self._tool != self.TOOL_NONE:
                self._dragging = True
                self._start_pt = self.mapToScene(event.position().toPoint())
                if self._tool == self.TOOL_RECT:
                    self._temp_rect_item.setRect(QRectF(self._start_pt, self._start_pt))
                    self._temp_rect_item.show()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self._dragging and self._tool == self.TOOL_RECT and self._start_pt:
            cur_pt = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._start_pt, cur_pt).normalized()
            self._temp_rect_item.setRect(rect)

    def mouseReleaseEvent(self, event):
        if self._dragging and self._tool != self.TOOL_NONE:
            end_pt = self.mapToScene(event.position().toPoint())
            self._finish_drawing(self._start_pt, end_pt)
            self._dragging = False
            self._temp_rect_item.hide()

        super().mouseReleaseEvent(event)
        if self._tool == self.TOOL_NONE and not self.scene.focusItem():
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def _finish_drawing(self, start, end):
        if not start or not end: return
        if (start - end).manhattanLength() < 5 and self._tool != self.TOOL_TEXT: return

        data = None
        if self._tool == self.TOOL_RECT:
            rect = QRectF(start, end).normalized()
            data = {"type": "rect", "bbox": [rect.left(), rect.top(), rect.right(), rect.bottom()], "color": self._current_color}
        elif self._tool == self.TOOL_TEXT:
            text, ok = QInputDialog.getText(self, "输入", "批注内容:")
            if ok and text:
                data = {"type": "text", "pos": [end.x(), end.y()], "text": text, "color": self._current_color, "font_size": 36}

        if data:
            self._create_item(data)
            self.annotation_changed.emit()

    def _create_item(self, data):
        t = data.get("type")
        color = QColor(data.get("color", "#FF0000"))

        item = None
        if t == "text":
            item = EditableTextItem(data.get("text", ""), callback=lambda: self.annotation_changed.emit())
            font = QFont("Microsoft YaHei")
            font.setPointSize(int(data.get("font_size", 36)))
            font.setBold(True)
            item.setFont(font)
            item.setDefaultTextColor(color)
            item.setPos(*data.get("pos"))
        elif t == "rect":
            bbox = data.get("bbox")
            if bbox and len(bbox) == 4:
                rect = QRectF(QPointF(bbox[0], bbox[1]), QPointF(bbox[2], bbox[3])).normalized()
                item = QGraphicsRectItem(rect)
                pen = QPen(color, 4)
                item.setPen(pen)
                item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

        if item:
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.scene.addItem(item)
            return item

    def set_annotations(self, anns):
        self.blockSignals(True)
        for item in list(self.scene.items()):
            if item not in [self._pix_item, self._highlight_item, self._temp_rect_item]:
                self.scene.removeItem(item)
        if anns:
            for a in anns: self._create_item(a)
        self.blockSignals(False)

    def get_annotations(self):
        anns = []
        for item in self.scene.items(Qt.SortOrder.AscendingOrder):
            if item in [self._pix_item, self._highlight_item, self._temp_rect_item]: continue
            raw = item.data(Qt.ItemDataRole.UserRole)
            if not raw: continue
            data = raw.copy()
            if isinstance(item, QGraphicsTextItem):
                data["text"] = item.toPlainText()
                data["pos"] = [item.pos().x(), item.pos().y()]
            elif isinstance(item, QGraphicsRectItem):
                r = item.sceneBoundingRect()
                data["bbox"] = [r.left(), r.top(), r.right(), r.bottom()]
            anns.append(data)
        return anns

    def highlight_bbox(self, bbox, active):
        if not bbox or not active:
            self._highlight_item.hide()
        else:
            rect = QRectF(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])
            self._highlight_item.setRect(rect)
            self._highlight_item.show()

    def zoom_to_bbox(self, bbox):
        if not bbox: return
        rect = QRectF(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.scale(0.85, 0.85)

# ================= 4. UI 组件：结果卡片 =================

class SolutionCard(QFrame):
    clicked = pyqtSignal(list) # 手机上改为点击触发

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item_data = item
        self.bbox = item.get("bbox")
        self.init_ui()

    def init_ui(self):
        status = self.item_data.get("status", "Wrong")
        is_correct = "Correct" in status or "Right" in status

        bg_color = "#E8F5E9" if is_correct else "#FFEBEE"
        border_color = "#4CAF50" if is_correct else "#F44336"
        icon = "✔" if is_correct else "✘"

        self.setStyleSheet(f"""
            QFrame {{ 
                background-color: {bg_color}; 
                border-left: 5px solid {border_color}; 
                border-radius: 4px; margin-bottom: 5px; 
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        header = QHBoxLayout()
        lbl_status = QLabel(f"<b>{icon} 题号 {self.item_data.get('question_id', 'N/A')}</b>")
        lbl_status.setStyleSheet(f"color: {border_color}; font-size: 16px; border:none;")
        header.addWidget(lbl_status)
        header.addStretch()
        layout.addLayout(header)

        if not is_correct:
            self.add_field(layout, "学生答案:", self.item_data.get('student_answer', ''))
            self.add_field(layout, "正确答案:", self.item_data.get('correct_answer', ''), color="#D32F2F")

        expl = self.item_data.get('explanation', '')
        if expl:
            self.add_field(layout, "解析:", expl, is_long=True)

    def add_field(self, layout, label_text, content, color="#000000", is_long=False):
        if not content: return
        h = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet("border:none; font-weight:bold; color: #555;")
        lbl.setFixedWidth(70)
        lbl.setAlignment(Qt.AlignmentFlag.AlignTop)

        if is_long:
            val = QTextEdit(content)
            val.setReadOnly(True)
            val.setStyleSheet(f"border:none; background:transparent; color:{color};")
            val.setMaximumHeight(80)
        else:
            val = QLabel(content)
            val.setWordWrap(True)
            val.setStyleSheet(f"border:none; color:{color};")

        h.addWidget(lbl)
        h.addWidget(val)
        layout.addLayout(h)

    def mousePressEvent(self, event):
        if self.bbox: self.clicked.emit(self.bbox)
        super().mousePressEvent(event)

# ================= 5. AI 工作线程 =================

class AnalysisWorker(QThread):
    result_ready = pyqtSignal(str, dict)

    def __init__(self, task, config):
        super().__init__()
        self.task = task
        self.config = config

    def run(self):
        try:
            b64_str, scale_ratio = ImageUtils.compress_image_to_base64(self.task["path"])
            if not b64_str: raise Exception("图片读取或处理失败")

            api_key = self.config.get("api_key")
            provider = self.config["current_provider"]

            if "自定义" in provider:
                base_url = self.config["custom_provider_settings"]["base_url"]
                model = self.config["custom_provider_settings"]["model"]
            else:
                setting = DEFAULT_PROVIDER_PRESETS.get(provider, {})
                base_url = setting.get("base_url")
                model = setting.get("model")

            prompt_title = self.config.get("last_prompt", list(self.config["prompts"].keys())[0])
            sys_prompt = self.config["prompts"].get(prompt_title, "")

            # [Android 修复] 添加 certifi 上下文，防止 SSL 证书报错
            ssl_context = ssl.create_default_context(cafile=certifi.where())

            client = OpenAI(
                api_key=api_key, 
                base_url=base_url, 
                http_client=httpx.Client(verify=ssl_context)
            )

            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}},
                        {"type": "text", "text": "请按 JSON 格式批改作业。"}
                    ]}
                ],
                temperature=0.1,
                max_tokens=4096
            )

            content = resp.choices[0].message.content
            data, err = parse_ai_response(content)

            if data and scale_ratio != 1.0:
                for item in data:
                    if item.get("bbox"):
                        old_b = item["bbox"]
                        item["bbox"] = [
                            int(old_b[0] * scale_ratio),
                            int(old_b[1] * scale_ratio),
                            int(old_b[2] * scale_ratio),
                            int(old_b[3] * scale_ratio)
                        ]

            self.result_ready.emit(self.task["id"], {"ok": True if not err else False, "data": data, "error": err})

        except Exception as e:
            traceback.print_exc()
            self.result_ready.emit(self.task["id"], {"ok": False, "error": str(e), "data": []})

# ================= 6. 设置弹窗 =================

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("设置")
        # 手机全屏化 Dialog 体验更好
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        tab_api = QWidget()
        form_layout = QFormLayout(tab_api)

        self.cbo_prov = QComboBox()
        self.cbo_prov.addItems(DEFAULT_PROVIDER_PRESETS.keys())
        self.cbo_prov.setCurrentText(self.config.get("current_provider"))
        self.cbo_prov.setFixedHeight(50) # 增大触摸区域

        self.txt_key = QLineEdit(self.config.get("api_key", ""))
        self.txt_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_key.setPlaceholderText("sk-...")
        self.txt_key.setFixedHeight(50)

        form_layout.addRow("服务商:", self.cbo_prov)
        form_layout.addRow("API Key:", self.txt_key)
        form_layout.addRow(QLabel("⚠️ 注意：由于安全策略，API Key 仅在本次运行有效，重启 App 需重新输入。"))

        tab_prompt = QWidget()
        prompt_layout = QVBoxLayout(tab_prompt)

        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("模式:"))
        self.cbo_prompt_select = QComboBox()
        self.cbo_prompt_select.addItems(self.config["prompts"].keys())
        self.cbo_prompt_select.currentTextChanged.connect(self.load_prompt_text)
        self.cbo_prompt_select.setFixedHeight(50)
        h_layout.addWidget(self.cbo_prompt_select)
        prompt_layout.addLayout(h_layout)

        self.txt_prompt_content = QTextEdit()
        prompt_layout.addWidget(self.txt_prompt_content)

        btn_save_prompt = QPushButton("暂存当前 Prompt 修改")
        btn_save_prompt.setFixedHeight(50)
        btn_save_prompt.clicked.connect(self.save_current_prompt)
        prompt_layout.addWidget(btn_save_prompt)

        self.tabs.addTab(tab_api, "API 设置")
        self.tabs.addTab(tab_prompt, "提示词")
        layout.addWidget(self.tabs)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        for btn in btns.buttons():
            btn.setMinimumHeight(60) # 增大底部按钮
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.load_prompt_text(self.cbo_prompt_select.currentText())

    def load_prompt_text(self, key):
        self.txt_prompt_content.setText(self.config["prompts"].get(key, ""))

    def save_current_prompt(self):
        key = self.cbo_prompt_select.currentText()
        val = self.txt_prompt_content.toPlainText()
        self.config["prompts"][key] = val
        QMessageBox.information(self, "已暂存", f"【{key}】的提示词已更新(本次运行有效)")

    def get_data(self):
        self.config["current_provider"] = self.cbo_prov.currentText()
        self.config["api_key"] = self.txt_key.text()
        return self.config

# ================= 7. 主窗口 =================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager.load()
        self.tasks = []
        self.current_task_id = None
        self.workers = {}

        self.init_ui()
        self.image_view.annotation_changed.connect(self.save_current_annotations)

    def init_ui(self):
        self.setWindowTitle("AI 作业批改 (移动版)")
        self.showMaximized() # 手机端默认最大化

        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(48, 48)) # 增大图标适配手指
        self.addToolBar(toolbar)

        btn_add = QAction("➕ 导入", self)
        btn_add.triggered.connect(self.add_images)
        
        btn_run = QAction("▶ 批改", self)
        btn_run.triggered.connect(self.start_grading)

        # [修改] 移除了“导出图片”按钮

        btn_setting = QAction("⚙ 设置", self)
        btn_setting.triggered.connect(self.open_settings)

        self.cbo_prompt = QComboBox()
        self.update_prompt_combo()
        self.cbo_prompt.setCurrentText(self.config.get("last_prompt", ""))
        self.cbo_prompt.currentTextChanged.connect(self.on_prompt_changed)
        self.cbo_prompt.setFixedWidth(200)
        self.cbo_prompt.setFixedHeight(40)

        toolbar.addAction(btn_add)
        toolbar.addAction(btn_run)
        toolbar.addSeparator()
        toolbar.addWidget(self.cbo_prompt)
        toolbar.addSeparator()
        toolbar.addAction(btn_setting)

        # 主布局
        splitter = QSplitter(Qt.Orientation.Vertical) # 手机竖屏更适合垂直分割

        # 上半部分：图片与工具栏
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        tool_layout = QHBoxLayout()
        self.btn_auto = QPushButton("🤖 自动标记")
        self.btn_rect = QPushButton("⬜ 画框")
        self.btn_text = QPushButton("T 写字")
        self.btn_clear = QPushButton("🧹 清除")
        
        for b in [self.btn_auto, self.btn_rect, self.btn_text, self.btn_clear]:
            b.setMinimumHeight(45)

        self.btn_rect.setCheckable(True)
        self.btn_text.setCheckable(True)
        self.btn_auto.clicked.connect(self.auto_annotate)
        self.btn_rect.clicked.connect(lambda: self.select_tool("rect"))
        self.btn_text.clicked.connect(lambda: self.select_tool("text"))
        self.btn_clear.clicked.connect(lambda: self.image_view.set_annotations([]))

        tool_layout.addWidget(self.btn_auto)
        tool_layout.addWidget(self.btn_rect)
        tool_layout.addWidget(self.btn_text)
        tool_layout.addWidget(self.btn_clear)

        self.image_view = AnnotatableImageView()
        top_layout.addLayout(tool_layout)
        top_layout.addWidget(self.image_view)

        # 下半部分：任务列表与详情
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        self.info_tabs = QTabWidget()
        self.info_tabs.setStyleSheet("QTabBar::tab { height: 40px; width: 100px; }")

        # 任务列表页
        list_container = QWidget()
        lc_layout = QVBoxLayout(list_container)
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self.on_list_click)
        self.btn_clear_list = QPushButton("清空列表")
        self.btn_clear_list.setFixedHeight(40)
        self.btn_clear_list.clicked.connect(self.clear_task_list)
        lc_layout.addWidget(self.list_widget)
        lc_layout.addWidget(self.btn_clear_list)

        # 结果详情页
        self.scroll_area = QScrollArea()
        self.result_container = QWidget()
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.result_container)
        self.scroll_area.setWidgetResizable(True)

        self.info_tabs.addTab(list_container, "作业列表")
        self.info_tabs.addTab(self.scroll_area, "批改详情")
        
        bottom_layout.addWidget(self.info_tabs)

        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 6) # 图片占 60%
        splitter.setStretchFactor(1, 4) # 详情占 40%

        self.setCentralWidget(splitter)
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("请点击 ⚙ 设置 API Key 后开始")

    def update_prompt_combo(self):
        self.cbo_prompt.blockSignals(True)
        self.cbo_prompt.clear()
        self.cbo_prompt.addItems(self.config["prompts"].keys())
        self.cbo_prompt.blockSignals(False)

    def select_tool(self, tool_name):
        self.btn_rect.setChecked(tool_name == "rect")
        self.btn_text.setChecked(tool_name == "text")
        self.image_view.set_tool(tool_name)

    def add_images(self):
        # 注意：Android 上 QFileDialog 界面可能较简陋
        files, _ = QFileDialog.getOpenFileNames(self, "选择作业", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        for f in files:
            tid = str(time.time()) + os.path.basename(f)
            self.tasks.append({
                "id": tid, "path": f, "status": "waiting",
                "results": [], "annotations": []
            })
            item = QListWidgetItem(os.path.basename(f))
            item.setData(Qt.ItemDataRole.UserRole, tid)
            self.list_widget.addItem(item)
        if files:
            self.list_widget.setCurrentRow(self.list_widget.count()-1)
            self.on_list_click(self.list_widget.item(self.list_widget.count()-1))
            self.info_tabs.setCurrentIndex(0) # 切换到列表页

    def clear_task_list(self):
        self.tasks.clear()
        self.list_widget.clear()
        self.current_task_id = None
        self.image_view.set_image("")
        self.image_view.set_annotations([])
        while self.result_layout.count():
            child = self.result_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

    def on_prompt_changed(self, text):
        self.config["last_prompt"] = text
        # 内存更新，不保存文件

    def on_list_click(self, item):
        if not item: return
        tid = item.data(Qt.ItemDataRole.UserRole)
        self.current_task_id = tid
        task = next((t for t in self.tasks if t["id"] == tid), None)
        if task:
            self.image_view.set_image(task["path"])
            self.image_view.set_annotations(task.get("annotations", []))
            self.render_results(task)

    def save_current_annotations(self):
        if self.current_task_id:
            task = next(t for t in self.tasks if t["id"] == self.current_task_id)
            task["annotations"] = self.image_view.get_annotations()

    def start_grading(self):
        if not self.config.get("api_key"):
            QMessageBox.warning(self, "缺少 Key", "API Key 未配置或 App 重启已重置。\n请前往设置重新输入。")
            return

        has_task = False
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            tid = item.data(Qt.ItemDataRole.UserRole)
            task = next(t for t in self.tasks if t["id"] == tid)

            if task["status"] in ["waiting", "error"]:
                has_task = True
                task["status"] = "analyzing"
                item.setForeground(QColor("#1976D2"))

                worker = AnalysisWorker(task, self.config)
                worker.result_ready.connect(self.on_worker_done)
                self.workers[tid] = worker
                worker.start()

        if has_task:
            self.status_bar.showMessage("正在后台批改...")
        else:
            QMessageBox.information(self, "提示", "所有任务已完成。")

    def on_worker_done(self, tid, res):
        try:
            task = next(t for t in self.tasks if t["id"] == tid)
        except StopIteration:
            return

        list_item = None
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == tid:
                list_item = self.list_widget.item(i)
                break

        if res["ok"]:
            task["status"] = "done"
            task["results"] = res["data"]
            if list_item: list_item.setForeground(QColor("#2E7D32"))
            self.auto_annotate_task(task)
            if self.current_task_id == tid:
                self.render_results(task)
                self.image_view.set_annotations(task["annotations"])
                self.info_tabs.setCurrentIndex(1) # 自动跳转到详情页
                self.status_bar.showMessage(f"完成: {os.path.basename(task['path'])}")
        else:
            task["status"] = "error"
            if list_item: list_item.setForeground(QColor("#D32F2F"))
            QMessageBox.warning(self, "批改失败", f"{os.path.basename(task['path'])}:\n{res['error']}")

    def auto_annotate(self):
        if self.current_task_id:
            task = next(t for t in self.tasks if t["id"] == self.current_task_id)
            self.auto_annotate_task(task)
            self.image_view.set_annotations(task["annotations"])

    def auto_annotate_task(self, task):
        if not task.get("results"): return
        new_anns = []
        for item in task["results"]:
            bbox = item.get("bbox")
            if not bbox or len(bbox) != 4: continue

            h = abs(bbox[3] - bbox[1])
            font_size = max(24, min(int(h * 0.4), 80))

            status = item.get("status", "Wrong")
            is_correct = "Correct" in status or "Right" in status
            symbol = "✔" if is_correct else "✘"
            color = "#4CAF50" if is_correct else "#D32F2F"

            new_anns.append({
                "type": "text", "pos": [bbox[2], bbox[1]],
                "text": symbol, "color": color, "font_size": font_size
            })

            if not is_correct:
                ans = item.get("correct_answer", "")
                if ans and len(ans) < 10:
                    new_anns.append({
                        "type": "text", "pos": [bbox[2] + font_size, bbox[1]],
                        "text": ans, "color": color, "font_size": int(font_size * 0.6)
                    })
        task["annotations"] = new_anns

    def render_results(self, task):
        while self.result_layout.count():
            child = self.result_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        results = task.get("results", [])
        if not results:
            self.result_layout.addWidget(QLabel("暂无结果" if task["status"] != "analyzing" else "分析中..."))
            return

        for item in results:
            card = SolutionCard(item)
            # 移除 Hover，仅保留点击
            card.clicked.connect(self.image_view.zoom_to_bbox)
            self.result_layout.addWidget(card)

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.config = dlg.get_data()
            ConfigManager.save(self.config)
            self.update_prompt_combo()
            self.cbo_prompt.setCurrentText(self.config.get("last_prompt", ""))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 12) 
    app.setFont(font)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
