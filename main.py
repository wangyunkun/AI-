import flet as ft
import base64
import json
import threading
import pandas as pd
import io
import os
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
        """
        修复点1：使用 client_storage 读取配置，适配 Android 持久化
        """
        default = {
            "current_provider": "阿里百炼 (Alibaba)",
            "system_prompt": DEFAULT_PROMPT,
            "providers": PROVIDER_PRESETS
        }

        try:
            # 从本地存储读取
            saved = self.page.client_storage.get("app_config")
            if not saved:
                return default

            # 合并新旧配置，防止key缺失
            if "providers" not in saved:
                saved["providers"] = PROVIDER_PRESETS
            else:
                for k, v in PROVIDER_PRESETS.items():
                    if k not in saved["providers"]:
                        saved["providers"][k] = v
            return saved
        except Exception as e:
            print(f"Config Load Error: {e}")
            return default

    def save_config_storage(self):
        """
        修复点2：使用 client_storage 保存配置
        """
        try:
            self.page.client_storage.set("app_config", self.config)
            return True
        except Exception as e:
            print(f"Config Save Error: {e}")
            return False

    def init_client(self):
        p = self.config.get("current_provider")
        conf = self.config["providers"].get(p, {})
        if conf.get("api_key") and conf.get("base_url"):
            self.client = OpenAI(api_key=conf["api_key"], base_url=conf["base_url"])
            return True
        return False

    def get_excel_bytes(self):
        
        if not self.current_data:
            return None

        normalized_data = []
        for i, item in enumerate(self.current_data):
            normalized_data.append({
                "序号": i + 1,
                "隐患描述": item.get("issue", "无"),
                "依据规范": item.get("regulation", "无"),
                "整改建议": item.get("correction", "无")
            })
        df = pd.DataFrame(normalized_data)

        output = io.BytesIO()
        
        # ===========================================================
        # 【关键修复】添加 engine_kwargs={'options': {'in_memory': True}}
        # 这会禁止 XlsxWriter 尝试访问 Android 的 /tmp 目录
        # ===========================================================
        with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={'options': {'in_memory': True}}) as writer:
            # 留出前2行写标题
            df.to_excel(writer, sheet_name='排查报告', startrow=2, index=False)

            workbook = writer.book
            worksheet = writer.sheets['排查报告']

            # --- 定义样式 ---
            title_format = workbook.add_format({
                'bold': True, 'font_size': 18, 'align': 'center', 'valign': 'vcenter',
                'fg_color': '#E6F3FF', 'border': 1
            })
            header_format = workbook.add_format({
                'bold': True, 'text_wrap': True, 'valign': 'top', 'align': 'center',
                'fg_color': '#0070C0', 'font_color': 'white', 'border': 1
            })
            body_format = workbook.add_format({
                'text_wrap': True, 'valign': 'top', 'align': 'left', 'border': 1
            })
            center_format = workbook.add_format({
                'text_wrap': True, 'valign': 'top', 'align': 'center', 'border': 1
            })

            # --- 写入内容 ---
            worksheet.merge_range('A1:D1', '普洱版纳区域质量安全检查报告', title_format)
            time_str = f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            worksheet.merge_range('A2:D2', time_str,
                                  workbook.add_format({'align': 'right', 'italic': True, 'font_color': '#666666'}))

            # 设置列宽
            worksheet.set_column('A:A', 6, center_format)
            worksheet.set_column('B:B', 40, body_format)
            worksheet.set_column('C:C', 30, body_format)
            worksheet.set_column('D:D', 40, body_format)

            # 重写表头
            headers = df.columns.values
            for col_num, value in enumerate(headers):
                worksheet.write(2, col_num, value, header_format)

        # 重要：确保指针回到开头
        output.seek(0)
        return output


def main(page: ft.Page):
    # ================= 页面设置 =================
    page.title = "普洱版纳质量安全部-测试版"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#f2f4f7"
    page.scroll = ft.ScrollMode.AUTO

    # 初始化App逻辑 (传入page以使用存储)
    app = SafetyApp(page)

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

        # 使用新的保存方法
        if app.save_config_storage():
            status_txt.value = "✅ 配置已保存 (Storage)"
        else:
            status_txt.value = "❌ 保存失败"

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
                if not app.current_image_path:
                    raise Exception("未选择图片")

                # 读取图片并转换base64
                with open(app.current_image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()

                resp = app.client.chat.completions.create(
                    model=app.config["providers"][p]["model"],
                    messages=[{"role": "system", "content": app.config["system_prompt"]},
                              {"role": "user",
                               "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                           {"type": "text", "text": "找出所有隐患"}]}],
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
                btn_export.disabled = False
                page.update()
            except Exception as err:
                status_txt.value = f"❌ {str(err)[:20]}"
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

    # ================= 修复点3：导出逻辑改为保存文件 =================

    def save_file_result(e: ft.FilePickerResultEvent):
        """
        用户选择保存路径后的回调
        """
        if e.path:
            try:
                excel_bytes_io = app.get_excel_bytes()
                if excel_bytes_io:
                    # 将二进制数据写入用户选择的路径
                    with open(e.path, "wb") as f:
                        f.write(excel_bytes_io.getvalue())

                    page.snack_bar = ft.SnackBar(ft.Text(f"✅ 文件已保存至: {e.path}"), bgcolor="green")
                else:
                    page.snack_bar = ft.SnackBar(ft.Text("❌ 数据为空，无法保存"), bgcolor="red")
            except Exception as err:
                page.snack_bar = ft.SnackBar(ft.Text(f"❌ 保存失败: {str(err)}"), bgcolor="red")

            page.snack_bar.open = True
            page.update()

    # 专用的保存文件选择器
    save_picker = ft.FilePicker(on_result=save_file_result)
    page.overlay.append(save_picker)

    def trigger_export_options(e):
        # 弹出底部菜单让用户选择
        def close_bs(e):
            export_bs.open = False
            page.update()

        def save_excel(e):
            close_bs(e)
            if not app.current_data:
                return
            # 触发文件保存对话框
            fname = f"安全检查报告_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            save_picker.save_file(file_name=fname, allowed_extensions=["xlsx"])

        def copy_text(e):
            close_bs(e)
            if not app.current_data:
                return
            text_report = "=== 普洱版纳区域安全检查报告 ===\n"
            for i, item in enumerate(app.current_data):
                text_report += f"\n【隐患{i+1}】{item.get('issue')}\n整改: {item.get('correction')}\n"
            page.set_clipboard(text_report)
            page.snack_bar = ft.SnackBar(ft.Text("✅ 文本已复制到剪贴板"), bgcolor="green")
            page.snack_bar.open = True
            page.update()

        export_bs = ft.BottomSheet(
            ft.Container(
                ft.Column([
                    # 注意：这里的所有 Icons 都要改成全大写
                    ft.ListTile(leading=ft.Icon(ft.Icons.TABLE_VIEW), title=ft.Text("保存为 Excel 表格"), on_click=save_excel),
                    ft.ListTile(leading=ft.Icon(ft.Icons.COPY), title=ft.Text("复制纯文本内容"), on_click=copy_text),
                    ft.ListTile(leading=ft.Icon(ft.Icons.CANCEL, color="red"), title=ft.Text("取消", color="red"), on_click=close_bs),
                ], tight=True),
                padding=10
            ),
            dismissible=True
        )
        page.overlay.append(export_bs)
        export_bs.open = True
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
                                  actions=[ft.TextButton("保存", on_click=save_config_ui)])

    pick_dlg = ft.FilePicker(on_result=on_picked)
    page.overlay.append(pick_dlg)

    header = ft.Container(
        content=ft.Row([
            ft.Text("🛡️ 普洱版纳质量安全检查AI", size=18, weight="bold"),
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

    # 按钮改为触发选项
    btn_export = ft.ElevatedButton("导出结果", icon=ft.Icons.DOWNLOAD, on_click=trigger_export_options, disabled=True,
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

    page.add(ft.SafeArea(ft.Container(content=ft.Column([header, layout]), padding=10)))
    render_results([])


ft.app(target=main)

