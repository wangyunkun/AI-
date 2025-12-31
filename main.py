ort flet as ft
import base64
import json
import threading
import os
import copy
from datetime import datetime
from openai import OpenAI

# ================= 1. 预设配置 =================
PROVIDER_PRESETS = {
    "阿里百炼 (Alibaba)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-vl-max",
        "api_key": ""
    },
    "硅基流动 (SiliconFlow)": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2-VL-72B-Instruct",
        "api_key": ""
    },
    "DeepSeek (官方)": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": ""
    },
    "火山引擎 (豆包)": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-pro-4k-vl",
        "api_key": ""
    },
    "自定义 (Custom)": {
        "base_url": "",
        "model": "",
        "api_key": ""
    }
}

DEFAULT_PROMPT = """你是一位拥有30年一线经验的**国家注册安全工程师**及**工程质量监理专家**。你的眼神如鹰隼般锐利，绝不放过任何一个细微的安全隐患、违规施工行为或工程质量通病。\r\n\r\n你的任务是审查施工现场照片，进行**“安全+质量”双维度的全方位扫描**。\r\n\r\n请按照以下逻辑顺序，对画面进行“像素级”的排查：\r\n\r\n### 第一优先级：危大工程与特种设备（高危安全核心）\r\n1. **起重吊装与机械**：\r\n   - **设备状态**：汽车吊/履带吊支腿是否完全伸出并垫实？吊臂下是否有人员逗留？钢丝绳是否有断丝/锈蚀？\r\n   - **违规作业**：是否违章用装载机/挖机吊装？是否有歪拉斜吊、超载？土方机械作业半径内是否有人？\r\n2. **深基坑与边坡**：\r\n   - **支护**：支护结构是否有变形、裂缝？是否有渗漏水现象？\r\n   - **临边**：基坑周边堆载是否过大？是否按规定设置防护栏杆及警示灯？\r\n\r\n### 第二优先级：主体结构与关键工艺（核心质量审查）\r\n1. **钢筋工程（隐蔽验收级审查）**：\r\n   - **绑扎与连接**：钢筋间距是否均匀？扎丝是否朝内？直螺纹套筒连接是否有露丝过长？搭接长度是否明显不足？\r\n   - **保护层与锈蚀**：是否垫设保护层垫块？钢筋是否有严重锈蚀（老锈）或油污？\r\n2. **混凝土工程（外观质量审查）**：\r\n   - **缺陷**：是否有蜂窝、麻面、孔洞、露筋、夹渣等外观质量缺陷？\r\n   - **养护**：楼板/柱体是否覆盖薄膜或浇水养护？是否有早期干缩裂缝？\r\n   - **缝隙处理**：施工缝留置是否规范？是否存在烂根现象？\r\n3. **模板工程（安全+质量）**：\r\n   - **稳固性**：立杆是否垂直？扫地杆、剪刀撑是否缺失（安全）？\r\n   - **拼缝**：模板拼缝是否严密？是否有漏浆痕迹（质量）？对拉螺栓是否规范设置？\r\n\r\n### 第三优先级：二次结构与通用设施（工艺与防护）\r\n1. **砌体与墙体**：\r\n   - **灰缝**：砂浆是否饱满？是否存在瞎缝、通缝？顶砖是否按规范斜砌（倒八字）？\r\n   - **构造柱**：马牙槎留置是否标准（五退五进）？是否预留拉结筋？\r\n2. **脚手架与通道**：\r\n   - **规范性**：脚手板是否铺满且固定（探头板）？安全网是否破损或系挂不严？连墙件是否按规定设置？\r\n3. **临电与消防**：\r\n   - **用电**：“一机一闸一漏一箱”是否落实？电缆是否拖地/浸水？\r\n   - **动火**：气瓶间距是否足够？动火点旁是否有灭火器？是否配备接火斗？\r\n\r\n### 第四优先级：文明施工与成品保护（综合管理）\r\n1. **材料管理**：\r\n   - 钢筋/水泥是否离地堆放并覆盖（防雨防潮）？材料堆放是否杂乱无章？\r\n2. **作业环境**：\r\n   - 路面是否积水/泥泞？裸土是否覆盖（扬尘控制）？是否有大面积建筑垃圾未清理？\r\n3. **人员行为 (PPE)**：\r\n   - 安全帽（下颌带）、反光衣、高处作业安全带（高挂低用）是否佩戴齐全。\r\n\r\n---\r\n\r\n### 输出规则（极其重要）\r\n\r\n1. **引用标准（精准匹配）**：\r\n   - **安全类**：JGJ 33《建筑机械使用安全技术规程》、JGJ 59《建筑施工安全检查标准》、JGJ 130《扣件式钢管脚手架安全技术规范》。\r\n   - **质量类**：GB 50204《混凝土结构工程施工质量验收规范》、GB 50203《砌体结构工程施工质量验收规范》、GB 50666《混凝土结构工程施工规范》。\r\n2. **问题分类**：请明确标识问题是属于【安全】还是【质量】。\r\n3. **数量统计**：如果同一类问题出现多次，请合并为一条，说明数量。\r\n4. **宁严勿漏**：对于模糊不清的隐患，用“疑似”字样指出，提示人工复核。\r\n\r\n请返回纯净的 JSON 列表（无 Markdown 标记），格式如下：\r\n[\r\n    {\r\n        \"issue\": \"【安全】挖掘机作业半径内有2名工人违规穿越，且无人指挥\",\r\n        \"regulation\": \"违反《建筑机械使用安全技术规程》JGJ 33-2012 第x条\",\r\n        \"correction\": \"立即停止作业，设置警戒隔离区，配备专职指挥人员\"\r\n    },\r\n    {\r\n        \"issue\": \"【质量】剪力墙底部出现严重烂根，且局部有露筋现象\",\r\n        \"regulation\": \"违反《混凝土结构工程施工质量验收规范》GB 50204-2015 第8.2.1条\",\r\n        \"correction\": \"凿除松散混凝土，清洗干净后用高一等级微膨胀砂浆修补，并加强振捣管控\"\r\n    },\r\n    {\r\n        \"issue\": \"【工艺】砌体结构出现3处通缝，且灰缝饱满度目测不足80%\",\r\n        \"regulation\": \"违反《砌体结构工程施工质量验收规范》GB 50203-2011\",\r\n        \"correction\": \"拆除不规范砌体，重新砌筑，确保上下错缝及砂浆饱满度\"\r\n    }\r\n]\r\n\r\n如果未发现任何问题，返回 []
"""


class SafetyApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config = self.load_config()
        self.current_image_path = None
        self.current_data = []
        self.client = None

    def load_config(self):
        """读取配置"""
        default_config = {
            "current_provider": "阿里百炼 (Alibaba)",
            "system_prompt": DEFAULT_PROMPT,
            "providers": copy.deepcopy(PROVIDER_PRESETS)
        }
        try:
            if self.page.client_storage.contains_key("app_config"):
                saved = self.page.client_storage.get("app_config")
                if not saved or not isinstance(saved, dict):
                    return default_config
                if "providers" not in saved:
                    saved["providers"] = copy.deepcopy(PROVIDER_PRESETS)
                else:
                    for k, v in PROVIDER_PRESETS.items():
                        if k not in saved["providers"]:
                            saved["providers"][k] = v
                return saved
            else:
                return default_config
        except Exception as e:
            print(f"读取配置失败: {e}")
            return default_config

    def save_config_storage(self):
        """保存配置"""
        try:
            self.page.client_storage.set("app_config", self.config)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def init_client(self):
        p = self.config.get("current_provider")
        conf = self.config["providers"].get(p, {})
        if conf.get("api_key") and conf.get("base_url"):
            self.client = OpenAI(api_key=conf["api_key"], base_url=conf["base_url"])
            return True
        return False


def main(page: ft.Page):
    # ================= 页面设置 =================
    page.title = "普洱版纳质量安全部"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#f2f4f7"
    page.scroll = ft.ScrollMode.AUTO

    app = SafetyApp(page)

    # ================= 辅助功能：弹窗提示 =================
    def show_snack(message, color="green"):
        """封装更稳定的弹窗提示"""
        try:
            # 使用 page.open 是新版 Flet 更稳定的写法
            page.open(ft.SnackBar(ft.Text(message), bgcolor=color))
            page.update()
        except:
            # 兜底兼容旧版
            page.snack_bar = ft.SnackBar(ft.Text(message), bgcolor=color)
            page.snack_bar.open = True
            page.update()

    # ================= 详情抽屉 =================
    def show_bottom_sheet(item):
        bs_content.controls = [
            ft.Container(height=10),
            ft.Container(width=40, height=5, bgcolor=ft.Colors.GREY_300, border_radius=10,
                         alignment=ft.alignment.center),
            ft.Text("隐患详情", size=18, weight="bold", text_align="center"),
            ft.Divider(),
            ft.Text("⚠️ 隐患描述", color="red", weight="bold"),
            ft.Container(content=ft.Text(item.get("issue", ""), selectable=True), padding=10, bgcolor=ft.Colors.RED_50,
                         border_radius=6),
            ft.Container(height=10),
            ft.Text("⚖️ 依据规范", color="blue", weight="bold"),
            ft.Container(content=ft.Text(item.get("regulation", ""), selectable=True), padding=10,
                         bgcolor=ft.Colors.BLUE_50, border_radius=6),
            ft.Container(height=10),
            ft.Text("🛠️ 整改建议", color="green", weight="bold"),
            ft.Container(content=ft.Text(item.get("correction", ""), selectable=True), padding=10,
                         bgcolor=ft.Colors.GREEN_50, border_radius=6),
            ft.Container(height=30)
        ]
        bs.open = True
        page.update()

    bs_content = ft.Column(scroll=ft.ScrollMode.AUTO, tight=True)
    bs = ft.BottomSheet(content=ft.Container(content=bs_content, padding=20,
                                             border_radius=ft.border_radius.only(top_left=15, top_right=15)),
                        dismissible=True)
    page.overlay.append(bs)

    # ================= 列表渲染 =================
    result_column = ft.Column(spacing=10)

    def render_results(data):
        result_column.controls.clear()
        if not data:
            result_column.controls.append(
                ft.Container(content=ft.Text("暂无数据，请上传图片分析", color="grey"), alignment=ft.alignment.center,
                             padding=30))
        else:
            for i, item in enumerate(data):
                card = ft.Container(
                    bgcolor="white", padding=15, border_radius=10,
                    shadow=ft.BoxShadow(blur_radius=5, color=ft.Colors.BLACK12),
                    on_click=lambda e, d=item: show_bottom_sheet(d),
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.WARNING_ROUNDED, color="red"),
                            ft.Text(f"隐患 #{i + 1}", weight="bold", size=16),
                            ft.Container(expand=True),
                            ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color="grey")
                        ]),
                        ft.Text(item.get("issue", ""), max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Divider(height=5, color="transparent"),
                        ft.Text(item.get("regulation", "")[:20] + "...", size=12, color="grey")
                    ])
                )
                result_column.controls.append(card)
        page.update()

    # ================= UI 组件 =================
    status_txt = ft.Text("请配置 Key", color="grey", size=12)
    img_control = ft.Image(src="https://placehold.co/600x400?text=Preview", fit=ft.ImageFit.CONTAIN, expand=True,
                           border_radius=8)
    img_container = ft.Container(content=img_control, height=250, bgcolor=ft.Colors.BLACK12, border_radius=10,
                                 alignment=ft.alignment.center)

    # ================= 逻辑处理 =================
    def save_config_ui(e):
        p = dd_provider.value
        app.config["current_provider"] = p
        app.config["system_prompt"] = tf_prompt.value
        app.config["providers"][p]["base_url"] = tf_url.value.strip()
        app.config["providers"][p]["model"] = tf_model.value.strip()
        app.config["providers"][p]["api_key"] = tf_key.value.strip()

        if app.save_config_storage():
            status_txt.value = "✅ 配置已保存"
            show_snack("配置已保存，重启后依然有效", "green")
        else:
            status_txt.value = "❌ 保存失败"
            show_snack("配置保存失败", "red")

        page.close(dlg_settings)
        page.update()

    def refresh_settings(val):
        conf = app.config["providers"].get(val, {})
        tf_url.value = conf.get("base_url", "")
        tf_model.value = conf.get("model", "")
        tf_key.value = conf.get("api_key", "")
        page.update()

    def run_task(e):
        if not app.init_client():
            status_txt.value = "❌ 未配置API或Key"
            status_txt.color = "red"
            page.open(dlg_settings)
            page.update()
            return

        btn_analyze.disabled = True
        btn_analyze.text = "正在分析..."
        page.update()

        def task():
            try:
                p = app.config["current_provider"]
                if not app.current_image_path:
                    raise Exception("请先选择图片")

                with open(app.current_image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()

                resp = app.client.chat.completions.create(
                    model=app.config["providers"][p]["model"],
                    messages=[
                        {"role": "system", "content": app.config["system_prompt"]},
                        {"role": "user", "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": "找出所有隐患"}
                        ]}
                    ],
                    temperature=0.1
                )
                content = resp.choices[0].message.content.replace("```json", "").replace("```", "")
                s, e_idx = content.find('['), content.rfind(']') + 1
                data = json.loads(content[s:e_idx]) if s != -1 and e_idx != -1 else []
                app.current_data = data

                render_results(data)
                status_txt.value = "✅ 分析完成"
                status_txt.color = "green"
                btn_analyze.text = "重新分析"
                btn_analyze.disabled = False
                btn_copy.disabled = False
                page.update()
            except Exception as err:
                status_txt.value = f"❌ 出错: {str(err)[:20]}"
                status_txt.color = "red"
                btn_analyze.text = "重新分析"
                btn_analyze.disabled = False
                page.update()

        threading.Thread(target=task).start()

    def on_picked(e):
        if e.files:
            app.current_image_path = e.files[0].path
            img_control.src = e.files[0].path
            status_txt.value = "📸 图片已就绪"
            status_txt.color = "blue"
            btn_analyze.disabled = False
            page.update()

    # ================= 复制逻辑 (重写增强版) =================
    def copy_to_clipboard(e):
        """
        增强的复制功能：带异常捕获和强制提示
        """
        try:
            if not app.current_data:
                show_snack("没有可复制的数据，请先分析", "red")
                return

            # 构建纯文本报告
            text_report = "【普洱版纳区域质量安全检查报告】\n"
            text_report += f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            text_report += "-" * 20 + "\n"

            for i, item in enumerate(app.current_data):
                text_report += f"\n🔴 隐患 {i + 1}:\n"
                text_report += f"{item.get('issue', '无')}\n"
                text_report += f"⚖️ 规范: {item.get('regulation', '无')}\n"
                text_report += f"🛠️ 整改: {item.get('correction', '无')}\n"

            # 核心动作：写入剪贴板
            page.set_clipboard(text_report)

            # 成功提示
            show_snack("✅ 已复制！可直接去微信粘贴", "green")

        except Exception as err:
            # 失败提示
            show_snack(f"❌ 复制失败: {str(err)}", "red")
            print(f"Clipboard Error: {err}")

    # ================= 布局组装 =================
    dd_provider = ft.Dropdown(label="厂商", options=[ft.dropdown.Option(k) for k in PROVIDER_PRESETS],
                              value=app.config.get("current_provider"),
                              on_change=lambda e: refresh_settings(e.control.value))
    tf_key = ft.TextField(label="API Key", password=True)
    tf_url = ft.TextField(label="Base URL")
    tf_model = ft.TextField(label="Model Name")
    tf_prompt = ft.TextField(label="系统提示词", value=app.config.get("system_prompt"), multiline=True, min_lines=3)

    dlg_settings = ft.AlertDialog(title=ft.Text("API 设置"),
                                  content=ft.Column([dd_provider, tf_key, tf_url, tf_model, tf_prompt],
                                                    scroll=ft.ScrollMode.AUTO, height=350, width=300),
                                  actions=[ft.TextButton("保存配置", on_click=save_config_ui)])

    pick_dlg = ft.FilePicker(on_result=on_picked)
    page.overlay.append(pick_dlg)

    header = ft.Container(
        content=ft.Row([
            ft.Text("🛡️ 普洱版纳区域质量安全检查AI", size=18, weight="bold"),
            ft.Row([
                ft.IconButton(ft.Icons.SETTINGS, tooltip="设置", on_click=lambda e: page.open(dlg_settings)),
                ft.IconButton(ft.Icons.EXIT_TO_APP, tooltip="退出", icon_color="red", on_click=lambda e: os._exit(0))
            ])
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=15, bgcolor="white", border_radius=10, shadow=ft.BoxShadow(blur_radius=2, color=ft.Colors.BLACK12)
    )

    btn_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=15)
    btn_upload = ft.ElevatedButton("选图", icon=ft.Icons.IMAGE, on_click=lambda _: pick_dlg.pick_files(),
                                   style=btn_style)
    btn_analyze = ft.ElevatedButton("分析", icon=ft.Icons.AUTO_AWESOME, on_click=run_task, disabled=True,
                                    style=ft.ButtonStyle(bgcolor="blue", color="white", padding=15,
                                                         shape=ft.RoundedRectangleBorder(radius=8)))

    btn_copy = ft.ElevatedButton("复制结果", icon=ft.Icons.COPY, on_click=copy_to_clipboard, disabled=True,
                                 style=ft.ButtonStyle(color="green", padding=15,
                                                      shape=ft.RoundedRectangleBorder(radius=8)))

    layout = ft.ResponsiveRow([
        ft.Column(col={"xs": 12, "md": 5}, controls=[
            ft.Container(content=img_container, bgcolor="white", padding=10, border_radius=10),
            ft.Container(height=5),
            ft.Row([
                ft.Column([btn_upload], expand=1),
                ft.Column([btn_analyze], expand=1),
                ft.Column([btn_copy], expand=1),
            ]),
            ft.Container(content=status_txt, alignment=ft.alignment.center),
        ]),

        ft.Column(col={"xs": 12, "md": 7}, controls=[
            ft.Container(
                content=ft.Column([
                    ft.Text("📋 检查结果", size=16, weight="bold", color=ft.Colors.GREY_700),
                    result_column
                ]),
                bgcolor="white", padding=15, border_radius=10
            )
        ])
    ], spacing=20)

    page.add(ft.SafeArea(ft.Container(content=ft.Column([header, layout]), padding=10)))
    refresh_settings(app.config.get("current_provider"))
    render_results([])


ft.app(target=main)import sys
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

