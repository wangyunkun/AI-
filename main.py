import flet as ft
import base64
import json
import threading
import os
import copy
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
        读取配置 (修复 persistence 问题)
        """
        # 使用 deepcopy 确保默认值不被引用修改
        default_config = {
            "current_provider": "阿里百炼 (Alibaba)",
            "system_prompt": DEFAULT_PROMPT,
            "providers": copy.deepcopy(PROVIDER_PRESETS)
        }

        try:
            # 尝试从手机安全存储中读取
            if self.page.client_storage.contains_key("app_config"):
                saved = self.page.client_storage.get("app_config")

                # 简单的校验，防止空数据
                if not saved or not isinstance(saved, dict):
                    return default_config

                # 补全可能缺失的新字段
                if "providers" not in saved:
                    saved["providers"] = copy.deepcopy(PROVIDER_PRESETS)
                else:
                    # 如果预设里有新厂商，补全到存档里
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
        """
        保存配置到手机存储
        """
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
    page.title = "普洱版纳质量安全部-测试版"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#f2f4f7"
    page.scroll = ft.ScrollMode.AUTO

    # 初始化逻辑
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
        # 更新内存中的配置
        app.config["current_provider"] = p
        app.config["system_prompt"] = tf_prompt.value
        app.config["providers"][p]["base_url"] = tf_url.value.strip()
        app.config["providers"][p]["model"] = tf_model.value.strip()
        app.config["providers"][p]["api_key"] = tf_key.value.strip()

        # 保存到手机存储
        if app.save_config_storage():
            status_txt.value = "✅ 配置已保存"
            page.snack_bar = ft.SnackBar(ft.Text("配置已保存，重启后依然有效"), bgcolor="green")
            page.snack_bar.open = True
        else:
            status_txt.value = "❌ 保存失败"

        page.close(dlg_settings)
        page.update()

    def refresh_settings(val):
        """刷新设置弹窗中的输入框数值"""
        conf = app.config["providers"].get(val, {})
        tf_url.value = conf.get("base_url", "")
        tf_model.value = conf.get("model", "")
        tf_key.value = conf.get("api_key", "")
        page.update()

    def run_task(e):
        if not app.init_client():
            status_txt.value = "❌ 未配置API或Key"
            status_txt.color = "red"
            page.open(dlg_settings)  # 自动打开设置
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

                # 回到主线程更新UI
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

    # ================= 复制逻辑 (替代导出) =================
    def copy_to_clipboard(e):
        if not app.current_data:
            page.snack_bar = ft.SnackBar(ft.Text("没有可复制的数据"), bgcolor="red")
            page.snack_bar.open = True
            page.update()
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

        # 写入剪贴板
        page.set_clipboard(text_report)

        # 显示成功提示
        page.snack_bar = ft.SnackBar(
            ft.Text("✅ 已保存在剪贴板，可以粘贴在微信或文档中"),
            bgcolor="green",
            duration=3000
        )
        page.snack_bar.open = True
        page.update()

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

    # 修改后的复制按钮
    btn_copy = ft.ElevatedButton("复制检查结果", icon=ft.Icons.COPY, on_click=copy_to_clipboard, disabled=True,
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

    # 启动时初始化一次设置输入框，确保已保存的 Key 能显示出来
    refresh_settings(app.config.get("current_provider"))

    render_results([])


ft.app(target=main)
