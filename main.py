#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建设工程质量安全检查助手 - 手机版 V4.6 (Flet重构 极致稳定版)
修复说明：
1. 修复 Flet 渲染本地绝对路径图片导致前端卡死在 "work..." 的问题 (采用 Base64 实时渲染)。
2. 修复 Flet 0.25+ 版本废弃 page.dialog 导致的静默报错，升级为 page.open()。
3. 增加全局异常捕获，即使出错也会将错误打印在屏幕上，告别死锁白屏。
4. 全量保留 11 个专业提示词和业务逻辑。
"""

import os, json, base64, time, re, threading
from datetime import datetime
from typing import Dict, List

import flet as ft
from openai import OpenAI

# ==================== 全局配置 ====================
CONFIG_FILE = "app_config_mobile_v4.json"
MAX_IMAGES = 20

DS = {
    "primary":       "#1A56DB",
    "primary_light": "#EBF0FF",
    "primary_dark":  "#1145B0",
    "danger":        "#E02424",
    "danger_light":  "#FDE8E8",
    "warning":       "#D03801",
    "warning_light": "#FEF3C7",
    "success":       "#057A55",
    "success_light": "#DEF7EC",
    "info":          "#1A56DB",
    "info_light":    "#E1EFFE",
    "bg":            "#F3F4F6",
    "surface":       "#FFFFFF",
    "surface2":      "#F9FAFB",
    "text_primary":  "#111928",
    "text_secondary":"#6B7280",
    "text_hint":     "#9CA3AF",
    "border":        "#E5E7EB",
    "nav_active":    "#1A56DB",
    "nav_inactive":  "#9CA3AF",
}

RISK_STYLE = {
    "严重安全隐患": {"bg": "#FDE8E8", "border": "#E02424", "icon": "🔴", "priority": 0, "badge_bg": "#E02424"},
    "一般安全隐患": {"bg": "#FEF3C7", "border": "#D03801", "icon": "🟠", "priority": 1, "badge_bg": "#D03801"},
    "严重质量缺陷": {"bg": "#FFFBEB", "border": "#B45309", "icon": "🟡", "priority": 2, "badge_bg": "#B45309"},
    "一般质量缺陷": {"bg": "#E1EFFE", "border": "#1A56DB", "icon": "🔵", "priority": 3, "badge_bg": "#1A56DB"},
}

PROVIDER_PRESETS = {
    "阿里百炼 (Qwen-VL-Max)":  {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-vl-max"},
    "阿里百炼 (Qwen2.5-VL)":   {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen2.5-vl-72b"},
    "硅基流动 (Qwen2-VL)":     {"base_url": "https://api.siliconflow.cn/v1",                    "model": "Qwen/Qwen2-VL-72B-Instruct"},
    "自定义":                   {"base_url": "", "model": ""},
}

DEFAULT_PROMPTS = {
    "V4.6 安全质量双聚焦": "聚焦安全隐患 + 质量问题",
    "安全隐患专项": "仅识别安全隐患（忽略质量）",
    "质量问题专项": "仅识别质量问题（忽略安全）",
    "高危风险筛查": "仅识别严重安全隐患",
}

# ==================== V4.6 版提示词系统 ====================
ROUTER_SYSTEM_PROMPT = """
你是一名拥有 25 年经验的工程建设总监。请扫描施工现场图片，快速识别核心施工内容，指派 **3-5 名** 最对口的硬核技术专家。

### 必须从以下 11 个角色中选择（严禁编造其他角色）：
1. **管道** 2. **电气** 3. **结构** 4. **机械** 5. **基坑**
6. **消防** 7. **暖通** 8. **给排水** 9. **防水** 10. **环保** 11. **水利**

### 强制规则：
1. 始终包含 **安全** 专家。
2. 如果画面模糊或无特定专业内容，仅输出 ["安全"]。
3. **看到以下任一情形，必须选派"机械"专家**：
   - 挖掘机、装载机、推土机、压路机等工程机械
   - 塔吊、施工升降机、物料提升机
   - 汽车吊、履带吊等起重机械
   - 吊篮、高处作业吊篮
   - 混凝土泵车、搅拌机
4. **看到以下任一情形，必须选派"水利"专家**：
   - 大坝、堤防、围堰施工
   - 溢洪道、消力池、泄洪洞
   - 渠道、渡槽、倒虹吸
   - 水闸、泵站、水电站
   - 隧洞开挖、高边坡支护
   - 帷幕灌浆、土工膜铺设
5. 输出必须是 JSON 字符串列表。

示例：看到挖掘机作业 → `["机械", "安全"]`
示例：看到塔吊 → `["机械", "安全", "结构"]`
示例：看到大坝填筑 → `["水利", "安全", "机械"]`
示例：看到隧洞开挖 → `["水利", "安全", "机械"]`
示例：只有工人 → `["安全"]`
"""

SPECIALIST_PROMPT_TEMPLATE_V6 = """
你是一名【{role}】（{role_desc}），拥有 30 年一线经验。你刚检查完现场，现在要写**整改通知单**。

## 你的任务
对图片进行**工艺级找茬**，识别**具体违规事实**，不是泛泛而谈。

## 典型重大隐患清单（必须重点检查）
{critical_hazards}

⚠️ **如果发现上述任一情形，必须立即报告为"严重安全隐患"**！

## 深度检查清单（按此逐项扫描）
{checklist}

## 必须报告的情形
{must_report_if}

✅ **发现上述任一情形，直接报告，不要犹豫**！

## 核心规范依据（引用条文必须准确）
{norms}

## 误判警示（以下情况不要误报）
{anti_hallucination}

## 输出格式要求（JSON 数组）
每个问题必须包含：
- **risk_level**: "严重安全隐患" / "一般安全隐患" / "严重质量缺陷" / "一般质量缺陷"
- **issue**: 【{role}】+ 具体描述（说人话，不要套话）
- **regulation**: 规范条文号（如"GB 50242-2002 第 3.3.15 条"）
- **correction**: 整改措施（具体可执行，如"立即停工，更换合格管材"）
- **bbox**: [x1, y1, x2, y2]（问题位置坐标）
- **confidence**: 0.0-1.0（置信度，不确定给 0.6-0.7）

**输出示例**:
[
  {{
    "risk_level": "严重安全隐患",
    "issue": "【机械】使用挖掘机进行吊装作业（吊钩挂在挖掘机铲斗上吊运钢筋）",
    "regulation": "JGJ 33-2012《建筑机械使用安全技术规程》第 4.1.14 条",
    "correction": "立即停止违章作业，使用合格起重设备进行吊装",
    "bbox": [120, 150, 480, 320],
    "confidence": 0.98
  }}
]

## 最后强调
1. 不要说"可能存在""疑似"，要给出明确判断
2. 不要说"建议"，要说"必须""立即"
3. 问题描述要具体，如"DN100 止回阀装反"而不是"阀门安装不规范"
4. 看到典型重大隐患，必须报告为"严重安全隐患"
"""

REGULATION_DATABASE_V6 = {
    "管道": {
        "role_desc": "管道与阀门工艺专家 | 30 年压力管道安装经验",
        "critical_hazards": ["压力管道使用非压力管道管材", "阀门无标识或标识错误", "法兰垫片使用错误", "管道支吊架间距过大导致管道下垂", "补偿器未做预拉伸或限位措施"],
        "norms": "### GB 50242-2002《建筑给水排水及采暖工程施工质量验收规范》\n**第 3.3.13 条** 法兰连接螺栓紧固后露出螺母 2-3 扣\n**第 3.3.15 条** 阀门安装方向正确\n### TSG D0001-2009《压力管道安全技术监察规程》\n**第 110 条** 安装前进行外观检查",
        "checklist": ["管道颜色标识是否错误", "法兰螺栓是否露牙不足或过长", "阀门手轮方向是否向下", "支吊架间距是否过大", "焊缝外观是否有裂纹"],
        "must_report_if": ["发现管道有凹陷、裂纹、严重腐蚀", "发现法兰垫片外露不均匀", "发现管道支吊架锈蚀严重"],
        "anti_hallucination": "临时封堵盲板不是缺阀门；试压用临时支撑不是支架不足"
    },
    "电气": {
        "role_desc": "注册电气工程师 | 30 年变配电及施工现场经验",
        "critical_hazards": ["临时用电未采用 TN-S 接零保护系统", "配电箱未做重复接地", "一闸多机", "电缆直接拖地或浸水", "带电体裸露无防护罩"],
        "norms": "### GB 50303-2015《建筑电气工程施工质量验收规范》\n**第 12.1.1 条** 金属桥架必须接地\n### JGJ 46-2005《施工现场临时用电安全技术规范》\n**第 8.1.3 条** 每台用电设备必须有各自专用的开关箱",
        "checklist": ["黄绿双色线是否用作他途", "配电箱门是否有跨接软铜线", "插座接线是否左零右火上接地", "电缆是否直接拖地"],
        "must_report_if": ["发现电线绝缘层破损", "发现开关箱内积水", "发现漏电保护器失效", "发现配电箱未上锁"],
        "anti_hallucination": "施工中临时接线待整理不属于严重违规"
    },
    "结构": {
        "role_desc": "结构总工程师 | 30 年混凝土及钢结构经验",
        "critical_hazards": ["模板支撑体系立杆悬空", "高大模板未设置扫地杆、剪刀撑", "钢筋主筋位置错误", "混凝土浇筑后出现贯穿裂缝", "钢结构高强螺栓未终拧"],
        "norms": "### GB 50204-2015《混凝土结构工程施工质量验收规范》\n### JGJ 162-2008《建筑施工模板安全技术规范》\n**第 6.1.2 条** 模板支架立杆底部必须设置垫板",
        "checklist": ["立杆底部是否悬空", "钢筋间距是否明显不均匀", "混凝土是否有裂缝", "模板是否鼓胀下沉"],
        "must_report_if": ["发现模板支撑松动", "发现钢筋规格型号不符", "发现混凝土蜂窝夹渣"],
        "anti_hallucination": "温度裂缝(发丝状)不是结构裂缝"
    },
    "机械": {
        "role_desc": "起重机械专家 | 30 年塔吊施工升降机安拆经验",
        "critical_hazards": ["【致命】使用非吊装机械进行吊装作业", "【致命】塔吊力矩限制器失效", "钢丝绳断丝超过 10%", "特种作业人员无证操作"],
        "norms": "### GB 5144-2006《塔式起重机安全规程》\n### JGJ 33-2012《建筑机械使用安全技术规程》\n**第 4.1.14 条** 严禁使用挖掘机等非起重机械进行吊装作业。",
        "checklist": ["是否用挖掘机/装载机吊物", "限位器是否失效", "钢丝绳是否断丝压扁", "防脱钩装置是否缺失"],
        "must_report_if": ["发现起重机械超负荷使用", "发现多塔作业无防碰撞措施"],
        "anti_hallucination": "设备表面轻微锈迹不是缺陷"
    },
    "基坑": {
        "role_desc": "岩土工程师 | 30 年深基坑支护及降水经验",
        "critical_hazards": ["基坑开挖超过 5m 无专项方案", "基坑边堆载超过设计荷载", "支护结构出现裂缝位移", "基坑监测数据超预警值未停工"],
        "norms": "### JGJ 120-2012《建筑基坑支护技术规程》\n**第 8.1.1 条** 基坑周边 1m 范围内不得堆载",
        "checklist": ["坑边 1m 内是否有堆土堆料", "临边防护是否缺失", "坑底是否有大面积积水管涌"],
        "must_report_if": ["发现支护结构有明显变形", "发现基坑周边地面开裂"],
        "anti_hallucination": "临时堆土待运不是违规"
    },
    "消防": {
        "role_desc": "注册消防工程师 | 30 年施工现场消防管理经验",
        "critical_hazards": ["氧气瓶与乙炔瓶混放或间距不足 5m", "气瓶无防震圈防倾倒措施", "动火作业无监护人无灭火器", "消防通道堵塞"],
        "norms": "### GB 50720-2011《建设工程施工现场消防安全技术规范》\n**第 5.3.7 条** 氧气瓶与乙炔瓶工作间距不小于 5m",
        "checklist": ["气瓶间距是否小于 5m", "动火作业是否无监护人", "灭火器是否压力不足", "工人宿舍是否使用大功率电器"],
        "must_report_if": ["发现乙炔瓶卧放使用", "发现消防栓无水"],
        "anti_hallucination": "空瓶待运可横放"
    },
    "安全": {
        "role_desc": "注册安全工程师 | 30 年施工现场安全管理经验",
        "critical_hazards": ["【致命】使用挖掘机等违章吊装", "高处作业不系安全带", "安全帽未系下颌带", "临边洞口防护缺失", "脚手架未满铺脚手板"],
        "norms": "### JGJ 59-2011《建筑施工安全检查标准》\n**第 3.2.5 条** 必须正确佩戴安全帽\n**第 5.1.1 条** 高处作业必须系安全带",
        "checklist": ["工人是否未系下颌带", "2m以上高处作业是否无安全带", "1.2m护栏是否缺失", "预留洞口是否有固定盖板"],
        "must_report_if": ["发现安全防护设施被拆除", "发现特种作业无证操作"],
        "anti_hallucination": "地面作业不强制系安全带，休息区可不戴安全帽"
    },
    "暖通": {
        "role_desc": "暖通工程师 | 30 年通风空调及采暖经验",
        "critical_hazards": ["风管穿越防火分区未设防火阀", "排烟管道未做独立支吊架", "空调冷热水管道结露", "风机盘管倒坡"],
        "norms": "### GB 50243-2016《通风与空调工程施工质量验收规范》\n**第 6.2.3 条** 防火阀必须设独立支吊架",
        "checklist": ["风管支吊架间距是否过大", "保温层是否破损", "防火阀位置是否错误"],
        "must_report_if": ["发现风管漏光漏风", "发现设备运行异常噪音"],
        "anti_hallucination": "调试阶段部分阀门未开启正常"
    },
    "给排水": {
        "role_desc": "给排水工程师 | 30 年市政及给排水经验",
        "critical_hazards": ["排水管道倒坡", "压力管道未做强度试验", "消防管道阀门常闭未锁定"],
        "norms": "### GB 50268-2008《给水排水管道工程施工及验收规范》\n**第 5.3.1 条** 管道不得直接放在原状土上",
        "checklist": ["排水管道是否倒坡", "大口径管道是否无支墩", "地漏水封深度是否不足"],
        "must_report_if": ["发现管道渗漏", "发现阀门启闭不灵活"],
        "anti_hallucination": "施工阶段未通水正常"
    },
    "防水": {
        "role_desc": "防水工程师 | 30 年屋面及地下防水经验",
        "critical_hazards": ["地下室底板防水层破损", "屋面卷材搭接宽度不足", "卫生间防水层未上翻", "防水保护层未及时施工"],
        "norms": "### GB 50207-2012《屋面工程质量验收规范》\n**第 4.3.1 条** 卷材搭接宽度不达标",
        "checklist": ["卷材搭接是否不足 100mm", "阴阳角是否未做圆弧", "管根周围是否无附加层"],
        "must_report_if": ["发现防水层起鼓开裂", "发现防水层裸露未保护"],
        "anti_hallucination": "施工缝处轻微潮湿不是渗漏"
    },
    "环保": {
        "role_desc": "环境工程师 | 30 年施工现场环保经验",
        "critical_hazards": ["裸土未覆盖", "未设置围挡或围挡破损", "污水直排", "建筑垃圾焚烧"],
        "norms": "### GB 50720-2011《建设工程施工现场环境与卫生标准》\n**第 4.2.1 条** 裸露场地应采取覆盖",
        "checklist": ["裸土是否绿色密目网全覆盖", "沉淀池是否未定期清淤", "出入口是否无洗车槽"],
        "must_report_if": ["发现扬尘污染严重", "发现垃圾私自焚烧"],
        "anti_hallucination": "少量生活垃圾分类存放待运不违规"
    },
    "水利": {
        "role_desc": "水利水电工程总工 | 30 年大坝围堰经验",
        "critical_hazards": ["【致命】围堰填筑未按方案分层碾压", "【致命】高边坡开挖无支护", "大坝填筑料含水率超标"],
        "norms": "### SL 714-2015《水利水电工程施工安全管理导则》\n**第 6.1.3 条** 高边坡、隧洞必须设置安全监测点",
        "checklist": ["围堰是否一次性填筑过高", "隧洞开挖初喷厚度是否不足", "混凝土面板是否有贯穿裂缝"],
        "must_report_if": ["发现围堰渗漏管涌险情", "发现高边坡有掉块裂缝"],
        "anti_hallucination": "临时排水沟不是永久排水"
    }
}


# ==================== 配置管理器 ====================
class ConfigManager:
    @staticmethod
    def load():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {"api_key": "", "current_provider": "阿里百炼 (Qwen2.5-VL)",
                "prompts": DEFAULT_PROMPTS, "last_prompt": "V4.6 安全质量双聚焦",
                "custom_provider_settings": {"base_url": "", "model": ""}}

    @staticmethod
    def save(config):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except: pass


# ==================== Flet 主程序 (极限防崩溃外壳) ====================
def main(page: ft.Page):
    try:
        _run_app(page)
    except Exception as e:
        import traceback
        page.add(ft.Text(f"系统启动发生致命错误:\n\n{traceback.format_exc()}", color="red", selectable=True))
        page.update()

def _run_app(page: ft.Page):
    page.title = "安全质检助手 V4.6"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = DS["bg"]
    page.padding = 0
    page.window.width = 390
    page.window.height = 844

    config = ConfigManager.load()
    tasks = []
    current_tab = 0  # 全局控制导航栏状态
    
    # === 核心 UI 组件 ===
    home_list = ft.ListView(expand=True, spacing=10, padding=12)
    summary_list = ft.ListView(expand=True, spacing=10, padding=12)
    detail_list = ft.ListView(expand=True, spacing=10, padding=12)
    
    empty_state = ft.Container(
        content=ft.Column([
            ft.Text("📷", size=60),
            ft.Text("添加施工图片", size=19, weight=ft.FontWeight.BOLD, color=DS["text_primary"]),
            ft.Text("点击下方 ➕ 添加图片\n最多支持 20 张", size=14, color=DS["text_secondary"], text_align=ft.TextAlign.CENTER),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
        expand=True, alignment=ft.alignment.center
    )
    
    count_text = ft.Text("0/20", color=ft.colors.WHITE, size=13, weight=ft.FontWeight.BOLD)
    status_text = ft.Text("就绪", size=12, color=DS["text_secondary"])
    progress_bar = ft.ProgressBar(value=0, color=DS["primary"], bgcolor=DS["border"], height=4, visible=False)
    
    # 防止读取异常的配置
    safe_prompt = config.get("last_prompt", "V4.6 安全质量双聚焦")
    if safe_prompt not in DEFAULT_PROMPTS: safe_prompt = list(DEFAULT_PROMPTS.keys())[0]
    prompt_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option(k) for k in DEFAULT_PROMPTS.keys()],
        value=safe_prompt, text_size=13, height=45, expand=True,
        border_color=DS["border"], bgcolor=DS["bg"]
    )

    detail_title_text = ft.Text("", color="white", size=15, weight=ft.FontWeight.BOLD, expand=True)
    # 🚨 极其关键：初始图片不可见且无源，避免引擎崩溃
    detail_image = ft.Image(src_base64="", height=240, fit=ft.ImageFit.CONTAIN, visible=False)

    # ---------------- 辅助方法 ----------------
    def show_toast(msg, success=True):
        color = DS["success"] if success else DS["danger"]
        page.open(ft.SnackBar(ft.Text(f"{'✓' if success else '✕'}  {msg}"), bgcolor=color, duration=2500))
        status_text.value = "就绪"
        page.update()

    def copy_to_clipboard(text):
        page.set_clipboard(text)
        show_toast("已复制到剪贴板")
        
    def get_b64(path):
        """核心修复：将本地图片转Base64，解决移动端绝对路径渲染崩溃死锁问题"""
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except: return ""

    # ---------------- 分析逻辑线程 ----------------
    def worker_thread(task, api_key, base_url, model, prompt_text):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            b64 = get_b64(task['path'])

            task['progress_msg'] = "🔍 智能分诊中..."
            page.update()

            rr = client.chat.completions.create(
                model=model, temperature=0.1,
                messages=[{"role":"system","content":ROUTER_SYSTEM_PROMPT},
                          {"role":"user","content":[
                              {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
                              {"type":"text","text":"请分析施工内容并选派专家"}]}])
            
            roles = []
            try:
                m = re.search(r'\[.*?\]', rr.choices[0].message.content, re.DOTALL)
                if m: roles = json.loads(m.group())
            except: pass
            if not roles: roles = ["安全"]
            if "安全" not in roles: roles.append("安全")

            all_issues = []
            for idx, role in enumerate(roles):
                task['progress_msg'] = f"🔬 {role}专家分析 ({idx+1}/{len(roles)})"
                page.update()
                
                kb = REGULATION_DATABASE_V6.get(role, REGULATION_DATABASE_V6.get("安全", {}))
                
                prompt_sys = SPECIALIST_PROMPT_TEMPLATE_V6.format(
                    role=role, role_desc=kb.get('role_desc', ''),
                    critical_hazards='\n'.join(f'- {h}' for h in kb.get('critical_hazards', [])),
                    checklist='\n'.join(kb.get('checklist', [])),
                    must_report_if='\n'.join(f'- {item}' for item in kb.get('must_report_if', [])),
                    norms=kb.get('norms', ''), anti_hallucination=kb.get('anti_hallucination', '')
                )
                
                resp = client.chat.completions.create(
                    model=model, temperature=0.3, max_tokens=4096,
                    messages=[{"role":"system","content":prompt_sys},
                              {"role":"user","content":[
                                  {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
                                  {"type":"text","text":"请分析图片，找出所有问题。输出 JSON 数组。"}]}])
                
                clean = resp.choices[0].message.content.replace("```json","").replace("```","").strip()
                s, e = clean.find('['), clean.rfind(']')+1
                if s != -1 and e:
                    try:
                        parsed = json.loads(clean[s:e])
                        for item in parsed:
                            if isinstance(item, dict):
                                item["category"] = role
                                all_issues.append(item)
                    except: pass

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
            
        render_home_list()
        if detail_view.visible and hasattr(detail_view, "current_task"):
            render_detail_data(detail_view.current_task)
        page.update()

    def start_analysis(e):
        config["last_prompt"] = prompt_dropdown.value
        ConfigManager.save(config)
        
        api_key = config.get("api_key", "")
        p_name = config.get("current_provider")
        p_conf = PROVIDER_PRESETS.get(p_name, {})
        base_url = p_conf.get("base_url", "")
        model = p_conf.get("model", "")
        if p_name == "自定义":
            c = config.get("custom_provider_settings", {})
            base_url, model = c.get("base_url",""), c.get("model","")
            
        if not api_key:
            show_toast("请先在⚙设置中配置 API Key", False)
            open_settings()
            return
            
        waiting = [t for t in tasks if t['status'] in ('waiting','error')]
        if not waiting:
            show_toast("没有待分析的图片", False)
            return

        progress_bar.visible = True
        status_text.value = f"正在分析 {len(waiting)} 张..."
        prompt_text = config.get("prompts", DEFAULT_PROMPTS).get(prompt_dropdown.value, "")
        page.update()
        
        for t in waiting:
            t['status'] = 'analyzing'
            threading.Thread(target=worker_thread, args=(t, api_key, base_url, model, prompt_text)).start()
            
        render_home_list()

    # ---------------- 选取文件 ----------------
    def on_files_selected(e: ft.FilePickerResultEvent):
        if e.files:
            current = len(tasks)
            allowed = MAX_IMAGES - current
            if allowed <= 0:
                show_toast(f"最多支持 {MAX_IMAGES} 张图片", False)
                return
            added = 0
            for f in e.files[:allowed]:
                if any(t['path'] == f.path for t in tasks): continue
                tasks.append({"id": str(time.time()) + "_" + f.name, "path": f.path, "name": f.name, "status": "waiting", "data": None})
                added += 1
            if added:
                count_text.value = f"{len(tasks)}/20"
                show_toast(f"已添加 {added} 张图片")
                render_home_list()
        page.navigation_bar.selected_index = current_tab
        page.update()

    file_picker = ft.FilePicker(on_result=on_files_selected)
    page.overlay.append(file_picker)

    # ---------------- UI 渲染: 卡片生成 ----------------
    def build_risk_card(item, index, on_edit, on_delete, on_copy, on_detail):
        level = item.get("risk_level", "一般质量缺陷")
        st = RISK_STYLE.get(level, RISK_STYLE["一般质量缺陷"])
        
        issue_text = item.get("issue","")
        if len(issue_text) > 60: issue_text = issue_text[:60] + "..."
        
        has_reg = bool(item.get("regulation",""))
        has_cor = bool(item.get("correction",""))
        
        icons_row = []
        if has_reg: icons_row.append(ft.Text("📋", size=14))
        if has_cor: icons_row.append(ft.Text("✅", size=14))
        
        return ft.Container(
            bgcolor=st['bg'], border=ft.border.all(1.5, st['border']), border_radius=14, padding=12,
            on_click=lambda e: on_detail(item),
            content=ft.Column([
                ft.Row([
                    ft.Container(content=ft.Text(str(index), color="white", size=11, weight=ft.FontWeight.BOLD),
                                 bgcolor=st["border"], width=24, height=24, alignment=ft.alignment.center, border_radius=12),
                    ft.Container(content=ft.Text(f"{st['icon']} {level}", color="white", size=12, weight=ft.FontWeight.BOLD),
                                 bgcolor=st["badge_bg"], padding=ft.padding.symmetric(horizontal=8, vertical=4), border_radius=7),
                    ft.Container(content=ft.Text(item.get("category",""), color=DS["text_secondary"], size=11),
                                 bgcolor=DS["surface"], border=ft.border.all(1, DS["border"]), padding=ft.padding.symmetric(horizontal=8, vertical=4), border_radius=7, visible=bool(item.get("category"))),
                    ft.Container(expand=True),
                    ft.TextButton("编辑", on_click=lambda e: on_edit(item), style=ft.ButtonStyle(color=DS["info"], bgcolor=DS["info_light"], padding=2, shape=ft.RoundedRectangleBorder(radius=6))),
                    ft.TextButton("复制", on_click=lambda e: on_copy(item), style=ft.ButtonStyle(color=DS["primary"], bgcolor=DS["primary_light"], padding=2, shape=ft.RoundedRectangleBorder(radius=6))),
                    ft.TextButton("删除", on_click=lambda e: on_delete(item), style=ft.ButtonStyle(color=DS["danger"], bgcolor=DS["danger_light"], padding=2, shape=ft.RoundedRectangleBorder(radius=6))),
                ]),
                ft.Text(issue_text, size=14, color=DS["text_primary"], weight=ft.FontWeight.W_500),
                ft.Text("💬 点击卡片查看详情", size=11, color=DS["text_hint"], italic=True),
                ft.Divider(color=DS["border"], height=1),
                ft.Row([
                    ft.Row(icons_row, spacing=10),
                    ft.Container(expand=True),
                    ft.Text(f"置信度 {int(item.get('confidence',0)*100)}%", size=11, color=DS["text_hint"], visible=bool(item.get('confidence')))
                ])
            ], spacing=8)
        )

    # ---------------- UI 渲染: 各种 Dialog ----------------
    def show_edit_dialog(item, on_save_callback):
        cbo_level = ft.Dropdown(options=[ft.dropdown.Option("严重安全隐患"), ft.dropdown.Option("一般安全隐患"), ft.dropdown.Option("严重质量缺陷"), ft.dropdown.Option("一般质量缺陷")], value=item.get("risk_level", "一般质量缺陷"), text_size=14)
        edt_issue = ft.TextField(value=item.get("issue",""), multiline=True, min_lines=3, text_size=14)
        edt_reg = ft.TextField(value=item.get("regulation",""), multiline=True, min_lines=2, text_size=14)
        edt_cor = ft.TextField(value=item.get("correction",""), multiline=True, min_lines=2, text_size=14)
        edt_conf = ft.TextField(value=str(int(item.get("confidence", 0.9)*100)), text_size=14)
        
        dialog = ft.AlertDialog(title=ft.Text("✏️ 编辑问题"))
        def save(e):
            item["risk_level"] = cbo_level.value
            item["issue"] = edt_issue.value
            item["regulation"] = edt_reg.value
            item["correction"] = edt_cor.value
            try: item["confidence"] = max(0.0, min(1.0, float(edt_conf.value)/100.0))
            except: item["confidence"] = 0.9
            page.close(dialog)
            on_save_callback()
            show_toast("✓ 已保存修改")

        dialog.content = ft.Column([
            ft.Text("风险等级", weight=ft.FontWeight.BOLD), cbo_level,
            ft.Text("问题描述", weight=ft.FontWeight.BOLD), edt_issue,
            ft.Text("规范依据", weight=ft.FontWeight.BOLD), edt_reg,
            ft.Text("整改措施", weight=ft.FontWeight.BOLD), edt_cor,
            ft.Text("置信度(%)", weight=ft.FontWeight.BOLD), edt_conf,
        ], scroll=ft.ScrollMode.AUTO, tight=True)
        dialog.actions = [
            ft.TextButton("取消", on_click=lambda e: page.close(dialog)),
            ft.ElevatedButton("保存", on_click=save, bgcolor=DS["primary"], color="white")
        ]
        page.open(dialog)

    def show_detail_dialog(item):
        level = item.get("risk_level", "一般质量缺陷")
        st = RISK_STYLE.get(level, RISK_STYLE["一般质量缺陷"])
        dialog = ft.AlertDialog(title=ft.Text("📋 问题详情"))
        dialog.content = ft.Column([
            ft.Container(content=ft.Text(f"{st['icon']} {level}", color=st["border"], weight=ft.FontWeight.BOLD), bgcolor=st["badge_bg"], padding=8, border_radius=8),
            ft.Text(f"🏷️ 专业：{item.get('category','')}", color=DS["text_secondary"], weight=ft.FontWeight.BOLD, visible=bool(item.get('category'))),
            ft.Divider(),
            ft.Text("📝 问题描述", weight=ft.FontWeight.BOLD), ft.Text(item.get("issue",""), size=14),
            ft.Text("📋 规范依据", weight=ft.FontWeight.BOLD, visible=bool(item.get("regulation"))), ft.Text(item.get("regulation",""), size=13, color=DS["text_secondary"], visible=bool(item.get("regulation"))),
            ft.Text("✅ 整改措施", color=DS["success"], weight=ft.FontWeight.BOLD, visible=bool(item.get("correction"))), ft.Text(item.get("correction",""), size=13, visible=bool(item.get("correction"))),
            ft.Text(f"🎯 置信度 {int(item.get('confidence',0)*100)}%", weight=ft.FontWeight.BOLD, color=DS["primary"], visible=bool(item.get("confidence")))
        ], scroll=ft.ScrollMode.AUTO, tight=True)
        dialog.actions = [ft.ElevatedButton("关闭", on_click=lambda e: page.close(dialog), bgcolor=DS["primary"], color="white")]
        page.open(dialog)

    def show_delete_confirm(item, on_confirm_callback):
        dialog = ft.AlertDialog(title=ft.Text("确认删除"))
        def confirm(e):
            page.close(dialog)
            on_confirm_callback()
            show_toast("✓ 已删除")
        dialog.content = ft.Text(f"确定要删除这个问题吗？\n\n{item.get('issue', '')[:50]}...")
        dialog.actions = [
            ft.TextButton("取消", on_click=lambda e: page.close(dialog)),
            ft.ElevatedButton("确定", on_click=confirm, bgcolor=DS["danger"], color="white")
        ]
        page.open(dialog)

    def open_settings():
        key_input = ft.TextField(value=config.get("api_key",""), password=True, can_reveal_password=True, bgcolor=DS["bg"], text_size=14)
        provider_drop = ft.Dropdown(options=[ft.dropdown.Option(k) for k in PROVIDER_PRESETS.keys()], value=config.get("current_provider"), bgcolor=DS["bg"], text_size=14)
        url_input = ft.TextField(label="Base URL", value=config.get("custom_provider_settings",{}).get("base_url",""), bgcolor=DS["surface2"], text_size=14)
        model_input = ft.TextField(label="模型名称", value=config.get("custom_provider_settings",{}).get("model",""), bgcolor=DS["surface2"], text_size=14)
        
        custom_frame = ft.Column([url_input, model_input], visible=(provider_drop.value == "自定义"))
        def on_prov_change(e):
            custom_frame.visible = (provider_drop.value == "自定义")
            page.update()
        provider_drop.on_change = on_prov_change
        
        dialog = ft.AlertDialog(title=ft.Text("⚙ 设置"))
        def save(e):
            config["api_key"] = key_input.value
            config["current_provider"] = provider_drop.value
            config["custom_provider_settings"] = {"base_url": url_input.value, "model": model_input.value}
            ConfigManager.save(config)
            page.close(dialog)
            page.navigation_bar.selected_index = current_tab
            show_toast("设置已保存 ✓")

        def cancel(e):
            page.close(dialog)
            page.navigation_bar.selected_index = current_tab
            page.update()

        dialog.content = ft.Column([
            ft.Text("🔑 API KEY", size=12, weight=ft.FontWeight.BOLD, color=DS["text_hint"]), key_input,
            ft.Text("🤖 模型厂商", size=12, weight=ft.FontWeight.BOLD, color=DS["text_hint"]), provider_drop,
            custom_frame
        ], tight=True, scroll=ft.ScrollMode.AUTO)
        dialog.actions = [ft.TextButton("取消", on_click=cancel), ft.ElevatedButton("保存", on_click=save, bgcolor=DS["primary"], color="white")]
        page.open(dialog)

    # ---------------- 页面渲染逻辑 ----------------
    def render_home_list():
        home_list.controls.clear()
        if not tasks:
            home_list.controls.append(empty_state)
        else:
            for t in tasks:
                icon, color, text = "⏳", DS["text_hint"], "等待中"
                if t['status'] == 'analyzing': icon, color, text = "🔄", DS["primary"], t.get('progress_msg', '分析中')
                elif t['status'] == 'done': icon, color, text = "✅", DS["success"], f"发现 {len(t['data'])} 个问题" if t['data'] else "未发现问题"
                elif t['status'] == 'error': icon, color, text = "❌", DS["danger"], t.get('error', '失败')[:20]

                def make_click(t=t):
                    return lambda e: open_detail_view(t)

                # 🚨 核心修复：加载本地图片使用 src_base64 渲染，不再崩溃
                home_list.controls.append(
                    ft.Container(
                        bgcolor=DS["surface"], border_radius=12, border=ft.border.all(1, DS["border"]),
                        padding=10, on_click=make_click(),
                        content=ft.Row([
                            ft.Image(src_base64=get_b64(t['path']), width=50, height=50, fit=ft.ImageFit.COVER, border_radius=8),
                            ft.Column([
                                ft.Text(t['name'], size=14, weight=ft.FontWeight.W_600, color=DS["text_primary"]),
                                ft.Text(text, size=12, color=color)
                            ], expand=True, spacing=2),
                            ft.Text(icon, size=20),
                            ft.Text("›", size=20, color=DS["text_hint"])
                        ])
                    )
                )
        page.update()

    def render_summary():
        summary_list.controls.clear()
        all_issues = []
        for t in tasks:
            if t['status'] == 'done' and t.get('data'):
                for issue in t['data']:
                    issue['_src'] = t['name']
                    all_issues.append(issue)
                    
        if not all_issues:
            summary_list.controls.append(
                ft.Container(
                    bgcolor=DS["surface"], border_radius=14, border=ft.border.all(1, DS["border"]), padding=30,
                    content=ft.Column([
                        ft.Text("📊", size=52),
                        ft.Text("暂无分析结果", size=17, weight=ft.FontWeight.BOLD, color=DS["text_primary"]),
                        ft.Text("请先主页添加并分析图片", size=13, color=DS["text_secondary"])
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                )
            )
        else:
            counts = {}
            for issue in all_issues: counts[issue.get("risk_level","")] = counts.get(issue.get("risk_level",""),0)+1
            stat_row = ft.Row(wrap=True, spacing=8)
            for lvl in ["严重安全隐患","一般安全隐患","严重质量缺陷","一般质量缺陷"]:
                if counts.get(lvl,0):
                    st = RISK_STYLE[lvl]
                    stat_row.controls.append(
                        ft.Container(content=ft.Text(f"{st['icon']} {lvl[:4]} {counts[lvl]}个", size=12, color=st['border'], weight=ft.FontWeight.BOLD),
                                     bgcolor=st['bg'], border=ft.border.all(1, st['border']), border_radius=8, padding=ft.padding.symmetric(horizontal=10, vertical=5))
                    )
                    
            summary_list.controls.append(
                ft.Container(bgcolor=DS["surface"], border_radius=12, border=ft.border.all(1, DS["border"]), padding=14,
                             content=ft.Column([ft.Text(f"共发现 {len(all_issues)} 个问题", size=16, weight=ft.FontWeight.BOLD, color=DS["text_primary"]), stat_row]))
            )
            
            sorted_issues = sorted(all_issues, key=lambda x: RISK_STYLE.get(x.get("risk_level",""), RISK_STYLE["一般质量缺陷"])["priority"])
            for i, issue in enumerate(sorted_issues, 1):
                summary_list.controls.append(ft.Text(f"  📷 {issue.get('_src','')}", size=11, color=DS["text_hint"]))
                
                def make_callbacks(issue=issue):
                    def edit(item):
                        show_edit_dialog(item, lambda: render_summary())
                    def delete(item):
                        def on_del():
                            for tk in tasks:
                                if tk.get('data'):
                                    tk['data'] = [it for it in tk['data'] if it is not item]
                            render_summary()
                        show_delete_confirm(item, on_del)
                    def copy(item):
                        text = f"【{item.get('risk_level','')}】\n{item.get('issue','')}\n\n📋 规范依据：{item.get('regulation','')}\n✅ 整改措施：{item.get('correction','')}\n🎯 置信度：{int(item.get('confidence',0)*100)}%"
                        copy_to_clipboard(text)
                    def detail(item):
                        show_detail_dialog(item)
                    return edit, delete, copy, detail
                    
                e_cb, d_cb, c_cb, det_cb = make_callbacks()
                summary_list.controls.append(build_risk_card(issue, i, e_cb, d_cb, c_cb, det_cb))

    def render_detail_data(task):
        detail_list.controls.clear()
        
        if task['status'] == 'waiting':
            detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, border=ft.border.all(1, DS["border"]), padding=30, content=ft.Column([ft.Text("⏳", size=48), ft.Text("等待分析", size=17, weight=ft.FontWeight.BOLD, color=DS["text_hint"]), ft.Text("点击主页「▶ 开始分析」", size=13, color=DS["text_secondary"])], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)))
        elif task['status'] == 'analyzing':
            detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, border=ft.border.all(1, DS["border"]), padding=30, content=ft.Column([ft.Text("🔄", size=48), ft.Text("正在分析...", size=17, weight=ft.FontWeight.BOLD, color=DS["primary"]), ft.Text(task.get('progress_msg',''), size=13, color=DS["text_secondary"])], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)))
        elif task['status'] == 'error':
            detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, border=ft.border.all(1, DS["border"]), padding=30, content=ft.Column([ft.Text("❌", size=48), ft.Text("分析失败", size=17, weight=ft.FontWeight.BOLD, color=DS["danger"]), ft.Text(task.get('error','未知错误'), size=13, color=DS["text_secondary"])], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)))
        elif task['status'] == 'done':
            data = task.get('data') or []
            if not data:
                detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=14, border=ft.border.all(1, DS["border"]), padding=30, content=ft.Column([ft.Text("✅", size=48), ft.Text("未发现问题", size=17, weight=ft.FontWeight.BOLD, color=DS["success"]), ft.Text("该图片未检测到明显安全质量隐患", size=13, color=DS["text_secondary"])], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)))
            else:
                counts = {}
                for item in data: counts[item.get("risk_level","")] = counts.get(item.get("risk_level",""),0)+1
                stat_row = ft.Row(spacing=8, wrap=True)
                for lvl, cnt in counts.items():
                    st = RISK_STYLE.get(lvl, RISK_STYLE["一般质量缺陷"])
                    stat_row.controls.append(ft.Container(content=ft.Text(f"{st['icon']} {cnt}", color=st['border'], size=13, weight=ft.FontWeight.BOLD), bgcolor=st['bg'], border=ft.border.all(1, st['border']), padding=ft.padding.symmetric(horizontal=9, vertical=3), border_radius=7))
                
                detail_list.controls.append(ft.Container(bgcolor=DS["surface"], border_radius=12, border=ft.border.all(1, DS["border"]), padding=14, content=ft.Row([ft.Text(f"共 {len(data)} 个问题", size=15, weight=ft.FontWeight.BOLD, color=DS["text_primary"]), ft.Container(expand=True), stat_row])))
                
                sorted_data = sorted(data, key=lambda x: RISK_STYLE.get(x.get("risk_level",""), RISK_STYLE["一般质量缺陷"])["priority"])
                for i, item in enumerate(sorted_data, 1):
                    def make_detail_callbacks(item=item):
                        def edit(it):
                            show_edit_dialog(it, lambda: render_detail_data(task) or page.update())
                        def delete(it):
                            def on_del():
                                task['data'] = [i for i in task['data'] if i is not it]
                                render_detail_data(task)
                                page.update()
                            show_delete_confirm(it, on_del)
                        def copy(it):
                            text = f"【{it.get('risk_level','')}】\n{it.get('issue','')}\n\n📋 规范依据：{it.get('regulation','')}\n✅ 整改措施：{it.get('correction','')}\n🎯 置信度：{int(it.get('confidence',0)*100)}%"
                            copy_to_clipboard(text)
                        def detail(it):
                            show_detail_dialog(it)
                        return edit, delete, copy, detail
                        
                    e_cb, d_cb, c_cb, det_cb = make_detail_callbacks()
                    detail_list.controls.append(build_risk_card(item, i, e_cb, d_cb, c_cb, det_cb))

    def copy_all_issues():
        all_issues = []
        for t in tasks:
            if t['status'] == 'done' and t.get('data'):
                for issue in t['data']:
                    issue['_src'] = t['name']
                    all_issues.append(issue)
        if not all_issues:
            show_toast("暂无可复制的问题", False); return
        priority = {"严重安全隐患":0,"一般安全隐患":1,"严重质量缺陷":2,"一般质量缺陷":3}
        sorted_issues = sorted(all_issues, key=lambda x: priority.get(x.get('risk_level',''),4))
        lines = [
            "🏗️ 质量安全检查问题清单",
            f"检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"分析图片：{len([t for t in tasks if t['status']=='done'])} 张",
            f"发现问题：{len(all_issues)} 个",
            "="*40, ""
        ]
        for i, issue in enumerate(sorted_issues, 1):
            lines += [f"{i}. 【{issue.get('risk_level','')}】",
                      f"   来源：{issue.get('_src','')}",
                      f"   {issue.get('issue','')}",
                      f"   📋 依据：{issue.get('regulation','')}",
                      f"   ✅ 整改：{issue.get('correction','')}", ""]
        copy_to_clipboard("\n".join(lines))

    def clear_queue():
        if not tasks: return
        dialog = ft.AlertDialog(title=ft.Text("确认清空"), content=ft.Text("确定要清空所有图片吗？"))
        def confirm_clear(e):
            tasks.clear()
            count_text.value = "0/20"
            status_text.value = "就绪"
            render_home_list()
            page.close(dialog)
            show_toast("队列已清空")
        dialog.actions = [ft.TextButton("取消", on_click=lambda e: page.close(dialog)), ft.ElevatedButton("确定", on_click=confirm_clear, bgcolor=DS["danger"], color="white")]
        page.open(dialog)

    # === 单页容器架构 (SPA Views) ===
    home_view = ft.Column([
        ft.Container(bgcolor=DS["primary"], height=56, padding=ft.padding.symmetric(horizontal=16), content=ft.Row([ft.Text("🏗️ 普洱版纳安全质检助手", color="white", size=17, weight=ft.FontWeight.BOLD, expand=True), count_text])),
        ft.Container(bgcolor=DS["surface"], padding=10, border=ft.border.only(bottom=ft.BorderSide(1, DS["border"])), content=ft.Row([ft.Text("检查场景", size=13, color=DS["text_secondary"]), prompt_dropdown])),
        ft.Container(content=home_list, expand=True),
        progress_bar,
        ft.Container(bgcolor=DS["surface"], height=68, padding=10, border=ft.border.only(top=ft.BorderSide(1, DS["border"])), content=ft.Row([
            ft.ElevatedButton("🗑 清空", on_click=lambda e: clear_queue(), bgcolor=DS["surface2"], color=DS["text_secondary"]),
            ft.ElevatedButton("📋 复制全部", on_click=lambda e: copy_all_issues(), bgcolor=DS["success_light"], color=DS["success"]),
            ft.ElevatedButton("▶ 开始分析", on_click=start_analysis, bgcolor=DS["primary"], color="white", expand=True)
        ])),
        ft.Container(content=status_text, padding=ft.padding.only(left=14, bottom=4))
    ], expand=True, spacing=0)
    
    summary_view = ft.Column([
        ft.Container(bgcolor=DS["primary"], height=56, padding=16, content=ft.Text("📊 问题汇总", color="white", size=17, weight=ft.FontWeight.BOLD)),
        ft.Container(content=summary_list, expand=True),
        ft.Container(bgcolor=DS["surface"], height=68, padding=10, border=ft.border.only(top=ft.BorderSide(1, DS["border"])), content=ft.Row([
            ft.ElevatedButton("📋 复制全部问题", on_click=lambda e: copy_all_issues(), bgcolor=DS["primary"], color="white", expand=True)
        ]))
    ], expand=True, spacing=0, visible=False)
    
    detail_view = ft.Column([
        ft.Container(bgcolor=DS["primary"], height=56, padding=ft.padding.symmetric(horizontal=10), content=ft.Row([
            ft.IconButton(ft.icons.ARROW_BACK_IOS_NEW, icon_color="white", on_click=lambda e: close_detail_view()),
            detail_title_text
        ])),
        detail_image,
        ft.Container(content=detail_list, expand=True)
    ], expand=True, spacing=0, visible=False)
    
    main_container = ft.Container(content=ft.Stack([home_view, summary_view, detail_view], expand=True), expand=True)

    # ---------------- 页面导航控制 ----------------
    def on_nav_change(e):
        nonlocal current_tab
        idx = e.control.selected_index
        if idx == 0:
            current_tab = 0
            home_view.visible = True
            summary_view.visible = False
            detail_view.visible = False
            page.update()
        elif idx == 1:
            current_tab = 1
            render_summary()
            home_view.visible = False
            summary_view.visible = True
            detail_view.visible = False
            page.update()
        elif idx == 2:
            file_picker.pick_files(allow_multiple=True, file_type=ft.FilePickerFileType.IMAGE)
        elif idx == 3:
            open_settings()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0, bgcolor=DS["surface"],
        destinations=[
            ft.NavigationDestination(icon=ft.icons.HOME, label="主页"),
            ft.NavigationDestination(icon=ft.icons.BAR_CHART, label="汇总"),
            ft.NavigationDestination(icon=ft.icons.ADD_PHOTO_ALTERNATE, label="添加"),
            ft.NavigationDestination(icon=ft.icons.SETTINGS, label="设置"),
        ], on_change=on_nav_change
    )

    def open_detail_view(task):
        detail_view.current_task = task
        detail_title_text.value = f"  {task['name']}"
        detail_image.src_base64 = get_b64(task['path']) # 🚨 核心修复：加载详情页图片使用 Base64
        detail_image.visible = True
        render_detail_data(task)
        home_view.visible = False
        summary_view.visible = False
        detail_view.visible = True
        page.update()
        
    def close_detail_view():
        detail_view.visible = False
        if current_tab == 0: home_view.visible = True
        elif current_tab == 1: summary_view.visible = True
        page.update()

    # 将容器加入根页面
    page.add(main_container)
    render_home_list()

if __name__ == "__main__":
    ft.app(target=main)
