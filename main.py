import flet as ft
import base64
import json
import threading
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
[{"issue": "...", "regulation": "...", "correction": "..."}]
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
    # ================= 1. 页面初始化 =================
    page.title = "安全检查AI"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F7F9FC"
    page.padding = 0

    app = SafetyApp(page)

    # ================= 2. 辅助组件 =================
    def show_snack(message, color="green"):
        page.snack_bar = ft.SnackBar(ft.Text(message, color="white"), bgcolor=color, behavior="floating")
        page.snack_bar.open = True
        page.update()

    # 详情弹窗
    bs_content = ft.Column(scroll="auto", tight=True)
    bs = ft.BottomSheet(
        content=ft.Container(
            content=bs_content,
            padding=25,
            bgcolor="white",
            border_radius=ft.border_radius.only(top_left=20, top_right=20),
        ),
        dismissible=True
    )
    page.overlay.append(bs)

    def show_detail(item):
        bs_content.controls = [
            ft.Container(width=40, height=4, bgcolor="grey", border_radius=10, alignment=ft.alignment.center, opacity=0.3),
            ft.Container(height=15),
            ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="red", size=24),
                ft.Text("隐患详情", size=18, weight="bold")
            ]),
            ft.Divider(height=20, color="#EEEEEE"),
            ft.Text("问题描述", color="grey", size=12),
            ft.Text(item.get("issue", ""), size=16, weight="w500", selectable=True), # 允许长按复制
            ft.Container(height=10),
            ft.Text("规范依据", color="grey", size=12),
            ft.Container(
                content=ft.Text(item.get("regulation", ""), size=14, color="#1D4ED8", selectable=True),
                bgcolor="#EFF6FF", padding=10, border_radius=6
            ),
            ft.Container(height=10),
            ft.Text("整改建议", color="grey", size=12),
            ft.Container(
                content=ft.Text(item.get("correction", ""), size=14, color="#15803D", selectable=True),
                bgcolor="#F0FDF4", padding=10, border_radius=6
            ),
            ft.Container(height=30)
        ]
        bs.open = True
        page.update()

    # ================= 3. 结果列表 =================
    result_column = ft.Column(spacing=12)

    def render_results(data):
        result_column.controls.clear()
        if not data:
            result_column.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=60, color="#CBD5E1"),
                        ft.Text("暂无数据，请先上传照片", color="#94A3B8")
                    ], horizontal_alignment="center"),
                    alignment=ft.alignment.center,
                    padding=ft.padding.only(top=40)
                )
            )
        else:
            for i, item in enumerate(data):
                card = ft.Container(
                    bgcolor="white", padding=15, border_radius=12,
                    shadow=ft.BoxShadow(blur_radius=5, color=ft.Colors.BLACK12, offset=ft.Offset(0, 2)),
                    content=ft.Row([
                        ft.Container(
                            content=ft.Text(str(i + 1), color="white", weight="bold", size=12),
                            bgcolor="#EF4444", width=24, height=24, border_radius=12, 
                            alignment=ft.alignment.center
                        ),
                        ft.VerticalDivider(width=8, color="transparent"),
                        ft.Column([
                            ft.Text(item.get("issue", "未知隐患"), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, weight="bold", size=15, color="#1E293B"),
                            ft.Text(item.get("regulation", "无规范")[:18] + "...", size=12, color="#64748B")
                        ], expand=True, spacing=2),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color="#94A3B8")
                    ], alignment="start", vertical_alignment="center")
                )
                card.on_click = lambda e, d=item: show_detail(d)
                result_column.controls.append(card)
        page.update()

    # ================= 4. 核心控件 =================
    img_control = ft.Image(src="", visible=False, border_radius=12, fit="cover", expand=True)
    
    pick_dlg = ft.FilePicker()
    page.overlay.append(pick_dlg)

    placeholder = ft.Column([
        ft.Icon(ft.Icons.ADD_A_PHOTO, size=40, color="#94A3B8"),
        ft.Text("点击拍摄/上传照片", color="#94A3B8", size=14)
    ], alignment="center", horizontal_alignment="center")

    img_container = ft.Container(
        content=placeholder,
        height=220,
        bgcolor="#E2E8F0",
        border_radius=16,
        alignment=ft.alignment.center,
        shadow=ft.BoxShadow(blur_radius=0, color="transparent")
    )
    img_container.on_click = lambda _: pick_dlg.pick_files()

    status_txt = ft.Text("准备就绪", size=13, color="#64748B")
    loading_anim = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)

    # ================= 5. 业务逻辑 =================
    def run_analysis(e):
        if not app.current_image_path:
            show_snack("请先选择照片", "red")
            return
        if not app.init_client():
            show_snack("请先配置 API Key", "red")
            dlg_settings.open = True
            page.update()
            return

        btn_analyze.disabled = True
        btn_analyze.text = "AI分析中..."
        loading_anim.visible = True
        status_txt.value = "正在上传并分析..."
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
                json_str = content.replace("```json", "").replace("```", "").strip()
                s, e = json_str.find('['), json_str.rfind(']') + 1
                if s != -1 and e != -1:
                    data = json.loads(json_str[s:e])
                    app.current_data = data # 保存数据，用于复制
                    render_results(data)
                    status_txt.value = f"✅ 发现 {len(data)} 处隐患"
                    show_snack("分析完成", "green")
                else:
                    status_txt.value = "⚠️ 数据解析失败"

            except Exception as err:
                status_txt.value = "❌ 分析出错"
                show_snack(f"错误: {str(err)[:30]}", "red")
            finally:
                btn_analyze.disabled = False
                btn_analyze.text = "开始智能分析"
                loading_anim.visible = False
                page.update()

        threading.Thread(target=task, daemon=True).start()

    def on_picked(e):
        if e.files:
            app.current_image_path = e.files[0].path
            img_container.content = img_control
            img_control.src = app.current_image_path
            img_control.visible = True
            img_container.shadow = ft.BoxShadow(blur_radius=10, color=ft.Colors.BLACK12)
            status_txt.value = "✅ 图片已就绪"
            render_results([]) 
            page.update()
    
    pick_dlg.on_result = on_picked

    # 🔧 修复：复制逻辑重写，拼接完整报告
    def copy_result(e):
        if not app.current_data:
            show_snack("没有可复制的内容", "red")
            return
        
        # 拼接文本报告
        report = "【安全检查报告】\n"
        report += f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        report += "-" * 20 + "\n"
        
        for i, item in enumerate(app.current_data):
            report += f"{i+1}. {item.get('issue', '未知问题')}\n"
            report += f"   🛑 依据: {item.get('regulation', '无')}\n"
            report += f"   ✅ 整改: {item.get('correction', '无')}\n\n"
        
        page.set_clipboard(report)
        show_snack("报告已复制到剪贴板", "green")

    # ================= 6. 设置弹窗 =================
    def save_settings(e):
        p = dd_provider.value
        app.config["current_provider"] = p
        app.config["system_prompt"] = tf_prompt.value
        app.config["providers"][p]["base_url"] = tf_url.value.strip()
        app.config["providers"][p]["model"] = tf_model.value.strip()
        app.config["providers"][p]["api_key"] = tf_key.value.strip()
        app.save_config_storage()
        show_snack("保存成功", "green")
        dlg_settings.open = False
        page.update()

    def update_settings_view(val):
        conf = app.config["providers"].get(val, {})
        tf_url.value = conf.get("base_url", "")
        tf_model.value = conf.get("model", "")
        tf_key.value = conf.get("api_key", "")
        page.update()

    dd_provider = ft.Dropdown(label="厂商", options=[ft.dropdown.Option(k) for k in PROVIDER_PRESETS], 
                              value=app.config.get("current_provider"))
    dd_provider.on_change = lambda e: update_settings_view(e.control.value)

    tf_key = ft.TextField(label="API Key", password=True, can_reveal_password=True, text_size=14)
    tf_url = ft.TextField(label="Base URL", text_size=14)
    tf_model = ft.TextField(label="Model", text_size=14)
    tf_prompt = ft.TextField(label="Prompt", multiline=True, min_lines=2, text_size=12, value=app.config.get("system_prompt"))

    dlg_settings = ft.AlertDialog(
        title=ft.Text("设置"),
        content=ft.Column([dd_provider, tf_key, tf_url, tf_model, tf_prompt], height=400, width=300, scroll="auto"), 
        actions=[ft.TextButton("保存", on_click=save_settings)]
    )
    page.dialog = dlg_settings

    # ================= 7. 布局组装 (修复比例问题) =================
    
    # 🔧 修复：使用 expand=True 确保 Row 撑满宽度，space_between 才会生效
    header = ft.Row([
        ft.Column([
            ft.Text("勐海县水利质量与安全中心", size=22, weight="bold", color="#1E293B"),
            ft.Text("智能识别 · 实时分析", size=12, color="#64748B")
        ], expand=True), 
        ft.IconButton(ft.Icons.SETTINGS, icon_color="#475569", icon_size=28,
                      on_click=lambda e: setattr(dlg_settings, 'open', True) or page.update())
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    btn_analyze = ft.ElevatedButton(
        "开始智能分析", icon=ft.Icons.AUTO_AWESOME, 
        bgcolor="#2563EB", color="white",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), padding=16),
        expand=True
    )
    btn_analyze.on_click = run_analysis
    
    btn_copy = ft.ElevatedButton(
        "复制结果", icon=ft.Icons.COPY, # 修改了按钮文字
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), padding=16),
    )
    btn_copy.on_click = copy_result

    main_layout = ft.Column(
        controls=[
            # 🔧 修复：让 Header 所在的容器撑满宽度
            ft.Container(content=header, padding=ft.padding.only(bottom=10)),
            img_container,
            ft.Container(height=10),
            ft.Row([loading_anim, status_txt], alignment="center"),
            ft.Container(height=5),
            ft.Row([btn_analyze, btn_copy], spacing=10),
            ft.Divider(height=30, color="#E2E8F0"),
            ft.Text("检查结果", size=16, weight="bold", color="#334155"),
            result_column,
            ft.Container(height=50)
        ],
        scroll="auto",
        expand=True
    )

    # 🔧 修复：SafeArea 包裹整个 View，确保顶部不被遮挡
    page.add(ft.SafeArea(ft.Container(main_layout, padding=10), expand=True))
    
    # 启动时刷新配置
    update_settings_view(app.config.get("current_provider"))

ft.app(target=main)



