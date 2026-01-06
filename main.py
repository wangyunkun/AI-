import flet as ft
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
    "自定义 (Custom)": {
        "base_url": "",
        "model": "",
        "api_key": ""
    }
}

DEFAULT_PROMPT = """你是一位拥有30年一线经验的**国家注册安全工程师**。你的任务是审查施工现场照片，进行**“安全+质量”双维度的全方位扫描**。
请按照以下逻辑顺序排查：
1. 危大工程与特种设备（起重、基坑、脚手架）。
2. 主体结构与关键工艺（钢筋、混凝土、模板）。
3. 二次结构与通用设施（砌体、临电、消防）。
4. 文明施工与人员行为（PPE、材料堆放）。

输出规则：
1. 引用标准：JGJ 59, JGJ 130, GB 50204 等。
2. 问题分类：【安全】或【质量】。
3. 宁严勿漏。

请返回纯净的 JSON 列表（无 Markdown），格式如下：
[
    {
        "issue": "【安全】挖掘机作业半径内有人穿越",
        "regulation": "违反《建筑机械使用安全技术规程》JGJ 33-2012",
        "correction": "立即停止作业，设置警戒隔离区"
    }
]
如果未发现任何问题，返回 []"""


class SafetyApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config = self.load_config()
        self.current_image_path = None
        self.current_data = []
        self.client = None

    def load_config(self):
        default_config = {
            "current_provider": "阿里百炼 (Alibaba)",
            "system_prompt": DEFAULT_PROMPT,
            "providers": copy.deepcopy(PROVIDER_PRESETS)
        }
        try:
            if self.page.client_storage.contains_key("app_config"):
                saved = self.page.client_storage.get("app_config")
                if isinstance(saved, dict) and "providers" in saved:
                    default_config.update(saved)
                    for k, v in PROVIDER_PRESETS.items():
                        if k not in default_config["providers"]:
                            default_config["providers"][k] = v
                    return default_config
            return default_config
        except Exception:
            return default_config

    def save_config_storage(self):
        try:
            self.page.client_storage.set("app_config", self.config)
            return True
        except Exception:
            return False

    def init_client(self):
        p = self.config.get("current_provider")
        conf = self.config["providers"].get(p, {})
        if conf.get("api_key") and conf.get("base_url"):
            self.client = OpenAI(api_key=conf["api_key"], base_url=conf["base_url"])
            return True
        return False


def main(page: ft.Page):
    # ================= 移动端视窗设置 (关键优化) =================
    page.title = "智能安全检查AI"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F7F9FC"  # 浅灰蓝背景，更像APP
    page.padding = 0  # 移除默认内边距，自己控制 SafeArea

    # === 调试时强制窗口大小，模拟手机 (iPhone 13/14 尺寸) ===
    # 打包成 APP 后这些设置会被自动忽略，适配全屏
    page.window_width = 390
    page.window_height = 844
    page.window_resizable = True

    app = SafetyApp(page)

    # ================= 辅助功能 =================
    def show_snack(message, color="green"):
        page.open(ft.SnackBar(ft.Text(message, color="white"), bgcolor=color, behavior=ft.SnackBarBehavior.FLOATING))

    # ================= 详情弹窗 (Bottom Sheet) =================
    bs_content = ft.Column(scroll=ft.ScrollMode.AUTO, tight=True)
    bs = ft.BottomSheet(
        content=ft.Container(
            content=bs_content,
            padding=25,
            bgcolor="white",
            border_radius=ft.border_radius.only(top_left=20, top_right=20),
            shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.BLACK12)
        ),
        dismissible=True
    )

    def show_detail(item):
        bs_content.controls = [
            ft.Container(width=40, height=4, bgcolor="grey", border_radius=10, alignment=ft.alignment.center,
                         opacity=0.3),
            ft.Container(height=15),
            ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="red", size=24),
                ft.Text("隐患详情", size=18, weight="bold")
            ]),
            ft.Divider(height=20),
            ft.Text("问题描述", color="grey", size=12),
            ft.Text(item.get("issue", ""), size=16, weight="w500"),
            ft.Container(height=10),
            ft.Text("规范依据", color="grey", size=12),
            ft.Container(
                content=ft.Text(item.get("regulation", ""), size=14, color="blue"),
                bgcolor="#EFF6FF", padding=10, border_radius=6
            ),
            ft.Container(height=10),
            ft.Text("整改建议", color="grey", size=12),
            ft.Container(
                content=ft.Text(item.get("correction", ""), size=14, color="#166534"),
                bgcolor="#F0FDF4", padding=10, border_radius=6
            ),
            ft.Container(height=30)  # 底部留白
        ]
        page.open(bs)
        page.update()

    # ================= 结果列表 (卡片式) =================
    # 注意：这里去掉了 scroll 属性，让整个页面滚动
    result_column = ft.Column(spacing=12)

    def render_results(data):
        result_column.controls.clear()
        if not data:
            # 空状态
            result_column.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=60, color="#CBD5E1"),
                        ft.Text("暂无数据，请先上传照片", color="#94A3B8")
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    alignment=ft.alignment.center,
                    padding=ft.padding.only(top=40)
                )
            )
        else:
            for i, item in enumerate(data):
                # 卡片设计
                card = ft.Container(
                    bgcolor="white",
                    padding=15,
                    border_radius=12,
                    shadow=ft.BoxShadow(blur_radius=5, color=ft.Colors.BLACK12, offset=ft.Offset(0, 2)),
                    on_click=lambda e, d=item: show_detail(d),
                    content=ft.Row([
                        # 序号球
                        ft.Container(
                            content=ft.Text(str(i + 1), color="white", weight="bold", size=12),
                            bgcolor="#EF4444", width=24, height=24, border_radius=12, alignment=ft.alignment.center
                        ),
                        ft.VerticalDivider(width=8, color="transparent"),
                        # 文本区
                        ft.Column([
                            ft.Text(item.get("issue", "未知隐患"), max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                                    weight="bold", size=15, color="#1E293B"),
                            ft.Text(item.get("regulation", "无规范")[:18] + "...", size=12, color="#64748B")
                        ], expand=True, spacing=2),
                        ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color="#94A3B8")
                    ], alignment=ft.MainAxisAlignment.START)
                )
                result_column.controls.append(card)
        page.update()

    # ================= 控件区 =================

    # 图片预览组件
    img_control = ft.Image(
        src="",
        src_base64=None,
        fit=ft.ImageFit.COVER,
        visible=False,
        border_radius=12,
        expand=True
    )

    # 占位符组件（没图的时候显示）
    placeholder_control = ft.Column([
        ft.Icon(ft.Icons.ADD_A_PHOTO, size=40, color="#94A3B8"),
        ft.Text("点击拍摄/上传照片", color="#94A3B8", size=14)
    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    img_container = ft.Container(
        content=placeholder_control,
        height=220,  # 手机上合适的高度
        bgcolor="#E2E8F0",
        border_radius=16,
        alignment=ft.alignment.center,
        on_click=lambda _: pick_dlg.pick_files(),
        shadow=ft.BoxShadow(blur_radius=0, color="transparent")  # 没图时不显示阴影
    )

    status_txt = ft.Text("请上传照片", size=13, color="#64748B", text_align="center")
    loading_anim = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)

    # ================= 逻辑处理 =================
    def run_analysis(e):
        if not app.current_image_path:
            show_snack("📸 请先选择照片", "red")
            return
        if not app.init_client():
            show_snack("⚙️ 请先配置 API Key", "red")
            page.open(dlg_settings)
            return

        # UI 锁定状态
        btn_analyze.disabled = True
        btn_analyze.text = "AI正在思考..."
        btn_analyze.bgcolor = "#94A3B8"
        loading_anim.visible = True
        status_txt.value = "正在上传图片并请求云端分析..."
        page.update()

        def task():
            try:
                p = app.config["current_provider"]
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

                content = resp.choices[0].message.content
                # 增强 JSON 提取逻辑
                json_str = content.replace("```json", "").replace("```", "").strip()
                start = json_str.find('[')
                end = json_str.rfind(']') + 1

                if start != -1 and end != -1:
                    data = json.loads(json_str[start:end])
                    app.current_data = data
                    render_results(data)
                    status_txt.value = f"✅ 分析完成，发现 {len(data)} 处问题"
                    show_snack("分析完成", "green")
                else:
                    status_txt.value = "⚠️ 解析失败，AI返回格式有误"
                    print(content)

            except Exception as err:
                status_txt.value = "❌ 分析出错，请重试"
                show_snack(f"错误: {str(err)[:30]}", "red")
            finally:
                btn_analyze.disabled = False
                btn_analyze.text = "开始智能分析"
                btn_analyze.bgcolor = "#2563EB"
                btn_copy.disabled = False
                loading_anim.visible = False
                page.update()

        threading.Thread(target=task, daemon=True).start()

    def on_picked(e):
        if e.files:
            app.current_image_path = e.files[0].path
            # 切换显示模式
            img_container.content = img_control
            img_control.src = app.current_image_path
            img_control.visible = True
            img_container.shadow = ft.BoxShadow(blur_radius=10, color=ft.Colors.BLACK12)

            status_txt.value = "✅ 照片已就绪，点击下方按钮开始"
            btn_analyze.disabled = False
            render_results([])  # 清空上次结果
            page.update()

    def save_settings(e):
        p = dd_provider.value
        app.config["current_provider"] = p
        app.config["system_prompt"] = tf_prompt.value
        app.config["providers"][p]["base_url"] = tf_url.value.strip()
        app.config["providers"][p]["model"] = tf_model.value.strip()
        app.config["providers"][p]["api_key"] = tf_key.value.strip()
        app.save_config_storage()
        show_snack("设置已保存", "green")
        page.close(dlg_settings)

    def update_settings_view(val):
        conf = app.config["providers"].get(val, {})
        tf_url.value = conf.get("base_url", "")
        tf_model.value = conf.get("model", "")
        tf_key.value = conf.get("api_key", "")
        page.update()

    def copy_result(e):
        if not app.current_data: return
        txt = "【检查报告】\n" + "\n".join([f"{i + 1}. {item['issue']}" for i, item in enumerate(app.current_data)])
        page.set_clipboard(txt)
        show_snack("已复制到剪贴板", "green")

    # ================= 弹窗与设置 =================
    pick_dlg = ft.FilePicker(on_result=on_picked)
    page.overlay.append(pick_dlg)

    dd_provider = ft.Dropdown(label="厂商", options=[ft.dropdown.Option(k) for k in PROVIDER_PRESETS],
                              value=app.config.get("current_provider"),
                              on_change=lambda e: update_settings_view(e.control.value))
    tf_key = ft.TextField(label="API Key", password=True, can_reveal_password=True, text_size=14)
    tf_url = ft.TextField(label="Base URL", text_size=14)
    tf_model = ft.TextField(label="Model", text_size=14)
    tf_prompt = ft.TextField(label="Prompt", multiline=True, min_lines=2, text_size=12,
                             value=app.config.get("system_prompt"))

    dlg_settings = ft.AlertDialog(
        title=ft.Text("设置 API"),
        content=ft.Column([dd_provider, tf_key, tf_url, tf_model, tf_prompt], height=400, width=300,
                          scroll=ft.ScrollMode.AUTO),
        actions=[ft.TextButton("保存", on_click=save_settings)]
    )

    # ================= 主页面布局 (垂直流式) =================

    # 顶部栏
    header = ft.Row([
        ft.Column([
            ft.Text("西双版纳州水利工程质量与安全中心", size=22, weight="bold", color="#1E293B"),
            ft.Text("智能识别隐患 · 实时分析", size=12, color="#64748B")
        ]),
        ft.IconButton(ft.Icons.SETTINGS, icon_color="#475569", on_click=lambda e: page.open(dlg_settings))
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

    # 按钮组
    btn_analyze = ft.ElevatedButton(
        "开始智能分析",
        icon=ft.Icons.AUTO_AWESOME,
        on_click=run_analysis,
        bgcolor="#2563EB", color="white",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), padding=16),
        expand=True
    )

    btn_copy = ft.ElevatedButton(
        "复制结果",
        icon=ft.Icons.COPY,
        on_click=copy_result,
        disabled=True,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), padding=16),
    )

    # 整体滚动容器 (模拟手机APP的主视图)
    main_layout = ft.Column(
        controls=[
            ft.Container(height=10),  # 顶部安全距离
            header,
            ft.Container(height=15),
            img_container,
            ft.Container(height=10),
            ft.Row([loading_anim, status_txt], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=5),
            ft.Row([btn_analyze, btn_copy], spacing=10),
            ft.Divider(height=30, color="#E2E8F0"),
            ft.Text("检查结果", size=16, weight="bold", color="#334155"),
            result_column,
            ft.Container(height=50)  # 底部防遮挡距离
        ],
        scroll=ft.ScrollMode.AUTO,  # 开启页面级滚动
        expand=True,
        spacing=0
    )

    # 使用 SafeArea 包裹防止刘海屏遮挡
    page.add(ft.SafeArea(ft.Container(main_layout, padding=20), expand=True))

    # 初始化
    update_settings_view(app.config.get("current_provider"))


ft.app(target=main)
