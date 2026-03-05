#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建设工程质量安全检查助手 - 手机版 V5.0 (Flet 跨平台重构版)
专为 Android/iOS 编译优化。
完全保留原业务逻辑、提示词和 UI 风格。
"""

import os, json, base64, time, re, threading
from datetime import datetime
from typing import Dict, List

import flet as ft
from openai import OpenAI

# ==================== 全局配置 (完全保留) ====================
CONFIG_FILE = "app_config.json"
MAX_IMAGES = 20

DS = {
    "primary": "#1A56DB",
    "primary_light": "#EBF0FF",
    "danger": "#E02424",
    "danger_light": "#FDE8E8",
    "success": "#057A55",
    "success_light": "#DEF7EC",
    "info": "#1A56DB",
    "info_light": "#E1EFFE",
    "bg": "#F3F4F6",
    "surface": "#FFFFFF",
    "surface2": "#F9FAFB",
    "text_primary": "#111928",
    "text_secondary": "#6B7280",
    "text_hint": "#9CA3AF",
    "border": "#E5E7EB",
}

RISK_STYLE = {
    "严重安全隐患": {"bg": "#FDE8E8", "border": "#E02424", "icon": "🔴", "priority": 0},
    "一般安全隐患": {"bg": "#FEF3C7", "border": "#D03801", "icon": "🟠", "priority": 1},
    "严重质量缺陷": {"bg": "#FFFBEB", "border": "#B45309", "icon": "🟡", "priority": 2},
    "一般质量缺陷": {"bg": "#E1EFFE", "border": "#1A56DB", "icon": "🔵", "priority": 3},
}

PROVIDER_PRESETS = {
    "阿里百炼 (Qwen-VL-Max)": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-vl-max"},
    "阿里百炼 (Qwen2.5-VL)": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen2.5-vl-72b"},
    "硅基流动 (Qwen2-VL)": {"base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen2-VL-72B-Instruct"},
}

DEFAULT_PROMPTS = {
    "V4.6 安全质量双聚焦": "聚焦安全隐患 + 质量问题",
    "安全隐患专项": "仅识别安全隐患",
    "质量问题专项": "仅识别质量问题",
}

REGULATION_DB = {
    "安全": {
        "role_desc": "注册安全工程师 | 30 年经验",
        "critical_hazards": ["高处作业不系安全带", "安全帽未系下颌带", "临边洞口防护缺失", "使用挖掘机吊装"],
        "checklist": ["【一眼识别】安全帽：未系下颌带立即报告", "【一眼识别】安全带：2m 以上无安全带立即报告", "【一眼识别】临边防护：无 1.2m 护栏立即报告"],
        "must_report_if": ["发现高处作业无安全带", "发现临边洞口无防护", "发现使用挖掘机吊物"],
        "norms": "### JGJ 59-2011《建筑施工安全检查标准》\n**第 3.2.5 条** 进入施工现场必须正确佩戴安全帽，系好下颌带。\n**第 5.1.1 条** 高处作业 (2m 及以上) 必须系安全带，安全带必须高挂低用。\n### JGJ 33-2012\n**第 4.1.14 条** 严禁使用挖掘机、装载机进行吊装作业。",
        "anti_hallucination": "管理人员在安全通道内检查可短时摘帽；地面作业不强制系安全带。"
    },
    "机械": {
        "role_desc": "起重机械专家 | 30 年经验",
        "critical_hazards": ["【致命】使用挖掘机吊装", "塔吊限制器失效或被短接", "钢丝绳断丝超过 10%", "施工升降机防坠安全器失效"],
        "checklist": ["【一眼识别】吊装设备：挖掘机、装载机吊物立即报告", "【一眼识别】限位器：查看是否有线头短接", "【一眼识别】钢丝绳：断丝断股立即报告"],
        "must_report_if": ["发现使用挖掘机、装载机吊物", "发现限位器短接或失效", "发现钢丝绳断丝断股"],
        "norms": "### GB 5144-2006《塔式起重机安全规程》\n**第 6.1.1 条** 塔吊必须装设力矩限制器、起重量限制器、高度限位器。\n### JGJ 33-2012《建筑机械使用安全技术规程》\n**第 4.1.14 条** 严禁使用挖掘机、装载机、推土机等非起重机械进行吊装作业。",
        "anti_hallucination": "停工状态吊钩无荷载正常；设备表面轻微锈迹不是缺陷。"
    },
    "电气": {
        "role_desc": "注册电气工程师 | 30 年经验",
        "critical_hazards": ["临时用电未采用 TN-S 系统", "配电箱未做重复接地", "一闸多机", "电缆直接拖地或浸水"],
        "checklist": ["【一眼识别】电线颜色：黄绿双色只能是 PE 线", "【一眼识别】配电箱门：必须有跨接软铜线", "【一眼识别】插座接线：左零右火上接地"],
        "must_report_if": ["发现电线绝缘层破损", "发现漏电保护器失效", "发现电缆接头裸露"],
        "norms": "### JGJ 46-2005《施工现场临时用电安全技术规范》\n**第 5.1.1 条** 临时用电工程必须采用 TN-S 接零保护系统，实行三级配电两级保护。\n**第 8.1.3 条** 每台用电设备必须有各自专用的开关箱，严禁一闸多机。",
        "anti_hallucination": "施工中临时接线待整理正常；备用回路不是故障。"
    },
    "管道": {
        "role_desc": "管道工艺专家 | 30 年经验",
        "critical_hazards": ["压力管道使用排水管", "阀门无标识或标识错误", "法兰垫片使用错误"],
        "checklist": ["【一眼识别】管道颜色：红色消防、绿色给水、蓝色排水、黄色燃气", "【一眼识别】法兰螺栓：必须露出 2-3 扣"],
        "must_report_if": ["发现管道有凹陷、裂纹", "发现阀门铭牌缺失", "发现不同材质管道直接焊接"],
        "norms": "### GB 50242-2002《建筑给水排水及采暖工程施工质量验收规范》\n**第 3.3.13 条** 法兰连接螺栓紧固后露出螺母 2-3 扣。\n**第 3.3.15 条** 阀门安装前必须做强度和严密性试验，安装方向正确。",
        "anti_hallucination": "临时封堵盲板不是缺阀门；试压用临时支撑不是支架不足。"
    },
    "结构": {
        "role_desc": "结构总工程师 | 30 年经验",
        "critical_hazards": ["模板支撑立杆悬空或无垫板", "高大模板未设置扫地杆剪刀撑", "混凝土浇筑后出现贯穿裂缝"],
        "checklist": ["【一眼识别】立杆底部：悬空、无垫板立即报告", "【一眼识别】混凝土裂缝：宽度超 0.3mm 立即报告"],
        "must_report_if": ["发现立杆悬空无垫板", "发现混凝土裂缝宽度超过 0.3mm"],
        "norms": "### JGJ 162-2008《建筑施工模板安全技术规范》\n**第 6.1.2 条** 模板支架立杆底部必须设置垫板，严禁悬空，垫板厚度不小于 50mm。\n### GB 50204-2015《混凝土结构工程施工质量验收规范》",
        "anti_hallucination": "未抹面不是不平整；温度裂缝（发丝状）不是结构裂缝。"
    },
}

ROUTER_PROMPT = """你是工程建设总监。识别图片施工内容，选派 2-5 个专家：
1. 安全 2. 机械 3. 电气 4. 结构 5. 管道
规则：必须包含"安全"；看到机械必须选"机械"；看到管道相关选"管道"。
输出 JSON 数组，如：["机械","安全","管道"]"""


# ==================== 配置管理器 (完全保留) ====================
class ConfigManager:
    @staticmethod
    def load():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {
            "api_key": "",
            "current_provider": "阿里百炼 (Qwen2.5-VL)",
            "last_prompt": "V4.6 安全质量双聚焦"
        }

    @staticmethod
    def save(config):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except: pass

# ==================== 辅助方法 ====================
def get_b64(path):
    """将本地图片转为 Base64，适配手机端引擎渲染"""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except: return ""

def parse_roles(text):
    try:
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m: return json.loads(m.group())
    except: pass
    return []

def build_ai_prompt(role, kb):
    return f"""你是【{role}】（{kb.get('role_desc', '')}）。
## 重大隐患清单
{chr(10).join(f'- {h}' for h in kb.get('critical_hazards', []))}
⚠️ 发现上述情形必须报告为"严重安全隐患"！
## 检查清单
{chr(10).join(kb.get('checklist', []))}
## 误判警示
{kb.get('anti_hallucination', '')}
## 输出格式（JSON 数组）
- risk_level: "严重安全隐患"/"一般安全隐患"/"严重质量缺陷"/"一般质量缺陷"
- issue: 【{role}】+ 具体描述
- regulation: 规范条文号
- correction: 整改措施
- confidence: 0.0-1.0"""

def parse_issues(text, role):
    issues = []
    try:
        clean = text.replace("```json", "").replace("```", "").strip()
        s, e = clean.find('['), clean.rfind(']') + 1
        if s != -1 and e:
            for item in json.loads(clean[s:e]):
                if isinstance(item, dict):
                    item["category"] = role
                    issues.append(item)
    except: pass
    return issues


# ==================== 主程序 (Flet) ====================
def main(page: ft.Page):
    page.title = "安全质检助手 V5.0"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = DS["bg"]
    page.padding = 0
    page.window.width = 390
    page.window.height = 844

    config = ConfigManager.load()
    tasks = []
    current_tab = 0

    # UI 全局组件
    home_list = ft.ListView(expand=True, spacing=10, padding=12)
    summary_list = ft.ListView(expand=True, spacing=10, padding=12)
    detail_list = ft.ListView(expand=True, spacing=10, padding=12)

    count_text = ft.Text("0/20", color=ft.colors.WHITE, size=13, weight=ft.FontWeight.BOLD)
    status_text = ft.Text("就绪", size=12, color=DS["text_secondary"])
    progress_bar = ft.ProgressBar(value=0, color=DS["primary"], bgcolor=DS["border"], height=4, visible=False)

    safe_prompt = config.get("last_prompt", "V4.6 安全质量双聚焦")
    if safe_prompt not in DEFAULT_PROMPTS: safe_prompt = list(DEFAULT_PROMPTS.keys())[0]
    prompt_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option(k) for k in DEFAULT_PROMPTS.keys()],
        value=safe_prompt, text_size=13, height=45, expand=True,
        border_color=DS["border"], bgcolor=DS["bg"]
    )

    detail_title_text = ft.Text("", color="white", size=15, weight=ft.FontWeight.BOLD, expand=True)
    detail_image = ft.Image(src_base64="", height=240, fit=ft.ImageFit.CONTAIN, visible=False)

    def show_toast(msg, success=True):
        color = DS["success"] if success else DS["danger"]
        page.open(ft.SnackBar(ft.Text(f"{'✓' if success else '✕'}  {msg}"), bgcolor=color, duration=2500))
        status_text.value = "就绪"
        page.update()

    def copy_to_clipboard(text):
        page.set_clipboard(text)
        show_toast("已复制到剪贴板")

    # ---------------- 核心工作线程 ----------------
    def analyze_task_thread(task, api_key, base_url, model, prompt_text):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            b64 = get_b64(task['path'])

            task['progress_msg'] = "🔍 智能分诊中..."
            page.update()

            rr = client.chat.completions.create(
                model=model, temperature=0.1,
                messages=[{"role": "system", "content": ROUTER_PROMPT},
                          {"role": "user", "content": [
                              {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                              {"type": "text", "text": "请分析施工内容并选派专家"}]}])

            roles = parse_roles(rr.choices[0].message.content)
            if not roles: roles = ["安全"]
            if "安全" not in roles: roles.append("安全")

            all_issues = []
            for idx, role in enumerate(roles):
                task['progress_msg'] = f"🔬 {role}专家分析 ({idx+1}/{len(roles)})"
                page.update()

                kb = REGULATION_DB.get(role, REGULATION_DB["安全"])
                resp = client.chat.completions.create(
                    model=model, temperature=0.3, max_tokens=4096,
                    messages=[{"role": "system", "content": build_ai_prompt(role, kb)},
                              {"role": "user", "content": [
                                  {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                  {"type": "text", "text": "请分析图片，找出所有问题。输出 JSON 数组。"}]}])
                
                all_issues.extend(parse_issues(resp.choices[0].message.content, role))

            task['status'] = 'done'
            task['data'] = all_issues
        except Exception as e:
            task['status'] = 'error'
            task['error'] = str(e)
            
        check_all_done()

    def check_all_done():
        analyzing_count = len([t for t in tasks if t['status'] == 'analyzing'])
        done_count = len([t for t in tasks if t['status'] in ('done', 'error')])
        total = len(tasks)
        
        if total > 0: progress_bar.value = done_count / total
            
        if analyzing_count == 0:
            progress_bar.visible = False
            total_issues = sum(len(t.get('data') or []) for t in tasks if t['status'] == 'done')
            status_text.value = f"分析完成，共 {total_issues} 个问题"
            show_toast(f"分析完成！发现 {total_issues} 个问题")
            
        render_home()
        if detail_view.visible and hasattr(detail_view, "current_task"):
            render_detail(detail_view.current_task)
        page.update()

    def start_analysis(e):
        config["last_prompt"] = prompt_dropdown.value
        ConfigManager.save(config)
        
        api_key = config.get("api_key", "")
        p_name = config.get("current_provider", "阿里百炼 (Qwen2.5-VL)")
        p_conf = PROVIDER_PRESETS.get(p_name, {})
        
        if not api_key:
            show_toast("请先在⚙设置中配置 API Key", False)
            open_settings()
            return
            
        waiting = [t for t in tasks if t['status'] in ('waiting', 'error')]
        if not waiting:
            show_toast("没有待分析的图片", False)
            return

        progress_bar.visible = True
        status_text.value = f"正在分析 {len(waiting)} 张..."
        prompt_text = config.get("prompts", DEFAULT_PROMPTS).get(prompt_dropdown.value, "")
        page.update()
        
        for t in waiting:
            t['status'] = 'analyzing'
            threading.Thread(target=analyze_task_thread, args=(t, api_key, p_conf.get("base_url"), p_conf.get("model"), prompt_text)).start()
            
        render_home()

    # ---------------- 选图逻辑 ----------------
    def on_files_selected(e: ft.FilePickerResultEvent):
        if e.files:
            allowed = MAX_IMAGES - len(tasks)
            if allowed <= 0:
                show_toast(f"最多支持 {MAX_IMAGES} 张", False)
                return
            added = 0
            for f in e.files[:allowed]:
                if any(t['path'] == f.path for t in tasks): continue
                tasks.append({"id": f"{time.time()}_{f.name}", "path": f.path, "name": f.name, "status": "waiting", "data": None})
                added += 1
            if added:
                count_text.value = f"{len(tasks)}/20"
                show_toast(f"已添加 {added} 张图片")
                render_home()
        page.navigation_bar.selected_index = current_tab
        page.update()

    file_picker = ft.FilePicker(on_result=on_files_selected)
    page.overlay.append(file_picker)

    # ---------------- UI 弹窗与组件 ----------------
    def build_risk_card(item, index, on_edit, on_delete, on_copy, on_detail):
        level = item.get("risk_level", "一般质量缺陷")
        st = RISK_STYLE.get(level, RISK_STYLE["一般质量缺陷"])
        
        issue_text = item.get("issue", "")
        if len(issue_text) > 60: issue_text = issue_text[:60] + "..."
        
        icons = []
        if item.get("regulation"): icons.append(ft.Text("📋", size=14))
        if item.get("correction"): icons.append(ft.Text("✅", size=14))
        
        return ft.Container(
            bgcolor=st['bg'], border=ft.border.all(1.5, st['border']), border_radius=14, padding=12,
            on_click=lambda e: on_detail(item),
            content=ft.Column([
                ft.Row([
                    ft.Container(content=ft.Text(str(index), color="white", size=11, weight=ft.FontWeight.BOLD), bgcolor=st["border"], width=24, height=24, alignment=ft.alignment.center, border_radius=12),
                    ft.Container(content=ft.Text(f"{st['icon']} {level}", color="white", size=12, weight=ft.FontWeight.BOLD), bgcolor=st["border"], padding=ft.padding.symmetric(horizontal=8, vertical=4), border_radius=7),
                    ft.Container(content=ft.Text(item.get("category",""), color=DS["text_secondary"], size=11), bgcolor=DS["surface"], border=ft.border.all(1, DS["border"]), padding=ft.padding.symmetric(horizontal=8, vertical=4), border_radius=7, visible=bool(item.get("category"))),
                    ft.Container(expand=True),
                    ft.TextButton("编辑", on_click=lambda e: on_edit(item), style=ft.ButtonStyle(color=DS["primary"], bgcolor=DS["info_light"], padding=2, shape=ft.RoundedRectangleBorder(radius=6))),
                    ft.TextButton("复制", on_click=lambda e: on_copy(item), style=ft.ButtonStyle(color=DS["primary"], bgcolor=DS["primary_light"], padding=2, shape=ft.RoundedRectangleBorder(radius=6))),
                    ft.TextButton("删除", on_click=lambda e: on_delete(item), style=ft.ButtonStyle(color=DS["danger"], bgcolor=DS["danger_light"], padding=2, shape=ft.RoundedRectangleBorder(radius=6))),
                ]),
                ft.Text(issue_text, size=14, color=DS["text_primary"], weight=ft.FontWeight.W_500),
                ft.Text("💬 点击查看详情", size=11, color=DS["text_hint"], italic=True),
                ft.Divider(color=DS["border"], height=1),
                ft.Row([
                    ft.Row(icons, spacing=10),
                    ft.Container(expand=True),
                    ft.Text(f"置信度 {int(item.get('confidence',0)*100)}%", size=11, color=DS["text_hint"], visible=bool(item.get('confidence')))
                ])
            ], spacing=8)
        )

    def show_edit_dialog(item, on_save):
        cbo = ft.Dropdown(options=[ft.dropdown.Option("严重安全隐患"), ft.dropdown.Option("一般安全隐患"), ft.dropdown.Option("严重质量缺陷"), ft.dropdown.Option("一般质量缺陷")], value=item.get("risk_level", "一般质量缺陷"), text_size=14)
        edt_iss = ft.TextField(value=item.get("issue",""), multiline=True, min_lines=3, text_size=14)
        edt_reg = ft.TextField(value=item.get("regulation",""), multiline=True, min_lines=2, text_size=14)
        edt_cor = ft.TextField(value=item.get("correction",""), multiline=True, min_lines=2, text_size=14)
        
        dialog = ft.AlertDialog(title=ft.Text("✏️ 编辑问题"))
        def save(e):
            item.update({"risk_level": cbo.value, "issue": edt_iss.value, "regulation": edt_reg.value, "correction": edt_cor.value})
            page.close(dialog)
            on_save()
            show_toast("✓ 已保存修改")

        dialog.content = ft.Column([ft.Text("风险等级", weight="bold"), cbo, ft.Text("问题描述", weight="bold"), edt_iss, ft.Text("规范依据", weight="bold"), edt_reg, ft.Text("整改措施", weight="bold"), edt_cor], scroll=ft.ScrollMode.AUTO, tight=True)
        dialog.actions = [ft.TextButton("取消", on_click=lambda e: page.close(dialog)), ft.ElevatedButton("保存", on_click=save, bgcolor=DS["primary"], color="white")]
        page.open(dialog)

    def show_detail_dialog(item):
        st = RISK_STYLE.get(item.get("risk_level", "一般质量缺陷"), RISK_STYLE["一般质量缺陷"])
        dialog = ft.AlertDialog(title=ft.Text("📋 问题详情"))
        dialog.content = ft.Column([
            ft.Container(content=ft.Text(f"{st['icon']} {item.get('risk_level')}", color="white", weight="bold"), bgcolor=st["border"], padding=8, border_radius=8),
            ft.Divider(),
            ft.Text("📝 问题描述", weight="bold"), ft.Text(item.get("issue",""), size=14),
            ft.Text("📋 规范依据", weight="bold", visible=bool(item.get("regulation"))), ft.Text(item.get("regulation",""), size=13, color=DS["text_secondary"], visible=bool(item.get("regulation"))),
            ft.Text("✅ 整改措施", color=DS["success"], weight="bold", visible=bool(item.get("correction"))), ft.Text(item.get("correction",""), size=13, visible=bool(item.get("correction")))
        ], scroll=ft.ScrollMode.AUTO, tight=True)
        dialog.actions = [ft.ElevatedButton("关闭", on_click=lambda e: page.close(dialog), bgcolor=DS["primary"], color="white")]
        page.open(dialog)

    def show_delete_confirm(item, on_confirm):
        dialog = ft.AlertDialog(title=ft.Text("确认删除"))
        def confirm(e):
            page.close(dialog)
            on_confirm()
            show_toast("✓ 已删除")
        dialog.content = ft.Text(f"确定要删除这个问题吗？\n\n{item.get('issue', '')[:50]}...")
        dialog.actions = [ft.TextButton("取消", on_click=lambda e: page.close(dialog)), ft.ElevatedButton("确定", on_click=confirm, bgcolor=DS["danger"], color="white")]
        page.open(dialog)

    def open_settings():
        key_inp = ft.TextField(value=config.get("api_key",""), password=True, can_reveal_password=True, text_size=14)
        prov_drop = ft.Dropdown(options=[ft.dropdown.Option(k) for k in PROVIDER_PRESETS.keys()], value=config.get("current_provider"), text_size=14)
        
        dialog = ft.AlertDialog(title=ft.Text("⚙ 设置"))
        def save(e):
            config["api_key"] = key_inp.value
            config["current_provider"] = prov_drop.value
            ConfigManager.save(config)
            page.close(dialog)
            page.navigation_bar.selected_index = current_tab
            show_toast("设置已保存 ✓")

        dialog.content = ft.Column([ft.Text("🔑 API KEY", size=12, weight="bold", color=DS["text_hint"]), key_inp, ft.Text("🤖 模型厂商", size=12, weight="bold", color=DS["text_hint"]), prov_drop], tight=True)
        dialog.actions = [ft.TextButton("取消", on_click=lambda e: page.close(dialog) or setattr(page.navigation_bar, 'selected_index', current_tab) or page.update()), ft.ElevatedButton("保存", on_click=save, bgcolor=DS["primary"], color="white")]
        page.open(dialog)

    # ---------------- 页面渲染 ----------------
    def render_home():
        home_list.controls.clear()
        if not tasks:
            home_list.controls.append(ft.Container(content=ft.Column([ft.Text("📷", size=60), ft.Text("添加施工图片", size=19, weight="bold"), ft.Text("点击下方 ➕ 添加图片", size=14, color=DS["text_secondary"])], horizontal_alignment="center", alignment="center"), expand=True, alignment=ft.alignment.center))
        else:
            for t in tasks:
                icon, color, text = "⏳", DS["text_hint"], "等待中"
                if t['status'] == 'analyzing': icon, color, text = "🔄", DS["primary"], t.get('progress_msg', '分析中')
                elif t['status'] == 'done': icon, color, text = "✅", DS["success"], f"发现 {len(t['data'])} 个问题" if t['data'] else "未发现问题"
                elif t['status'] == 'error': icon, color, text = "❌", DS["danger"], t.get('error', '失败')[:20]

                home_list.controls.append(
                    ft.Container(
                        bgcolor=DS["surface"], border_radius=12, border=ft.border.all(1, DS["border"]), padding=10,
                        on_click=lambda e, t=t: open_detail(t),
                        content=ft.Row([
                            ft.Image(src_base64=get_b64(t['path']), width=50, height=50, fit=ft.ImageFit.COVER, border_radius=8),
                            ft.Column([ft.Text(t['name'], size=14, weight="bold"), ft.Text(text, size=12, color=color)], expand=True, spacing=2),
                            ft.Text(icon, size=20), ft.Text("›", size=20, color=DS["text_hint"])
                        ])
                    )
                )
        page.update()

    def render_summary():
        summary_list.controls.clear()
        all_issues = [i for t in tasks if t['status'] == 'done' and t.get('data') for i in [dict(item, _src=t['name']) for item in t['data']]]
                    
        if not all_issues:
            summary_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, border=ft.border.all(1, DS["border"]), padding=30, content=ft.Column([ft.Text("📊", size=52), ft.Text("暂无分析结果", size=17, weight="bold"), ft.Text("请先主页添加并分析", size=13, color=DS["text_secondary"])], horizontal_alignment="center")))
        else:
            counts = {}
            for iss in all_issues: counts[iss.get("risk_level","")] = counts.get(iss.get("risk_level",""),0)+1
            stat_row = ft.Row(wrap=True, spacing=8)
            for lvl in ["严重安全隐患","一般安全隐患","严重质量缺陷","一般质量缺陷"]:
                if counts.get(lvl,0):
                    st = RISK_STYLE[lvl]
                    stat_row.controls.append(ft.Container(content=ft.Text(f"{st['icon']} {lvl[:4]} {counts[lvl]}个", size=12, color=st['border'], weight="bold"), bgcolor=st['bg'], border=ft.border.all(1, st['border']), border_radius=8, padding=ft.padding.symmetric(horizontal=10, vertical=5)))
            
            summary_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=12, border=ft.border.all(1, DS["border"]), padding=14, content=ft.Column([ft.Text(f"共发现 {len(all_issues)} 个问题", size=16, weight="bold"), stat_row])))
            
            for i, issue in enumerate(sorted(all_issues, key=lambda x: RISK_STYLE.get(x.get("risk_level",""), RISK_STYLE["一般质量缺陷"])["priority"]), 1):
                summary_list.controls.append(ft.Text(f"  📷 {issue.get('_src','')}", size=11, color=DS["text_hint"]))
                e_cb = lambda it, it_ref=issue: show_edit_dialog(it_ref, render_summary)
                d_cb = lambda it, it_ref=issue: show_delete_confirm(it_ref, lambda: [tk.__setitem__('data', [i for i in tk['data'] if i is not it_ref]) for tk in tasks if tk.get('data')] or render_summary())
                c_cb = lambda it: copy_to_clipboard(f"【{it.get('risk_level','')}】\n{it.get('issue','')}\n\n📋 依据：{it.get('regulation','')}\n✅ 整改：{it.get('correction','')}")
                det_cb = lambda it: show_detail_dialog(it)
                summary_list.controls.append(build_risk_card(issue, i, e_cb, d_cb, c_cb, det_cb))

    def render_detail(task):
        detail_list.controls.clear()
        if task['status'] == 'waiting': detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, padding=30, content=ft.Column([ft.Text("⏳", size=48), ft.Text("等待分析", size=17, weight="bold", color=DS["text_hint"])], horizontal_alignment="center")))
        elif task['status'] == 'analyzing': detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, padding=30, content=ft.Column([ft.Text("🔄", size=48), ft.Text("正在分析...", size=17, weight="bold", color=DS["primary"]), ft.Text(task.get('progress_msg',''), size=13, color=DS["text_secondary"])], horizontal_alignment="center")))
        elif task['status'] == 'error': detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, padding=30, content=ft.Column([ft.Text("❌", size=48), ft.Text("分析失败", size=17, weight="bold", color=DS["danger"]), ft.Text(task.get('error',''), size=13)], horizontal_alignment="center")))
        elif task['status'] == 'done':
            data = task.get('data') or []
            if not data: detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, padding=30, content=ft.Column([ft.Text("✅", size=48), ft.Text("未发现问题", size=17, weight="bold", color=DS["success"])], horizontal_alignment="center")))
            else:
                for i, item in enumerate(sorted(data, key=lambda x: RISK_STYLE.get(x.get("risk_level",""), RISK_STYLE["一般质量缺陷"])["priority"]), 1):
                    e_cb = lambda it, it_ref=item: show_edit_dialog(it_ref, lambda: render_detail(task) or page.update())
                    d_cb = lambda it, it_ref=item: show_delete_confirm(it_ref, lambda: task.__setitem__('data', [x for x in task['data'] if x is not it_ref]) or render_detail(task) or page.update())
                    c_cb = lambda it: copy_to_clipboard(f"【{it.get('risk_level','')}】\n{it.get('issue','')}\n\n📋 依据：{it.get('regulation','')}\n✅ 整改：{it.get('correction','')}")
                    det_cb = lambda it: show_detail_dialog(it)
                    detail_list.controls.append(build_risk_card(item, i, e_cb, d_cb, c_cb, det_cb))

    def copy_all():
        issues = [i for t in tasks if t['status'] == 'done' and t.get('data') for i in [dict(item, _src=t['name']) for item in t['data']]]
        if not issues: return show_toast("暂无可复制的问题", False)
        lines = ["🏗️ 质量安全检查问题清单", f"检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", f"发现问题：{len(issues)} 个", "=" * 40, ""]
        for i, iss in enumerate(sorted(issues, key=lambda x: RISK_STYLE.get(x.get('risk_level', ''), {"priority":4})["priority"]), 1):
            lines += [f"{i}. 【{iss.get('risk_level', '')}】", f"   来源：{iss.get('_src', '')}", f"   {iss.get('issue', '')}", f"   📋 依据：{iss.get('regulation', '')}", f"   ✅ 整改：{iss.get('correction', '')}", ""]
        copy_to_clipboard("\n".join(lines))

    def clear_all():
        if not tasks: return
        dialog = ft.AlertDialog(title=ft.Text("确认清空"), content=ft.Text("确定要清空所有图片吗？"))
        def conf(e):
            tasks.clear()
            count_text.value = "0/20"
            render_home()
            page.close(dialog)
            show_toast("队列已清空")
        dialog.actions = [ft.TextButton("取消", on_click=lambda e: page.close(dialog)), ft.ElevatedButton("确定", on_click=conf, bgcolor=DS["danger"], color="white")]
        page.open(dialog)

    # ---------------- 视图容器 (SPA 切换) ----------------
    v_home = ft.Column([
        ft.Container(bgcolor=DS["primary"], height=56, padding=ft.padding.symmetric(horizontal=16), content=ft.Row([ft.Text("🏗️ 安全质检助手 V5.0", color="white", size=17, weight="bold", expand=True), count_text])),
        ft.Container(bgcolor=DS["surface"], padding=10, border=ft.border.only(bottom=ft.BorderSide(1, DS["border"])), content=ft.Row([ft.Text("检查场景", size=13), prompt_dropdown])),
        ft.Container(content=home_list, expand=True), progress_bar,
        ft.Container(bgcolor=DS["surface"], height=68, padding=10, border=ft.border.only(top=ft.BorderSide(1, DS["border"])), content=ft.Row([
            ft.ElevatedButton("🗑 清空", on_click=lambda e: clear_all(), bgcolor=DS["surface2"], color=DS["text_secondary"]),
            ft.ElevatedButton("📋 复制全部", on_click=lambda e: copy_all(), bgcolor=DS["success_light"], color=DS["success"]),
            ft.ElevatedButton("▶ 开始分析", on_click=start_analysis, bgcolor=DS["primary"], color="white", expand=True)
        ])),
        ft.Container(content=status_text, padding=ft.padding.only(left=14, bottom=4))
    ], expand=True, spacing=0)
    
    v_summary = ft.Column([
        ft.Container(bgcolor=DS["primary"], height=56, padding=16, content=ft.Text("📊 问题汇总", color="white", size=17, weight="bold")),
        ft.Container(content=summary_list, expand=True),
        ft.Container(bgcolor=DS["surface"], height=68, padding=10, border=ft.border.only(top=ft.BorderSide(1, DS["border"])), content=ft.Row([
            ft.ElevatedButton("📋 复制全部问题", on_click=lambda e: copy_all(), bgcolor=DS["primary"], color="white", expand=True)
        ]))
    ], expand=True, spacing=0, visible=False)
    
    v_detail = ft.Column([
        ft.Container(bgcolor=DS["primary"], height=56, padding=ft.padding.symmetric(horizontal=10), content=ft.Row([
            ft.IconButton(ft.icons.ARROW_BACK_IOS_NEW, icon_color="white", on_click=lambda e: close_detail()), detail_title_text
        ])), detail_image, ft.Container(content=detail_list, expand=True)
    ], expand=True, spacing=0, visible=False)
    
    main_stack = ft.Stack([v_home, v_summary, v_detail], expand=True)

    def on_nav(e):
        nonlocal current_tab
        idx = e.control.selected_index
        if idx == 0:
            current_tab = 0; v_home.visible = True; v_summary.visible = False; v_detail.visible = False; page.update()
        elif idx == 1:
            current_tab = 1; render_summary(); v_home.visible = False; v_summary.visible = True; v_detail.visible = False; page.update()
        elif idx == 2: file_picker.pick_files(allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE)
        elif idx == 3: open_settings()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0, bgcolor=DS["surface"],
        destinations=[ft.NavigationDestination(icon=ft.icons.HOME, label="主页"), ft.NavigationDestination(icon=ft.icons.BAR_CHART, label="汇总"), ft.NavigationDestination(icon=ft.icons.ADD_PHOTO_ALTERNATE, label="添加"), ft.NavigationDestination(icon=ft.icons.SETTINGS, label="设置")],
        on_change=on_nav
    )

    def open_detail(task):
        v_detail.current_task = task
        detail_title_text.value = f"  {task['name']}"
        detail_image.src_base64 = get_b64(task['path'])
        detail_image.visible = True
        render_detail(task)
        v_home.visible = False; v_summary.visible = False; v_detail.visible = True
        page.update()
        
    def close_detail():
        v_detail.visible = False
        if current_tab == 0: v_home.visible = True
        elif current_tab == 1: v_summary.visible = True
        page.update()

    page.add(ft.Container(content=main_stack, expand=True))
    render_home()

if __name__ == "__main__":
    ft.app(main)

