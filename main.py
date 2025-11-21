import flet as ft
import base64
import json
import threading
import pandas as pd
import os
import sys
import io
import shutil  # 用于文件复制
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

DEFAULT_PROMPT = """你是一位拥有30年一线经验的**国家注册安全工程师**。
你的任务是审查施工现场照片，重点针对**施工机械**、**工艺规范**及**EHS风险**进行排查。

请按照以下格式返回纯净的 JSON 列表（不要使用Markdown代码块）：
[
    {
        "issue": "隐患描述内容",
        "regulation": "违反的规范名称",
        "correction": "具体的整改建议"
    }
]
如果未发现问题，返回 []。
"""

CONFIG_FILE = "app_config_final.json"


class SafetyApp:
    def __init__(self):
        self.config = self.load_config()
        self.current_image_path = None
        self.current_data = []
        self.client = None

    def load_config(self):
        default = {"current_provider": "阿里百炼 (Alibaba)", "system_prompt": DEFAULT_PROMPT,
                   "providers": PROVIDER_PRESETS}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if "providers" not in saved:
                        saved["providers"] = PROVIDER_PRESETS
                    else:
                        for k, v in PROVIDER_PRESETS.items():
                            if k not in saved["providers"]: saved["providers"][k] = v
                    return saved
            except:
                return default
        return default

    def save_config_to_file(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except:
            pass

    def init_client(self):
        p = self.config.get("current_provider")
        conf = self.config["providers"].get(p, {})
        if conf.get("api_key") and conf.get("base_url"):
            self.client = OpenAI(api_key=conf["api_key"], base_url=conf["base_url"])
            return True
        return False


def main(page: ft.Page):
    # ================= 页面设置 =================
    page.title = "安全检查AI助理"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#f2f4f7"
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO

    page.window.width = 1200
    page.window.height = 850
    page.window.min_width = 380
    page.window.min_height = 600

    app = SafetyApp()

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

    # ================= 核心逻辑 =================
    def save_config(e):
        p = dd_provider.value
        app.config["current_provider"] = p
        app.config["system_prompt"] = tf_prompt.value
        app.config["providers"][p]["base_url"] = tf_url.value.strip()
        app.config["providers"][p]["model"] = tf_model.value.strip()
        app.config["providers"][p]["api_key"] = tf_key.value.strip()
        app.save_config_to_file()
        status_txt.value = "✅ 配置已保存"
        page.close(dlg_settings)
        page.update()

    def refresh_settings(val):
        conf = app.config["providers"].get(val, {})
        tf_url.value = conf.get("base_url", "")
        tf_model.value = conf.get("model", "")
        tf_key.value = conf.get("api_key", "")
        page.update()
    
    def on_exit_app(e):
        try:
            page.window.close()
        except:
            sys.exit(0)

    def run_task(e):
        if not app.init_client():
            status_txt.value = "❌ 未配置API"
            status_txt.color = "red"
            page.update()
            return
        btn_analyze.disabled = True
        btn_analyze.text = "分析中..."
        page.update()

        def task():
            try:
                p = app.config["current_provider"]
                with open(app.current_image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                resp = app.client.chat.completions.create(
                    model=app.config["providers"][p]["model"],
                    messages=[{"role": "system", "content": app.config["system_prompt"]},
                              {"role": "user",
                               "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                           {"type": "text", "text": "找出所有隐患"}]}], temperature=0.1
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
                btn_export.disabled = False
                page.update()
            except Exception as err:
                status_txt.value = f"❌ {str(err)[:20]}"
                status_txt.color = "red"
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

    # ================= 【核心】安卓兼容导出逻辑 =================
    def on_save_excel(e):
        """
        终极导出方案：
        1. 在 APP 私有目录生成 (100% 有权限，不会是0KB)。
        2. 复制到 /storage/emulated/0/Download/ (公共目录)。
        3. 同时生成 Excel 和 TXT 两个文件，确保至少有一个能看。
        """
        try:
            if not app.current_data:
                raise Exception("无数据")

            # 1. 准备数据
            normalized_data = []
            txt_content = "=== 安全隐患排查报告 ===\n\n"
            txt_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            txt_content += "-" * 30 + "\n"

            for i, item in enumerate(app.current_data):
                issue = item.get("issue", "无")
                reg = item.get("regulation", "无")
                corr = item.get("correction", "无")
                
                normalized_data.append({
                    "隐患描述": issue,
                    "依据规范": reg,
                    "整改建议": corr
                })
                txt_content += f"【隐患 {i+1}】\n描述: {issue}\n规范: {reg}\n整改: {corr}\n\n"

            df = pd.DataFrame(normalized_data)
            
            # 2. 定义文件名 (使用时间戳防止覆盖)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename_xlsx = f"安全报告_{timestamp}.xlsx"
            filename_txt = f"安全报告_{timestamp}.txt"

            # 3. 【关键步骤】先保存到 APP 内部私有目录 (这里绝对可写)
            # os.environ["TMPDIR"] 在安卓上指向缓存目录，是安全的
            private_dir = os.getenv("TMPDIR", os.getcwd()) 
            private_path_xlsx = os.path.join(private_dir, filename_xlsx)
            private_path_txt = os.path.join(private_dir, filename_txt)

            # 写入 Excel 到私有目录
            with pd.ExcelWriter(private_path_xlsx, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='排查报告', index=False)
                # 简单的样式
                wb = writer.book
                ws = writer.sheets['排查报告']
                fmt = wb.add_format({'text_wrap': True, 'border': 1})
                ws.set_column('A:C', 30, fmt)

            # 写入 TXT 到私有目录 (双重保险)
            with open(private_path_txt, "w", encoding="utf-8") as f:
                f.write(txt_content)

            # 4. 【关键步骤】将私有目录的文件 复制 到公共 Download 目录
            is_mobile = page.platform in ["android", "ios"]
            
            if is_mobile:
                public_dir = "/storage/emulated/0/Download"
                final_path_xlsx = os.path.join(public_dir, filename_xlsx)
                final_path_txt = os.path.join(public_dir, filename_txt)

                # 使用 shutil 复制，比 open() 写入更稳健
                try:
                    shutil.copy(private_path_xlsx, final_path_xlsx)
                    shutil.copy(private_path_txt, final_path_txt)
                    
                    # 成功弹窗
                    dlg_success = ft.AlertDialog(
                        title=ft.Text("导出成功"),
                        content=ft.Text(f"报告已保存至【下载/Download】文件夹！\n\nExcel: {filename_xlsx}\n文本: {filename_txt}", size=16),
                        actions=[ft.TextButton("确定", on_click=lambda e: page.close(dlg_success))]
                    )
                    page.open(dlg_success)

                except Exception as e_copy:
                    # 如果复制失败，说明权限被拒，告诉用户去私有目录找
                    raise Exception(f"无法写入下载目录，文件保留在: {private_path_xlsx}\n错误: {e_copy}")
            
            else:
                # 电脑端逻辑 (FilePicker)
                if hasattr(e, "path") and e.path:
                     shutil.copy(private_path_xlsx, e.path)
                     page.snack_bar = ft.SnackBar(ft.Text("✅ 导出成功"), bgcolor="green")
                     page.snack_bar.open = True

            page.update()

        except Exception as err:
            page.snack_bar = ft.SnackBar(ft.Text(f"导出失败: {str(err)}"), bgcolor="red")
            page.snack_bar.open = True
            page.update()


    # ================= 布局组装 =================
    dd_provider = ft.Dropdown(label="厂商", options=[ft.dropdown.Option(k) for k in PROVIDER_PRESETS],
                              value=app.config.get("current_provider"),
                              on_change=lambda e: refresh_settings(e.control.value))
    tf_key = ft.TextField(label="Key", password=True)
    tf_url = ft.TextField(label="URL")
    tf_model = ft.TextField(label="Model")
    tf_prompt = ft.TextField(label="提示词", value=app.config.get("system_prompt"), multiline=True, min_lines=3)
    refresh_settings(app.config.get("current_provider"))
    
    dlg_settings = ft.AlertDialog(title=ft.Text("设置"),
                                  content=ft.Column([dd_provider, tf_key, tf_url, tf_model, tf_prompt],
                                                    scroll=ft.ScrollMode.AUTO, height=350, width=300),
                                  actions=[ft.TextButton("保存", on_click=save_config)])

    pick_dlg = ft.FilePicker(on_result=on_picked)
    save_dlg = ft.FilePicker(on_result=on_save_excel)
    
    page.overlay.extend([pick_dlg, save_dlg])

    header = ft.Container(
        content=ft.Row([
            ft.Text("🛡️ 安全检查AI助理", size=18, weight="bold"),
            ft.Row([
                ft.IconButton(ft.Icons.SETTINGS, tooltip="设置", on_click=lambda e: page.open(dlg_settings)),
                ft.IconButton(ft.Icons.EXIT_TO_APP, tooltip="退出系统", icon_color="red", on_click=on_exit_app)
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

    default_filename = f"安全报告_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    
    # 触发逻辑：手机直接运行，电脑弹窗
    def trigger_export(e):
        if page.platform in ["android", "ios"]:
            on_save_excel(None)
        else:
            save_dlg.save_file(file_name=default_filename)

    btn_export = ft.ElevatedButton("导出报告", icon=ft.Icons.DOWNLOAD,
                                   on_click=trigger_export, disabled=True,
                                   style=ft.ButtonStyle(color="green", padding=15,
                                                        shape=ft.RoundedRectangleBorder(radius=8)))

    layout = ft.ResponsiveRow([
        ft.Column(col={"xs": 12, "md": 5}, controls=[
            ft.Container(content=img_container, bgcolor="white", padding=10, border_radius=10),
            ft.Container(height=5),
            ft.Row([
                ft.Column([btn_upload], expand=1),
                ft.Column([btn_analyze], expand=1),
                ft.Column([btn_export], expand=1),
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

    page.add(
        ft.SafeArea(
            ft.Container(
                content=ft.Column([
                    header,
                    layout
                ]),
                padding=10
            )
        )
    )

    render_results([])


ft.app(target=main)
