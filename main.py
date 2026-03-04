#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建设工程质量安全检查助手 - 手机版 V4.6
基于 v4.6 版提示词系统
修复：
1. 移除所有 QPropertyAnimation pos 动画（主要卡死原因）
2. Toast 改用 QTimer 简单显隐
3. 设置改回 QDialog（稳定）
4. 移除 resizeEvent 中的动态布局
5. FAB 改为固定布局内按钮
6. 使用 V4.6 版提示词系统（更专业的规范依据和检查清单）
7. 添加日志窗口显示分析状态
"""

import sys, os, json, base64, time, re
from datetime import datetime
from typing import Dict, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QColor, QFont, QPalette
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QFrame, QFileDialog,
    QProgressBar, QMessageBox, QDialog, QLineEdit, QComboBox,
    QSizePolicy, QStackedWidget, QGraphicsDropShadowEffect,
    QDialogButtonBox, QCheckBox, QPlainTextEdit, QTextEdit
)
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
  }},
  {{
    "risk_level": "一般安全隐患",
    "issue": "【电气】配电箱门未跨接软铜线",
    "regulation": "GB 50303-2015《建筑电气工程施工质量验收规范》第 12.1.1 条",
    "correction": "在配电箱门与箱体间跨接截面积不小于 4mm²的铜芯软线",
    "bbox": [200, 100, 350, 280],
    "confidence": 0.95
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
        "critical_hazards": [
            "压力管道使用非压力管道管材（如用排水管代替给水管）",
            "阀门无标识或标识错误（介质流向、压力等级）",
            "法兰垫片使用错误（石棉垫片用于高温高压）",
            "管道支吊架间距过大导致管道下垂",
            "补偿器未做预拉伸或限位措施",
        ],
        "norms": """
### GB 50242-2002《建筑给水排水及采暖工程施工质量验收规范》
**第 3.3.13 条** 法兰连接螺栓紧固后露出螺母 2-3 扣，垫片不突入管内，法兰平行度偏差不大于法兰外径的 1.5‰。
**第 3.3.15 条** 阀门安装前必须做强度和严密性试验，安装方向正确（止回阀低进高出），手轮便于操作。
**第 4.1.2 条** 给水管道必须采用与管材相适应的管件，生活给水系统管材必须符合饮用水卫生标准。
### TSG D0001-2009《压力管道安全技术监察规程》
**第 110 条** 压力管道元件必须具有特种设备制造许可证，安装前进行外观检查和几何尺寸检查。
""",
        "checklist": [
            "【一眼识别】管道颜色标识：红色 - 消防、绿色 - 给水、蓝色 - 排水、黄色 - 燃气，颜色错误立即报告",
            "【一眼识别】法兰螺栓露牙：必须露出 2-3 扣，少于 2 扣未紧固，多于 3 扣螺栓过长",
            "【一眼识别】阀门手轮方向：向上或向外为正确，向下为错误（无法操作）",
            "【一眼识别】软接头状态：自然状态为正常，拉伸或压缩超过 15% 立即报告",
            "【工艺检查】法兰平行度：用钢尺测量两侧间距，差值大于 2mm 报告",
            "【工艺检查】支吊架间距：DN50 不超 5m，DN100 不超 6m，过大导致下垂",
            "【工艺检查】焊缝外观：无裂纹、未熔合、夹渣、气孔，咬边深度不超 0.5mm",
            "【材料检查】管材标识：查看喷码，压力管道必须有 GB/T 编号和钢号",
        ],
        "must_report_if": [
            "发现管道有凹陷、裂纹、严重腐蚀",
            "发现法兰垫片外露不均匀或偏置",
            "发现阀门铭牌缺失或模糊不清",
            "发现管道支吊架锈蚀严重或脱落",
            "发现不同材质管道直接焊接无过渡件",
        ],
        "anti_hallucination": "临时封堵盲板不是缺阀门；试压用临时支撑不是支架不足；保温层保护板接缝不是裂缝。"
    },
    "电气": {
        "role_desc": "注册电气工程师 | 30 年变配电及施工现场经验",
        "critical_hazards": [
            "临时用电未采用 TN-S 接零保护系统",
            "配电箱未做重复接地或接地电阻大于 10Ω",
            "一闸多机（一个开关控制多台设备）",
            "电缆直接拖地或浸水",
            "带电体裸露无防护罩",
            "使用铜丝、铁丝代替熔断器熔体",
        ],
        "norms": """
### GB 50303-2015《建筑电气工程施工质量验收规范》
**第 12.1.1 条** 金属桥架及其支架全长应不少于 2 处与接地干线相连，非镀锌桥架连接板两端跨接铜芯接地线截面积不小于 4mm²。
**第 14.1.1 条** 箱 (盘) 内 PE 线应通过汇流排连接，严禁串联连接，PE 线截面积符合设计要求。
**第 5.1.1 条** 三相或单相交流单芯电缆不得单独穿于钢导管内，必须同穿于一管防止涡流发热。
### JGJ 46-2005《施工现场临时用电安全技术规范》
**第 8.1.3 条** 每台用电设备必须有各自专用的开关箱，严禁用同一个开关箱直接控制 2 台及以上用电设备。
**第 5.1.1 条** 临时用电工程必须采用 TN-S 接零保护系统，实行三级配电两级保护。
""",
        "checklist": [
            "【一眼识别】电线颜色：黄绿双色只能是 PE 线，用作他途立即报告",
            "【一眼识别】配电箱门：必须有跨接软铜线，缺失立即报告",
            "【一眼识别】插座接线：左零右火上接地，接反立即报告",
            "【一眼识别】电缆敷设：直接拖地、过路无保护管立即报告",
            "【工艺检查】桥架跨接：每 30-50m 一处接地点，连接板处必须有跨接线",
            "【工艺检查】箱内接线：一机一闸一漏一箱，多机共用开关立即报告",
            "【工艺检查】漏电保护：测试漏保按钮，不动作立即报告",
            "【工艺检查】电缆弯曲半径：不小于电缆外径 10 倍，过小损伤绝缘",
            "【设备检查】配电箱标识：必须有一机一闸标识、责任人、联系电话",
        ],
        "must_report_if": [
            "发现电线绝缘层破损、老化开裂",
            "发现开关箱内积尘、积水或有异物",
            "发现漏电保护器失效或拆除",
            "发现电缆接头裸露无绝缘包扎",
            "发现配电箱未上锁或箱门缺失",
        ],
        "anti_hallucination": "施工中临时接线待整理；旧规范 PE 线可能不是黄绿双色 (2000 年前)；备用回路不是故障。"
    },
    "结构": {
        "role_desc": "结构总工程师 | 30 年混凝土及钢结构经验",
        "critical_hazards": [
            "模板支撑体系立杆悬空或垫板缺失",
            "高大模板未设置扫地杆、剪刀撑",
            "钢筋主筋位置错误（梁底筋放成面筋）",
            "混凝土浇筑后出现贯穿裂缝",
            "钢结构高强螺栓未终拧或梅花头未拧掉",
            "后浇带未按方案留设或提前拆除支撑",
        ],
        "norms": """
### GB 50204-2015《混凝土结构工程施工质量验收规范》
**第 5.5.1 条** 钢筋保护层厚度：梁类构件 +10mm/-7mm，板类构件 +8mm/-5mm，合格率 90% 以上。
**第 8.3.2 条** 施工缝留设位置：柱基础顶面、梁底面、板底面，继续浇筑前凿毛清理。
### JGJ 162-2008《建筑施工模板安全技术规范》
**第 6.1.2 条** 模板支架立杆底部必须设置垫板，严禁悬空，垫板厚度不小于 50mm。
**第 6.2.4 条** 满堂模板支架四边与中间每隔四排立杆设置一道纵向剪刀撑，由底至顶连续设置。
""",
        "checklist": [
            "【一眼识别】立杆底部：悬空、无垫板、垫板破裂立即报告",
            "【一眼识别】钢筋间距：用肉眼观察，明显不均匀或露筋立即报告",
            "【一眼识别】混凝土裂缝：宽度超 0.3mm 或贯穿性裂缝立即报告",
            "【一眼识别】模板变形：鼓胀、扭曲、下沉立即报告",
            "【工艺检查】钢筋绑扎：梁柱节点核心区箍筋不得遗漏",
            "【工艺检查】保护层垫块：每平方米不少于 1 块，梅花形布置",
            "【工艺检查】模板垂直度：层高 5m 内偏差小于 6mm",
            "【工艺检查】钢结构焊缝：焊脚尺寸符合设计，无咬边、未焊透",
            "【材料检查】钢筋锈蚀：表面锈皮脱落、出现麻坑不得使用",
        ],
        "must_report_if": [
            "发现模板支撑立杆间距大于方案要求",
            "发现梁底模板下挠或支撑松动",
            "发现钢筋规格型号与设计不符",
            "发现混凝土蜂窝、孔洞、夹渣",
            "发现钢结构涂装漏涂、返锈",
        ],
        "anti_hallucination": "未抹面不是不平整；待绑扎区域钢筋散乱正常；温度裂缝 (发丝状) 不是结构裂缝。"
    },
    "机械": {
        "role_desc": "起重机械专家 | 30 年塔吊施工升降机安拆经验",
        "critical_hazards": [
            "【致命】使用非吊装机械进行吊装作业（如用挖掘机、装载机吊物）",
            "【致命】塔吊力矩限制器、起重量限制器失效或被短接",
            "【致命】施工升降机防坠安全器过期或失效",
            "【致命】吊篮安全锁失效或配重不足",
            "钢丝绳一个节距内断丝超过 10% 继续使用",
            "起重机械未经检测验收或检测不合格继续使用",
            "特种作业人员无证操作",
        ],
        "norms": """
### GB 5144-2006《塔式起重机安全规程》
**第 6.1.1 条** 塔吊必须装设力矩限制器、起重量限制器、高度限位器、幅度限位器、回转限位器，灵敏可靠。
**第 7.2.1 条** 钢丝绳报废标准：一个节距内断丝数超过总丝数 10%，有断股、死弯、压扁、绳芯挤出。
**第 10.3 条** 塔吊基础不得积水，基础周围不得挖掘，地脚螺栓紧固并有防松措施。
### GB 10055-2007《施工升降机安全规程》
**第 11.1.9 条** 防坠安全器必须在有效标定期内使用，有效期为 1 年。
### JGJ 33-2012《建筑机械使用安全技术规程》
**第 4.1.14 条** 严禁使用挖掘机、装载机、推土机等非起重机械进行吊装作业。
""",
        "checklist": [
            "【一眼识别】吊装设备：挖掘机、装载机吊物立即报告 (致命违章)",
            "【一眼识别】限位器：查看是否有线头短接、拆除，失效立即报告",
            "【一眼识别】钢丝绳：断丝、断股、死弯、压扁立即报告",
            "【一眼识别】吊钩：防脱钩装置缺失或损坏立即报告",
            "【一眼识别】配重：吊篮配重块不足或固定失效立即报告",
            "【工艺检查】标准节螺栓：用扳手检查，松动立即报告",
            "【工艺检查】附墙装置：间距符合说明书，不得焊接在脚手架上",
            "【工艺检查】基础排水：塔吊基础积水立即报告",
            "【资料检查】验收标牌：查看设备验收合格证、检测标志",
            "【人员检查】操作证：无证操作立即报告",
        ],
        "must_report_if": [
            "发现起重机械超负荷使用",
            "发现多塔作业无防碰撞措施",
            "发现塔吊回转范围内有高压线无防护",
            "发现施工升降机门联锁失效",
            "发现机械设备带病运转",
        ],
        "anti_hallucination": "停工状态吊钩无荷载正常；设备表面轻微锈迹不是缺陷；临时停放不是故障。"
    },
    "基坑": {
        "role_desc": "岩土工程师 | 30 年深基坑支护及降水经验",
        "critical_hazards": [
            "基坑开挖超过 5m 无专项方案或未按方案支护",
            "基坑边堆载超过设计荷载（堆土、堆料、机械）",
            "支护结构出现裂缝、位移、渗漏",
            "基坑降水导致周边建筑物沉降开裂",
            "上下基坑无专用通道或通道设置不合理",
            "基坑监测数据超预警值未停工",
        ],
        "norms": """
### JGJ 120-2012《建筑基坑支护技术规程》
**第 8.1.1 条** 基坑周边 1m 范围内不得堆载，3m 范围内堆载不得超过设计荷载限值。
**第 8.1.4 条** 基坑开挖过程中必须采取降排水措施，坑底不得长期浸泡。
**第 9.1.2 条** 基坑监测项目包括：支护结构位移、周边建筑物沉降、地下水位、支撑轴力。
### JGJ 59-2011《建筑施工安全检查标准》
**第 3.11.3 条** 基坑开挖深度超过 2m 必须设置 1.2m 高防护栏杆，挂密目安全网。
""",
        "checklist": [
            "【一眼识别】坑边堆载：坑边 1m 内有堆土、堆料立即报告",
            "【一眼识别】临边防护：无 1.2m 护栏或护栏损坏立即报告",
            "【一眼识别】支护裂缝：喷锚面裂缝宽度超 5mm 立即报告",
            "【一眼识别】坑底积水：大面积积水或管涌立即报告",
            "【工艺检查】放坡坡度：土质松软地区放坡不足立即报告",
            "【工艺检查】锚杆间距：符合方案要求，偏差大于 100mm 报告",
            "【工艺检查】排水沟：基坑顶截水沟、底排水沟是否畅通",
            "【工艺检查】上下通道：专用梯道宽度不小于 1m，两侧扶手",
            "【监测检查】位移观测点：是否破坏，数据是否超预警",
        ],
        "must_report_if": [
            "发现支护结构有明显位移或变形",
            "发现基坑周边地面开裂",
            "发现锚杆、土钉拔出力不足",
            "发现降水井出水量突然减少或浑浊",
            "发现基坑监测数据连续超预警值",
        ],
        "anti_hallucination": "雨后坑边少量积水及时抽排正常；支护表面轻微渗水不是渗漏；临时堆土待运不是违规。"
    },
    "消防": {
        "role_desc": "注册消防工程师 | 30 年施工现场消防管理经验",
        "critical_hazards": [
            "氧气瓶与乙炔瓶混放或间距不足 5m",
            "气瓶距离明火作业点不足 10m",
            "气瓶无防震圈、防倾倒措施",
            "动火作业无监护人、无灭火器材",
            "消防通道堵塞、消防水源不足",
            "易燃材料堆放区无消防器材",
            "工人宿舍使用大功率电器或私拉乱接",
        ],
        "norms": """
### GB 50720-2011《建设工程施工现场消防安全技术规范》
**第 5.3.7 条** 氧气瓶与乙炔瓶工作间距不小于 5m，与明火作业点距离不小于 10m，气瓶不得暴晒、不得靠近热源。
**第 6.3.1 条** 施工现场动火作业必须办理动火许可证，设专人监护，配备灭火器材。
**第 4.2.1 条** 施工现场应设置临时消防车道，宽度不小于 4m，不得占用消防车道堆放材料。
**第 5.4.3 条** 易燃易爆危险品库房与在建工程防火间距不小于 15m。
""",
        "checklist": [
            "【一眼识别】气瓶间距：氧气乙炔瓶距离小于 5m 立即报告",
            "【一眼识别】气瓶状态：横放、暴晒、无防震圈立即报告",
            "【一眼识别】动火监护：无监护人、无灭火器立即报告",
            "【一眼识别】消防通道：被材料堵塞立即报告",
            "【工艺检查】灭火器配置：每 50㎡不少于 2 具，压力指针在绿区",
            "【工艺检查】临时消防水：是否有水，水压是否足够",
            "【工艺检查】易燃物堆放：保温材料、油漆单独存放",
            "【工艺检查】宿舍消防：不得使用大功率电器、不得私拉电线",
            "【资料检查】动火证：查看是否办理、是否在有效期内",
        ],
        "must_report_if": [
            "发现乙炔瓶卧放使用",
            "发现气瓶软管破损、接头漏气",
            "发现灭火器过期或压力不足",
            "发现电焊作业无接火盆、防火毯",
            "发现消防栓无水或配件缺失",
        ],
        "anti_hallucination": "空瓶待运可横放；少量油漆当天用完可暂存；食堂用火有专人管理不是违规。"
    },
    "安全": {
        "role_desc": "注册安全工程师 | 30 年施工现场安全管理经验",
        "critical_hazards": [
            "【致命】使用非吊装机械进行吊装作业（挖掘机、装载机、汽车吊等违章吊装）",
            "高处作业 (2m 以上) 不系安全带或低挂高用",
            "安全帽未系下颌带或佩戴不合格安全帽",
            "临边洞口防护缺失或防护不牢固",
            "脚手架未满铺脚手板或探头板",
            "安全网破损、老化、未系挂",
            "交叉作业无隔离措施",
            "恶劣天气 (6 级风、暴雨) 继续高处作业",
            "起重机械作业区域无警戒、无人监护",
        ],
        "norms": """
### JGJ 59-2011《建筑施工安全检查标准》
**第 3.2.5 条** 进入施工现场必须正确佩戴安全帽，系好下颌带，安全帽必须有合格证。
**第 5.1.1 条** 高处作业 (2m 及以上) 必须系安全带，安全带必须高挂低用，挂点牢固可靠。
**第 3.13.3 条** 楼梯口、电梯井口、通道口、预留洞口必须设置防护栏杆或盖板。
### JGJ 130-2011《建筑施工扣件式钢管脚手架安全技术规范》
**第 6.2.2 条** 脚手架作业层必须满铺脚手板，不得有探头板，外侧设置 180mm 高挡脚板。
""",
        "checklist": [
            "【一眼识别】安全帽：未系下颌带立即报告，帽壳裂纹立即更换",
            "【一眼识别】安全带：2m 以上无安全带或低挂高用立即报告",
            "【一眼识别】临边防护：无 1.2m 护栏立即报告",
            "【一眼识别】洞口防护：无盖板或盖板不固定立即报告",
            "【一眼识别】脚手板：未满铺、有探头板立即报告",
            "【工艺检查】安全网：破损、老化、未系满立即报告",
            "【工艺检查】防护栏杆：上杆 1.2m、下杆 0.6m、挡脚板 180mm",
            "【工艺检查】电梯井防护：每层 (不大于 10m) 一道水平网",
            "【工艺检查】通道防护：安全通道顶部双层防护，间距 600mm",
        ],
        "must_report_if": [
            "发现安全带挂在不牢固构件上",
            "发现安全防护设施被拆除或挪作他用",
            "发现工人酒后上岗",
            "发现特种作业无证操作",
            "发现安全警示标志缺失",
        ],
        "anti_hallucination": "管理人员在安全通道内检查可短时摘帽；地面作业不强制系安全带；休息区可不戴安全帽。"
    },
    "暖通": {
        "role_desc": "暖通工程师 | 30 年通风空调及采暖经验",
        "critical_hazards": [
            "风管穿越防火分区未设防火阀",
            "排烟管道未做独立支吊架",
            "空调冷热水管道保温层破损结露",
            "风机盘管冷凝水管倒坡",
            "设备基础未做减振或减振器失效",
        ],
        "norms": """
### GB 50243-2016《通风与空调工程施工质量验收规范》
**第 4.2.1 条** 风管法兰垫片厚度 3-5mm，不得凸入管内，垫片接头不得少于 2 处。
**第 6.2.3 条** 防火阀距墙表面距离不大于 200mm，必须设独立支吊架。
**第 8.2.4 条** 冷冻水管道保温层厚度符合设计，不得有冷桥现象。
""",
        "checklist": [
            "【一眼识别】风管支吊架：间距过大 (边长≤400mm 不超 4m) 立即报告",
            "【一眼识别】保温层：破损、脱落、结露立即报告",
            "【一眼识别】防火阀：位置错误、无法操作立即报告",
            "【工艺检查】法兰垫片：不得有直缝对接，垫片不得双拼",
            "【工艺检查】管道坡度：冷凝水管坡度不小于 0.01",
            "【工艺检查】软连接：长度 150-300mm，不得扭曲",
            "【工艺检查】设备找平：水平度偏差小于 1/1000",
        ],
        "must_report_if": [
            "发现风管漏光、漏风",
            "发现阀门安装方向错误",
            "发现管道穿墙无套管",
            "发现设备运行异常噪音",
        ],
        "anti_hallucination": "测试用临时管线；调试阶段部分阀门未开启正常。"
    },
    "给排水": {
        "role_desc": "给排水工程师 | 30 年市政及建筑给排水经验",
        "critical_hazards": [
            "排水管道倒坡或坡度不足",
            "压力管道未做强度试验",
            "排水管道未做闭水试验",
            "消防管道阀门常闭未锁定",
            "给水管道与生活水源混接",
        ],
        "norms": """
### GB 50268-2008《给水排水管道工程施工及验收规范》
**第 5.3.1 条** 管道基础砂垫层厚度不小于 100mm，管道不得直接放在原状土上。
**第 9.1.1 条** 压力管道必须进行水压试验，试验压力为工作压力的 1.5 倍。
**第 9.4.1 条** 无压管道必须进行闭水试验，试验水头为上游管道内顶以上 2m。
""",
        "checklist": [
            "【一眼识别】管道坡度：排水管道倒坡立即报告",
            "【一眼识别】管道支墩：大口径管道无支墩立即报告",
            "【一眼识别】检查井：井盖破损、井内淤堵立即报告",
            "【工艺检查】管道接口：橡胶圈安装到位，无扭曲",
            "【工艺检查】地漏水封：水封深度不小于 50mm",
            "【工艺检查】管道冲洗：出水清澈无杂质",
        ],
        "must_report_if": [
            "发现管道渗漏",
            "发现阀门启闭不灵活",
            "发现管道标识缺失",
            "发现检查井内有害气体",
        ],
        "anti_hallucination": "临时排水管；施工阶段未通水正常。"
    },
    "防水": {
        "role_desc": "防水工程师 | 30 年屋面及地下防水经验",
        "critical_hazards": [
            "地下室底板防水层破损渗漏",
            "屋面卷材搭接宽度不足",
            "卫生间防水层未上翻或高度不足",
            "穿墙管防水处理不当渗漏",
            "防水保护层未及时施工导致防水层破坏",
        ],
        "norms": """
### GB 50207-2012《屋面工程质量验收规范》
**第 4.3.1 条** 卷材搭接宽度：高聚物改性沥青防水卷材短边搭接 150mm，长边搭接 100mm。
**第 5.1.3 条** 屋面女儿墙、山墙、泛水处卷材必须满粘，收头用金属压条固定。
### GB 50108-2008《地下工程防水技术规范》
**第 4.1.7 条** 防水混凝土抗渗等级不得小于 P6，施工缝必须设置止水钢板或遇水膨胀止水条。
""",
        "checklist": [
            "【一眼识别】卷材搭接：用尺量，不足 100mm 立即报告",
            "【一眼识别】屋面积水：雨后积水或排水不畅立即报告",
            "【一眼识别】渗漏痕迹：墙面水渍、发霉立即报告",
            "【工艺检查】阴阳角：必须做圆弧处理 (R=50mm)",
            "【工艺检查】附加层：管根、地漏周围 500mm 范围附加层",
            "【工艺检查】涂膜厚度：用针刺法，平均厚度符合设计",
        ],
        "must_report_if": [
            "发现防水层起鼓、开裂",
            "发现防水层裸露未保护",
            "发现变形缝漏水",
            "发现后浇带渗漏",
        ],
        "anti_hallucination": "防水层未做保护层前不能上人；施工缝处轻微潮湿不是渗漏。"
    },
    "环保": {
        "role_desc": "环境工程师 | 30 年施工现场环保管理经验",
        "critical_hazards": [
            "裸土未覆盖或覆盖不完整",
            "施工现场未设置围挡或围挡破损",
            "噪声超标 (昼间 70dB，夜间 55dB)",
            "污水直排或未经沉淀排放",
            "建筑垃圾未及时清运",
            "焚烧建筑垃圾或废弃物",
        ],
        "norms": """
### GB 12523-2011《建筑施工场界环境噪声排放标准》
**第 4.1 条** 噪声限值：昼间 70dB(A)，夜间 55dB(A)，夜间指 22:00 至次日 6:00。
### GB 50720-2011《建设工程施工现场环境与卫生标准》
**第 4.2.1 条** 施工现场主要道路必须进行硬化处理，裸露场地和集中堆放的土方应采取覆盖、固化或绿化措施。
**第 4.3.1 条** 施工现场应设置排水沟及沉淀池，污水经沉淀达标后方可排放。
""",
        "checklist": [
            "【一眼识别】裸土覆盖：绿色密目网覆盖，破损立即更换",
            "【一眼识别】围挡：高度 2.5m(市区) 或 1.8m(郊区)，破损立即修复",
            "【一眼识别】道路硬化：主要道路必须硬化，无泥泞",
            "【一眼识别】沉淀池：三级沉淀，定期清淤",
            "【工艺检查】喷淋系统：塔吊喷淋、围挡喷淋正常运行",
            "【工艺检查】噪声监测：设置噪声监测仪，数据公示",
            "【工艺检查】车辆冲洗：出入口设置洗车槽，不带泥上路",
        ],
        "must_report_if": [
            "发现扬尘污染严重",
            "发现污水直排市政管网",
            "发现夜间超时施工扰民",
            "发现垃圾焚烧",
        ],
        "anti_hallucination": "短时扬尘配合雾炮使用；雾天不是扬尘；少量生活垃圾分类存放待运。"
    },
    "水利": {
        "role_desc": "水利水电工程总工 | 30 年大坝、堤防、渠道、水闸施工经验",
        "critical_hazards": [
            "【致命】围堰填筑未按方案分层碾压或防渗措施缺失",
            "【致命】高边坡 (超过 50m) 开挖无支护或未按方案支护",
            "【致命】隧洞开挖未执行短进尺、弱爆破、强支护原则",
            "【致命】混凝土面板堆石坝面板裂缝宽度超过 0.3mm 未处理",
            "【致命】帷幕灌浆压力超标导致地层抬动变形",
            "土石围堰防渗土工膜破损或未连续铺设",
            "大坝填筑料含水率超标或铺土过厚",
            "溢洪道、消力池等泄洪建筑物混凝土蜂窝、孔洞",
            "渠道衬砌混凝土板厚度不足或防冻层缺失",
            "水闸闸门启闭机未做荷载试验或制动失灵",
            "压力钢管焊缝无损检测不合格继续使用",
            "水下作业无专项方案或潜水员无证上岗",
        ],
        "norms": """
### SL 714-2015《水利水电工程施工安全管理导则》
**第 5.2.1 条** 施工单位必须对危险性较大的单项工程编制专项施工方案，超过一定规模的必须组织专家论证。
**第 6.1.3 条** 高边坡、深基坑、隧洞开挖、围堰施工等必须设置安全监测点，定期观测并记录。
**第 7.2.4 条** 爆破作业必须执行一炮三检制度，警戒距离符合设计要求。
### SL 310-2004《水利水电工程施工质量检验与评定规程》
**第 4.2.1 条** 原材料、中间产品必须按批次进行检验，检验合格后方可使用。
**第 5.3.2 条** 混凝土试块抗压强度必须符合设计要求，合格率 100%。
**第 6.1.1 条** 单元工程质量评定分为合格和优良两个等级，不合格必须返工处理。
### SL 260-2014《水利水电工程施工测量规范》
**第 3.2.1 条** 施工控制网必须与设计单位移交的控制点进行联测，精度符合设计要求。
**第 5.1.2 条** 大坝轴线、溢洪道中心线等 main 轴线放样误差不大于 10mm。
### SL 52-2015《水利水电工程施工安全防护设施技术规范》
**第 4.2.1 条** 临边作业必须设置 1.2m 高防护栏杆，挂密目式安全网。
**第 5.3.2 条** 隧洞施工必须设置通风、照明、排水系统，有毒有害气体浓度符合标准。
**第 6.1.1 条** 水上作业必须配备救生设备，作业人员穿救生衣。
### SL 631-2012《水利水电工程单元工程施工质量验收评定标准 - 土石方工程》
**第 4.2.3 条** 土方填筑必须分层碾压，每层厚度不大于 300mm，压实度符合设计要求。
### SL 632-2012《水利水电工程单元工程施工质量验收评定标准 - 混凝土工程》
**第 5.2.1 条** 钢筋安装位置偏差：受力钢筋间距±10mm，箍筋间距±20mm。
**第 6.1.2 条** 混凝土浇筑自由下落高度不大于 2m，超过 2m 必须设置串筒或溜槽。
""",
        "checklist": [
            "【一眼识别】围堰施工：堰体分层填筑、每层厚度不大于 300mm，一次性填筑过高立即报告",
            "【一眼识别】高边坡：开挖坡比符合设计，无倒悬、无松动岩块，锚杆、锚索外露长度符合要求",
            "【一眼识别】隧洞开挖：拱架间距符合设计，锁脚锚杆不得遗漏，初喷混凝土厚度不小于 50mm",
            "【一眼识别】大坝填筑：铺土均匀、无明显粗细颗粒集中，碾压痕迹清晰",
            "【一眼识别】混凝土面板：表面平整、无贯穿裂缝，接缝止水完好无破损",
            "【一眼识别】渠道衬砌：混凝土板厚度、平整度，伸缩缝填充饱满",
            "【一眼识别】压力钢管：焊缝外观、防腐层完整性，支座锚固可靠",
            "【一眼识别】闸门安装：门槽垂直度、止水橡皮压缩量符合设计",
            "【工艺检查】土石方填筑：每层厚度、碾压遍数、压实度检测报告",
            "【工艺检查】混凝土浇筑：配合比、坍落度、试块留置、养护记录",
            "【工艺检查】帷幕灌浆：灌浆压力、浆液配比、单位吸浆量记录",
            "【工艺检查】锚杆 (索)：钻孔深度、注浆饱满度、拉拔试验报告",
            "【工艺检查】土工膜铺设：搭接宽度不小于 100mm，焊缝严密",
            "【工艺检查】止水设施：止水带位置居中，接头热熔连接牢固",
            "【资料检查】特种作业证：爆破员、潜水员、起重工持证上岗",
            "【监测检查】变形观测点：大坝沉降、边坡位移、渗流压力监测数据",
        ],
        "must_report_if": [
            "发现围堰渗漏、管涌、裂缝等险情",
            "发现高边坡有掉块、裂缝、位移迹象",
            "发现隧洞初期支护开裂、变形",
            "发现大坝填筑料含水率过大或弹簧土",
            "发现混凝土结构有贯穿裂缝、蜂窝、孔洞",
            "发现压力钢管焊缝有裂纹、未焊透",
            "发现闸门启闭异常、制动失灵",
            "发现帷幕灌浆压力异常、地表抬动",
            "发现水下作业无防护措施",
            "发现监测数据超预警值未停工处理",
        ],
        "anti_hallucination": "施工缝凿毛处理正常；临时排水沟不是永久排水；养护期混凝土表面湿润不是渗漏；隧洞施工通风管临时断开不是无通风系统。"
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


# ==================== 分析线程 ====================
class AnalysisWorker(QThread):
    finished   = pyqtSignal(str, object)
    progress_msg = pyqtSignal(str, str)

    def __init__(self, task, config, prompt_text):
        super().__init__()
        self.task = task
        self.config = config
        self.prompt_text = prompt_text

    def run(self):
        try:
            p_name = self.config.get("current_provider")
            api_key = self.config.get("api_key", "")
            p_conf = PROVIDER_PRESETS.get(p_name, {})
            base_url = p_conf.get("base_url", "")
            model = p_conf.get("model", "")
            if p_name == "自定义":
                c = self.config.get("custom_provider_settings", {})
                base_url, model = c.get("base_url",""), c.get("model","")

            if not api_key:
                self.finished.emit(self.task['id'], {"error": "未配置 API Key，请在⚙设置中填写"}); return
            if not base_url or not model:
                self.finished.emit(self.task['id'], {"error": "未配置模型 URL 或名称"}); return

            client = OpenAI(api_key=api_key, base_url=base_url)
            with open(self.task['path'], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            self.progress_msg.emit(self.task['id'], "🔍 智能分诊中...")

            rr = client.chat.completions.create(
                model=model, temperature=0.1,
                messages=[{"role":"system","content":ROUTER_SYSTEM_PROMPT},
                          {"role":"user","content":[
                              {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
                              {"type":"text","text":"请分析施工内容并选派专家"}]}])
            roles = self._parse_roles(rr.choices[0].message.content)
            if not roles: roles = ["安全"]
            if "安全" not in roles: roles.append("安全")

            all_issues = []
            for idx, role in enumerate(roles):
                self.progress_msg.emit(self.task['id'], f"🔬 {role}专家分析 ({idx+1}/{len(roles)})")
                kb = REGULATION_DATABASE_V6.get(role, {})
                resp = client.chat.completions.create(
                    model=model, temperature=0.3, max_tokens=4096,
                    messages=[{"role":"system","content":self._build_prompt_v6(role,kb)},
                              {"role":"user","content":[
                                  {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
                                  {"type":"text","text":"请分析图片，找出所有问题。输出 JSON 数组。"}]}])
                issues = self._parse_issues(resp.choices[0].message.content, role)
                all_issues.extend(issues)

            self.finished.emit(self.task['id'], all_issues)
        except Exception as e:
            self.finished.emit(self.task['id'], {"error": str(e)})

    def _parse_roles(self, text):
        try:
            m = re.search(r'\[.*?\]', text, re.DOTALL)
            if m: return json.loads(m.group())
        except: pass
        return []

    def _build_prompt_v6(self, role, kb):
        """使用 V4.6 版提示词模板"""
        return SPECIALIST_PROMPT_TEMPLATE_V6.format(
            role=role,
            role_desc=kb.get('role_desc', ''),
            critical_hazards='\n'.join(f'- {h}' for h in kb.get('critical_hazards', [])),
            checklist='\n'.join(kb.get('checklist', [])),
            must_report_if='\n'.join(f'- {item}' for item in kb.get('must_report_if', [])),
            norms=kb.get('norms', ''),
            anti_hallucination=kb.get('anti_hallucination', '')
        )

    def _parse_issues(self, text, role):
        issues = []
        try:
            clean = text.replace("```json","").replace("```","").strip()
            s, e = clean.find('['), clean.rfind(']')+1
            if s!=-1 and e:
                for item in json.loads(clean[s:e]):
                    if isinstance(item, dict):
                        item["category"] = role
                        issues.append(item)
        except: pass
        return issues


# ==================== UI 组件 ====================
def shadow(widget, blur=10, y=2, alpha=25):
    eff = QGraphicsDropShadowEffect()
    eff.setBlurRadius(blur)
    eff.setOffset(0, y)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)


class RiskCard(QFrame):
    copy_requested = pyqtSignal(dict)
    edit_requested = pyqtSignal(dict)
    delete_requested = pyqtSignal(dict)
    card_clicked = pyqtSignal(dict)  # 新增：卡片点击信号

    def __init__(self, item, index=0):
        super().__init__()
        self.item = item
        level = item.get("risk_level", "一般质量缺陷")
        st = RISK_STYLE.get(level, RISK_STYLE["一般质量缺陷"])

        self.setStyleSheet(f"""
            RiskCard {{
                background: {st['bg']};
                border: 1.5px solid {st['border']};
                border-radius: 14px;
            }}
            RiskCard:hover {{
                border: 2px solid {st['border']};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)  # 鼠标悬停显示手型

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        # 头行
        hrow = QHBoxLayout(); hrow.setSpacing(8)

        num = QLabel(str(index))
        num.setFixedSize(24, 24)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet(f"background:{st['border']};color:white;border-radius:12px;font-size:11px;font-weight:700;")
        hrow.addWidget(num)

        badge = QLabel(f"{st['icon']} {level}")
        badge.setStyleSheet(f"background:{st['badge_bg']};color:white;padding:3px 9px;border-radius:7px;font-size:12px;font-weight:700;")
        hrow.addWidget(badge)

        cat = item.get("category","")
        if cat:
            cl = QLabel(cat)
            cl.setStyleSheet(f"background:{DS['surface']};color:{DS['text_secondary']};padding:3px 9px;border-radius:7px;font-size:11px;border:1px solid {DS['border']};")
            hrow.addWidget(cl)

        hrow.addStretch()

        # 操作按钮组 - 缩小按钮尺寸适应手机屏幕
        btn_edit = QPushButton("编辑")
        btn_edit.setFixedSize(48, 30)
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setStyleSheet(f"background:{DS['info_light']};color:{DS['info']};border:none;border-radius:6px;font-size:12px;font-weight:600;")
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(item))
        hrow.addWidget(btn_edit)

        btn_copy = QPushButton("复制")
        btn_copy.setFixedSize(48, 30)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet(f"background:{DS['primary_light']};color:{DS['primary']};border:none;border-radius:6px;font-size:12px;font-weight:600;")
        btn_copy.clicked.connect(lambda: self.copy_requested.emit(item))
        hrow.addWidget(btn_copy)

        btn_del = QPushButton("删除")
        btn_del.setFixedSize(48, 30)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet(f"background:{DS['danger_light']};color:{DS['danger']};border:none;border-radius:6px;font-size:12px;font-weight:600;")
        btn_del.clicked.connect(lambda: self.delete_requested.emit(item))
        hrow.addWidget(btn_del)

        lay.addLayout(hrow)

        # 问题描述 - 缩短显示，点击看详情
        issue_text = item.get("issue","")
        if len(issue_text) > 60:
            issue_text = issue_text[:60] + "..."
        lbl = QLabel(issue_text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"font-size:14px;color:{DS['text_primary']};font-weight:500;")
        lay.addWidget(lbl)

        # 提示文字
        hint = QLabel("💬 点击卡片查看详情")
        hint.setStyleSheet(f"font-size:11px;color:{DS['text_hint']};font-style:italic;")
        lay.addWidget(hint)

        # 分割线
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color:{DS['border']};")
        lay.addWidget(line)

        # 依据 & 整改 - 只显示标题，内容点击查看详情
        has_regulation = bool(item.get("regulation",""))
        has_correction = bool(item.get("correction",""))
        if has_regulation or has_correction:
            info_row = QHBoxLayout(); info_row.setSpacing(10)
            if has_regulation:
                info_row.addWidget(QLabel("📋"))
            if has_correction:
                info_row.addWidget(QLabel("✅"))
            info_row.addStretch()
            lay.addLayout(info_row)

        conf = item.get("confidence", 0)
        if conf:
            cl2 = QLabel(f"置信度 {int(conf*100)}%")
            cl2.setStyleSheet(f"font-size:11px;color:{DS['text_hint']};")
            cl2.setAlignment(Qt.AlignmentFlag.AlignRight)
            lay.addWidget(cl2)

    def mousePressEvent(self, event):
        """处理鼠标点击事件"""
        super().mousePressEvent(event)
        # 如果不是点击在按钮上，发送卡片点击信号
        self.card_clicked.emit(self.item)


class TaskRow(QWidget):
    clicked = pyqtSignal(dict)
    STATUS = {
        "waiting":   ("⏳", DS["text_hint"],     "等待中"),
        "analyzing": ("🔄", DS["primary"],        "分析中"),
        "done":      ("✅", DS["success"],         "完成"),
        "error":     ("❌", DS["danger"],          "失败"),
    }

    def __init__(self, task):
        super().__init__()
        self.task = task
        self.setFixedHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)

        # 缩略图
        self.thumb = QLabel()
        self.thumb.setFixedSize(50, 50)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setStyleSheet(f"background:{DS['bg']};border-radius:8px;border:1px solid {DS['border']};")
        try:
            pix = QPixmap(task['path'])
            if not pix.isNull():
                sc = pix.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
                x = (sc.width()-50)//2; y = (sc.height()-50)//2
                self.thumb.setPixmap(sc.copy(x, y, 50, 50))
        except: self.thumb.setText("📷")
        lay.addWidget(self.thumb)

        # 文字
        info = QVBoxLayout(); info.setSpacing(3)
        self.lbl_name = QLabel(task['name'])
        self.lbl_name.setStyleSheet(f"font-size:14px;font-weight:600;color:{DS['text_primary']};")
        info.addWidget(self.lbl_name)
        self.lbl_status = QLabel("等待中")
        self.lbl_status.setStyleSheet(f"font-size:12px;color:{DS['text_secondary']};")
        info.addWidget(self.lbl_status)
        lay.addLayout(info, 1)

        # 图标
        self.dot = QLabel("⏳")
        self.dot.setStyleSheet("font-size:20px;")
        self.dot.setFixedWidth(28)
        self.dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.dot)

        # 箭头
        arr = QLabel("›")
        arr.setStyleSheet(f"font-size:20px;color:{DS['text_hint']};")
        lay.addWidget(arr)

    def mousePressEvent(self, e):
        self.clicked.emit(self.task)

    def update_status(self, status, detail=""):
        icon, color, text = self.STATUS.get(status, ("⏳", DS["text_hint"], status))
        self.dot.setText(icon)
        self.lbl_status.setText(detail if detail else text)
        self.lbl_status.setStyleSheet(f"font-size:12px;color:{color};")


# ==================== 编辑对话框 ====================
class EditIssueDialog(QDialog):
    def __init__(self, parent, item):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("✏️ 编辑问题")
        self.setMinimumWidth(360)
        self.setModal(True)
        
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)
        
        def label(text):
            l = QLabel(text)
            l.setStyleSheet(f"font-size:13px;font-weight:600;color:{DS['text_primary']};")
            return l
        
        def textedit():
            t = QTextEdit()
            t.setMinimumHeight(80)
            t.setStyleSheet(f"""
                QTextEdit {{
                    background:{DS['bg']};border:1.5px solid {DS['border']};
                    border-radius:10px;padding:8px 12px;font-size:14px;
                }}
                QTextEdit:focus {{ border-color:{DS['primary']}; }}
            """)
            return t
        
        def combo():
            c = QComboBox()
            c.setMinimumHeight(42)
            c.setStyleSheet(f"""
                QComboBox {{
                    background:{DS['bg']};border:1.5px solid {DS['border']};
                    border-radius:10px;padding:8px 12px;font-size:14px;
                }}
            """)
            return c
        
        # 风险等级
        lay.addWidget(label("风险等级"))
        self.cbo_level = combo()
        self.cbo_level.addItems(["严重安全隐患", "一般安全隐患", "严重质量缺陷", "一般质量缺陷"])
        self.cbo_level.setCurrentText(item.get("risk_level", "一般质量缺陷"))
        lay.addWidget(self.cbo_level)
        
        # 问题描述
        lay.addWidget(label("问题描述"))
        self.edt_issue = textedit()
        self.edt_issue.setPlainText(item.get("issue", ""))
        lay.addWidget(self.edt_issue)
        
        # 规范依据
        lay.addWidget(label("规范依据"))
        self.edt_regulation = textedit()
        self.edt_regulation.setPlainText(item.get("regulation", ""))
        lay.addWidget(self.edt_regulation)
        
        # 整改措施
        lay.addWidget(label("整改措施"))
        self.edt_correction = textedit()
        self.edt_correction.setPlainText(item.get("correction", ""))
        lay.addWidget(self.edt_correction)
        
        # 置信度
        lay.addWidget(label("置信度"))
        self.edt_confidence = QLineEdit()
        self.edt_confidence.setMinimumHeight(42)
        conf_val = int(item.get("confidence", 0.9) * 100)
        self.edt_confidence.setText(f"{conf_val}")
        self.edt_confidence.setStyleSheet(f"""
            QLineEdit {{
                background:{DS['bg']};border:1.5px solid {DS['border']};
                border-radius:10px;padding:8px 12px;font-size:14px;
            }}
            QLineEdit:focus {{ border-color:{DS['primary']}; }}
        """)
        lay.addWidget(self.edt_confidence)
        
        # 按钮
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(80, 40)
        cancel_btn.setStyleSheet(f"background:{DS['surface2']};color:{DS['text_secondary']};border:1px solid {DS['border']};border-radius:8px;font-size:14px;")
        cancel_btn.clicked.connect(self.reject)
        btn_lay.addWidget(cancel_btn)
        
        ok_btn = QPushButton("保存")
        ok_btn.setFixedSize(80, 40)
        ok_btn.setStyleSheet(f"background:{DS['primary']};color:white;border:none;border-radius:8px;font-size:14px;font-weight:600;")
        ok_btn.clicked.connect(self.accept)
        btn_lay.addWidget(ok_btn)
        
        lay.addLayout(btn_lay)
    
    def get_updated_item(self):
        """获取更新后的问题项"""
        try:
            conf_text = self.edt_confidence.text().strip()
            conf_val = float(conf_text) / 100 if conf_text else 0.9
            conf_val = max(0.0, min(1.0, conf_val))
        except:
            conf_val = 0.9
        
        return {
            **self.item,
            "risk_level": self.cbo_level.currentText(),
            "issue": self.edt_issue.toPlainText().strip(),
            "regulation": self.edt_regulation.toPlainText().strip(),
            "correction": self.edt_correction.toPlainText().strip(),
            "confidence": conf_val
        }


# ==================== 问题详情弹窗 ====================
class IssueDetailDialog(QDialog):
    def __init__(self, parent, item):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("📋 问题详情")
        self.setMinimumWidth(360)
        self.setMinimumHeight(500)
        self.setModal(True)
        
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 16)
        
        # 标题区域
        title_frame = QFrame()
        title_frame.setStyleSheet(f"background:{DS['surface']};border-radius:12px;")
        title_lay = QVBoxLayout(title_frame)
        title_lay.setContentsMargins(14, 12, 14, 12)
        title_lay.setSpacing(8)
        
        # 风险等级标签
        level = item.get("risk_level", "一般质量缺陷")
        st = RISK_STYLE.get(level, RISK_STYLE["一般质量缺陷"])
        level_badge = QLabel(f"{st['icon']} {level}")
        level_badge.setStyleSheet(f"background:{st['badge_bg']};color:{st['border']};padding:6px 12px;border-radius:8px;font-size:14px;font-weight:700;")
        level_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lay.addWidget(level_badge)
        
        # 分类标签
        cat = item.get("category", "")
        if cat:
            cat_label = QLabel(f"🏷️ 专业：{cat}")
            cat_label.setStyleSheet(f"font-size:13px;color:{DS['text_secondary']};font-weight:600;")
            title_lay.addWidget(cat_label)
        
        lay.addWidget(title_frame)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        scroll_content = QWidget()
        scroll_content.setStyleSheet(f"background:{DS['bg']};")
        content_lay = QVBoxLayout(scroll_content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(10)
        
        # 问题描述
        desc_frame = QFrame()
        desc_frame.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
        desc_lay = QVBoxLayout(desc_frame)
        desc_lay.setContentsMargins(14, 12, 14, 12)
        desc_lay.setSpacing(8)
        
        desc_title = QLabel("📝 问题描述")
        desc_title.setStyleSheet(f"font-size:13px;font-weight:700;color:{DS['text_primary']};")
        desc_lay.addWidget(desc_title)
        
        desc_text = QLabel(item.get("issue", ""))
        desc_text.setWordWrap(True)
        desc_text.setStyleSheet(f"font-size:14px;color:{DS['text_primary']};line-height:1.6;")
        desc_lay.addWidget(desc_text)
        
        content_lay.addWidget(desc_frame)
        
        # 规范依据
        regulation = item.get("regulation", "")
        if regulation:
            reg_frame = QFrame()
            reg_frame.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
            reg_lay = QVBoxLayout(reg_frame)
            reg_lay.setContentsMargins(14, 12, 14, 12)
            reg_lay.setSpacing(8)
            
            reg_title = QLabel("📋 规范依据")
            reg_title.setStyleSheet(f"font-size:13px;font-weight:700;color:{DS['text_primary']};")
            reg_lay.addWidget(reg_title)
            
            reg_text = QLabel(regulation)
            reg_text.setWordWrap(True)
            reg_text.setStyleSheet(f"font-size:13px;color:{DS['text_secondary']};line-height:1.6;")
            reg_lay.addWidget(reg_text)
            
            content_lay.addWidget(reg_frame)
        
        # 整改措施
        correction = item.get("correction", "")
        if correction:
            corr_frame = QFrame()
            corr_frame.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
            corr_lay = QVBoxLayout(corr_frame)
            corr_lay.setContentsMargins(14, 12, 14, 12)
            corr_lay.setSpacing(8)
            
            corr_title = QLabel("✅ 整改措施")
            corr_title.setStyleSheet(f"font-size:13px;font-weight:700;color:{DS['success']};")
            corr_lay.addWidget(corr_title)
            
            corr_text = QLabel(correction)
            corr_text.setWordWrap(True)
            corr_text.setStyleSheet(f"font-size:13px;color:{DS['text_primary']};line-height:1.6;")
            corr_lay.addWidget(corr_text)
            
            content_lay.addWidget(corr_frame)
        
        # 置信度
        conf = item.get("confidence", 0)
        if conf:
            conf_frame = QFrame()
            conf_frame.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
            conf_lay = QHBoxLayout(conf_frame)
            conf_lay.setContentsMargins(14, 12, 14, 12)
            
            conf_label = QLabel("🎯 置信度")
            conf_label.setStyleSheet(f"font-size:13px;font-weight:600;color:{DS['text_secondary']};")
            conf_lay.addWidget(conf_label)
            
            conf_lay.addStretch()
            
            conf_value = QLabel(f"{int(conf*100)}%")
            conf_value.setStyleSheet(f"font-size:14px;font-weight:700;color:{DS['primary']};")
            conf_lay.addWidget(conf_value)
            
            content_lay.addWidget(conf_frame)
        
        content_lay.addStretch()
        scroll.setWidget(scroll_content)
        lay.addWidget(scroll, 1)
        
        # 底部按钮
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(100, 44)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"background:{DS['primary']};color:white;border:none;border-radius:10px;font-size:15px;font-weight:600;")
        close_btn.clicked.connect(self.accept)
        btn_lay.addWidget(close_btn)
        
        lay.addLayout(btn_lay)


# ==================== 设置对话框（稳定版） ====================
class SettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("⚙ 设置")
        self.setMinimumWidth(380)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 20, 20, 20)

        def section(t):
            l = QLabel(t)
            l.setStyleSheet(f"font-size:12px;font-weight:700;color:{DS['text_hint']};letter-spacing:1px;")
            return l

        def field():
            f = QLineEdit()
            f.setMinimumHeight(46)
            f.setStyleSheet(f"""
                QLineEdit {{
                    background:{DS['bg']};border:1.5px solid {DS['border']};
                    border-radius:10px;padding:8px 12px;font-size:14px;
                }}
                QLineEdit:focus {{ border-color:{DS['primary']}; }}
            """)
            return f

        def combo():
            c = QComboBox()
            c.setMinimumHeight(46)
            c.setStyleSheet(f"""
                QComboBox {{
                    background:{DS['bg']};border:1.5px solid {DS['border']};
                    border-radius:10px;padding:8px 12px;font-size:14px;
                }}
            """)
            return c

        # API Key
        lay.addWidget(section("🔑  API KEY"))
        self.fld_key = field()
        self.fld_key.setPlaceholderText("粘贴您的 API Key...")
        self.fld_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.fld_key.setText(config.get("api_key",""))
        lay.addWidget(self.fld_key)

        chk = QCheckBox("显示 Key")
        chk.setStyleSheet(f"font-size:13px;color:{DS['text_secondary']};")
        chk.toggled.connect(lambda c: self.fld_key.setEchoMode(
            QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        lay.addWidget(chk)

        # 模型
        lay.addWidget(section("🤖  模型厂商"))
        self.cbo = combo()
        self.cbo.addItems(list(PROVIDER_PRESETS.keys()))
        self.cbo.setCurrentText(config.get("current_provider","阿里百炼 (Qwen2.5-VL)"))
        lay.addWidget(self.cbo)

        # 自定义
        self.custom_frame = QFrame()
        self.custom_frame.setStyleSheet(f"background:{DS['surface2']};border-radius:10px;border:1px solid {DS['border']};")
        cf = QVBoxLayout(self.custom_frame)
        cf.setContentsMargins(12,10,12,10); cf.setSpacing(8)

        self.fld_url = field()
        self.fld_url.setPlaceholderText("Base URL")
        c2 = config.get("custom_provider_settings",{})
        self.fld_url.setText(c2.get("base_url",""))
        cf.addWidget(self.fld_url)

        self.fld_model = field()
        self.fld_model.setPlaceholderText("模型名称")
        self.fld_model.setText(c2.get("model",""))
        cf.addWidget(self.fld_model)

        lay.addWidget(self.custom_frame)
        self.custom_frame.setVisible(self.cbo.currentText() == "自定义")
        self.cbo.currentTextChanged.connect(lambda t: self.custom_frame.setVisible(t=="自定义"))

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_config(self):
        c = self.config.copy()
        c["api_key"] = self.fld_key.text().strip()
        c["current_provider"] = self.cbo.currentText()
        c["custom_provider_settings"] = {
            "base_url": self.fld_url.text().strip(),
            "model": self.fld_model.text().strip()
        }
        return c


# ==================== 详情页 ====================
class DetailPage(QWidget):
    back = pyqtSignal()
    copy_issue = pyqtSignal(dict)
    edit_issue = pyqtSignal(dict)
    delete_issue = pyqtSignal(dict)
    show_detail = pyqtSignal(dict)  # 新增：显示详情信号

    def __init__(self, task):
        super().__init__()
        self.task = task
        self.setStyleSheet(f"background:{DS['bg']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.setSpacing(0)

        # 顶栏
        top = QWidget(); top.setFixedHeight(56)
        top.setStyleSheet(f"background:{DS['primary']};")
        tl = QHBoxLayout(top); tl.setContentsMargins(10,0,16,0)

        btn_back = QPushButton("‹ 返回")
        btn_back.setFixedHeight(44)
        btn_back.setMinimumWidth(80)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet("background:rgba(255,255,255,0.2);color:white;border:none;border-radius:8px;font-size:15px;font-weight:600;padding:0 12px;")
        btn_back.clicked.connect(self.back)
        tl.addWidget(btn_back)

        name = QLabel(f"  {task['name']}")
        name.setStyleSheet("color:white;font-size:15px;font-weight:600;")
        tl.addWidget(name, 1)
        lay.addWidget(top)

        # 图片
        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setStyleSheet("background:#1F2937;")
        img_lbl.setFixedHeight(240)
        try:
            pix = QPixmap(task['path'])
            if not pix.isNull():
                img_lbl.setPixmap(pix.scaled(390, 240, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
        except: img_lbl.setText("📷 图片加载失败")
        lay.addWidget(img_lbl)

        # 结果滚动区
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        rw = QWidget(); rw.setStyleSheet(f"background:{DS['bg']};")
        self.rl = QVBoxLayout(rw)
        self.rl.setContentsMargins(12,12,12,12)
        self.rl.setSpacing(10)
        self._render()
        scroll.setWidget(rw)
        lay.addWidget(scroll)

    def _render(self):
        task = self.task
        if task['status'] == 'waiting':
            self._state("⏳","等待分析","点击主页「▶ 开始分析」", DS['text_hint'])
        elif task['status'] == 'analyzing':
            self._state("🔄","正在分析...", task.get('progress_msg',''), DS['primary'])
        elif task['status'] == 'done':
            data = task.get('data') or []
            if not data:
                self._state("✅","未发现问题","该图片未检测到明显安全质量隐患", DS['success'])
            else:
                # 汇总行
                summary = QFrame()
                summary.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
                sl = QHBoxLayout(summary); sl.setContentsMargins(14,10,14,10); sl.setSpacing(10)
                sl.addWidget(QLabel(f"共 {len(data)} 个问题").also(lambda l: l.setStyleSheet(f"font-size:15px;font-weight:700;color:{DS['text_primary']};")))
                sl.addStretch()
                counts = {}
                for item in data: counts[item.get("risk_level","")] = counts.get(item.get("risk_level",""),0)+1
                for lvl, cnt in counts.items():
                    st = RISK_STYLE.get(lvl, RISK_STYLE["一般质量缺陷"])
                    p = QLabel(f"{st['icon']} {cnt}")
                    p.setStyleSheet(f"background:{st['bg']};color:{st['border']};padding:3px 9px;border-radius:7px;font-size:13px;font-weight:700;border:1px solid {st['border']};")
                    sl.addWidget(p)
                self.rl.addWidget(summary)

                sorted_data = sorted(data, key=lambda x: RISK_STYLE.get(x.get("risk_level",""), RISK_STYLE["一般质量缺陷"])["priority"])
                for i, item in enumerate(sorted_data, 1):
                    card = RiskCard(item, i)
                    card.copy_requested.connect(self.copy_issue)
                    card.edit_requested.connect(self.edit_issue)
                    card.delete_requested.connect(self.delete_issue)
                    card.card_clicked.connect(self.show_detail)  # 连接点击信号
                    self.rl.addWidget(card)
        elif task['status'] == 'error':
            self._state("❌","分析失败", task.get('error','未知错误'), DS['danger'])
        self.rl.addStretch()

    def _state(self, icon, title, sub, color):
        w = QFrame()
        w.setStyleSheet(f"background:{DS['surface']};border-radius:14px;border:1px solid {DS['border']};")
        wl = QVBoxLayout(w); wl.setContentsMargins(20,30,20,30); wl.setSpacing(10)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for text, style in [
            (icon, "font-size:48px;"),
            (title, f"font-size:17px;font-weight:700;color:{color};"),
            (sub,   f"font-size:13px;color:{DS['text_secondary']};"),
        ]:
            l = QLabel(text); l.setStyleSheet(style)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter); l.setWordWrap(True)
            wl.addWidget(l)
        self.rl.addWidget(w)

    def refresh(self):
        while self.rl.count():
            w = self.rl.takeAt(0)
            if w.widget(): w.widget().deleteLater()
        self._render()


# QLabel.also helper
def _also(self, fn):
    fn(self); return self
QLabel.also = _also


# ==================== 主页 ====================
class HomePage(QWidget):
    open_detail  = pyqtSignal(dict)
    req_add      = pyqtSignal()
    req_analyze  = pyqtSignal()
    req_copy_all = pyqtSignal()
    req_clear    = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.task_rows: Dict[str, TaskRow] = {}
        self.setStyleSheet(f"background:{DS['bg']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0,0,0,0)
        lay.setSpacing(0)

        # 顶栏
        top = QWidget(); top.setFixedHeight(56)
        top.setStyleSheet(f"background:{DS['primary']};")
        tl = QHBoxLayout(top); tl.setContentsMargins(16,0,16,0)
        title = QLabel("🏗️ 普洱版纳区域安全质量检查助手")
        title.setStyleSheet("color:white;font-size:17px;font-weight:700;")
        tl.addWidget(title); tl.addStretch()

        self.lbl_count = QLabel("0/20")
        self.lbl_count.setStyleSheet("background:rgba(255,255,255,0.2);color:white;padding:4px 12px;border-radius:10px;font-size:13px;font-weight:600;")
        tl.addWidget(self.lbl_count)
        lay.addWidget(top)

        # 场景选择
        scene = QWidget(); scene.setFixedHeight(52)
        scene.setStyleSheet(f"background:{DS['surface']};border-bottom:1px solid {DS['border']};")
        sl = QHBoxLayout(scene); sl.setContentsMargins(14,0,14,0); sl.setSpacing(10)
        sl.addWidget(QLabel("检查场景").also(lambda l: l.setStyleSheet(f"font-size:13px;color:{DS['text_secondary']};font-weight:500;")))
        self.cbo_prompt = QComboBox()
        self.cbo_prompt.addItems(list(DEFAULT_PROMPTS.keys()))
        self.cbo_prompt.setMinimumHeight(38)
        self.cbo_prompt.setStyleSheet(f"""
            QComboBox {{
                background:{DS['bg']};border:1.5px solid {DS['border']};
                border-radius:9px;padding:6px 12px;font-size:13px;
                color:{DS['text_primary']};font-weight:500;
            }}
        """)
        sl.addWidget(self.cbo_prompt, 1)
        lay.addWidget(scene)

        # 空状态
        self.empty = QWidget()
        self.empty.setStyleSheet(f"background:{DS['bg']};")
        el = QVBoxLayout(self.empty); el.setAlignment(Qt.AlignmentFlag.AlignCenter); el.setSpacing(12)
        for text, style in [
            ("📷", "font-size:60px;"),
            ("添加施工图片", f"font-size:19px;font-weight:700;color:{DS['text_primary']};"),
            ("点击下方 ➕ 添加图片\n最多支持 20 张", f"font-size:14px;color:{DS['text_secondary']};"),
        ]:
            l = QLabel(text); l.setStyleSheet(style); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setWordWrap(True); el.addWidget(l)
        lay.addWidget(self.empty, 1)

        # 任务列表
        self.list_scroll = QScrollArea(); self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setStyleSheet("border:none;background:transparent;")
        self.list_scroll.hide()
        lc = QWidget(); lc.setStyleSheet(f"background:{DS['bg']};")
        self.list_lay = QVBoxLayout(lc)
        self.list_lay.setContentsMargins(12, 10, 12, 10)
        self.list_lay.setSpacing(8)
        self.list_lay.addStretch()
        self.list_scroll.setWidget(lc)
        lay.addWidget(self.list_scroll, 1)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(f"""
            QProgressBar {{ border:none;background:{DS['border']}; }}
            QProgressBar::chunk {{ background:{DS['primary']}; }}
        """)
        self.progress.hide()
        lay.addWidget(self.progress)

        # 操作栏（固定底部）
        bottom = QWidget(); bottom.setFixedHeight(68)
        bottom.setStyleSheet(f"background:{DS['surface']};border-top:1px solid {DS['border']};")
        bl = QHBoxLayout(bottom); bl.setContentsMargins(12,10,12,10); bl.setSpacing(10)

        btn_clear = QPushButton("🗑 清空")
        btn_clear.setFixedHeight(46)
        btn_clear.setMinimumWidth(80)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setStyleSheet(f"background:{DS['surface2']};color:{DS['text_secondary']};border:1.5px solid {DS['border']};border-radius:10px;font-size:14px;font-weight:600;")
        btn_clear.clicked.connect(self.req_clear)
        bl.addWidget(btn_clear)

        btn_copy = QPushButton("📋 复制全部")
        btn_copy.setFixedHeight(46)
        btn_copy.setMinimumWidth(110)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet(f"background:{DS['success_light']};color:{DS['success']};border:1.5px solid {DS['success']};border-radius:10px;font-size:14px;font-weight:600;")
        btn_copy.clicked.connect(self.req_copy_all)
        bl.addWidget(btn_copy)

        self.btn_analyze = QPushButton("▶ 开始分析")
        self.btn_analyze.setFixedHeight(46)
        self.btn_analyze.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_analyze.setStyleSheet(f"background:{DS['primary']};color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;")
        shadow(self.btn_analyze, blur=14, y=4, alpha=60)
        self.btn_analyze.clicked.connect(self.req_analyze)
        bl.addWidget(self.btn_analyze, 1)

        lay.addWidget(bottom)

        # 状态标签（叠在操作栏上方）
        self.status_lbl = QLabel("就绪")
        self.status_lbl.setStyleSheet(f"font-size:12px;color:{DS['text_secondary']};padding:3px 14px;")
        lay.insertWidget(lay.count()-1, self.status_lbl)

    def add_task(self, task):
        self.empty.hide(); self.list_scroll.show()
        row = TaskRow(task)
        row.clicked.connect(self.open_detail)
        card = QFrame()
        card.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
        shadow(card, blur=5, y=1, alpha=12)
        cl = QVBoxLayout(card); cl.setContentsMargins(0,0,0,0)
        cl.addWidget(row)
        self.list_lay.insertWidget(self.list_lay.count()-1, card)
        self.task_rows[task['id']] = row

    def update_task_status(self, task_id, status, detail=""):
        if task_id in self.task_rows:
            self.task_rows[task_id].update_status(status, detail)

    def update_count(self, n):
        self.lbl_count.setText(f"{n}/20")

    def set_status(self, text):
        self.status_lbl.setText(text)

    def set_progress(self, val, visible=True):
        self.progress.setVisible(visible)
        if visible: self.progress.setValue(val)

    def clear_all(self):
        while self.list_lay.count() > 1:
            w = self.list_lay.takeAt(0)
            if w.widget(): w.widget().deleteLater()
        self.task_rows.clear()
        self.empty.show(); self.list_scroll.hide()
        self.update_count(0); self.set_status("就绪")


# ==================== 汇总页 ====================
class SummaryPage(QWidget):
    copy_all = pyqtSignal()
    delete_issue = pyqtSignal(dict)
    show_detail = pyqtSignal(dict)  # 新增：显示详情信号

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background:{DS['bg']};")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        top = QWidget(); top.setFixedHeight(56)
        top.setStyleSheet(f"background:{DS['primary']};")
        tl = QHBoxLayout(top); tl.setContentsMargins(16,0,16,0)
        tl.addWidget(QLabel("📊 问题汇总").also(lambda l: l.setStyleSheet("color:white;font-size:17px;font-weight:700;")))
        lay.addWidget(top)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("border:none;")
        self.cw = QWidget(); self.cw.setStyleSheet(f"background:{DS['bg']};")
        self.cl = QVBoxLayout(self.cw); self.cl.setContentsMargins(12,12,12,80); self.cl.setSpacing(10)
        scroll.setWidget(self.cw)
        lay.addWidget(scroll, 1)

        bottom = QWidget(); bottom.setFixedHeight(68)
        bottom.setStyleSheet(f"background:{DS['surface']};border-top:1px solid {DS['border']};")
        bl = QHBoxLayout(bottom); bl.setContentsMargins(12,10,12,10)
        btn = QPushButton("📋  复制全部问题")
        btn.setFixedHeight(46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"background:{DS['primary']};color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;")
        btn.clicked.connect(self.copy_all)
        bl.addWidget(btn)
        lay.addWidget(bottom)

        self._show_empty()

    def _show_empty(self):
        while self.cl.count():
            w = self.cl.takeAt(0)
            if w.widget(): w.widget().deleteLater()
        w = QFrame()
        w.setStyleSheet(f"background:{DS['surface']};border-radius:14px;border:1px solid {DS['border']};")
        wl = QVBoxLayout(w); wl.setContentsMargins(30,40,30,40); wl.setSpacing(10); wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for text, style in [("📊","font-size:52px;"), ("暂无分析结果",f"font-size:17px;font-weight:700;color:{DS['text_primary']};"), ("请先主页添加并分析图片",f"font-size:13px;color:{DS['text_secondary']};")]:
            l = QLabel(text); l.setStyleSheet(style); l.setAlignment(Qt.AlignmentFlag.AlignCenter); wl.addWidget(l)
        self.cl.addWidget(w); self.cl.addStretch()

    def refresh(self, tasks):
        while self.cl.count():
            w = self.cl.takeAt(0)
            if w.widget(): w.widget().deleteLater()

        all_issues = []
        for t in tasks:
            if t['status']=='done' and t.get('data'):
                for issue in t['data']:
                    issue['_src'] = t['name']; all_issues.append(issue)

        if not all_issues: self._show_empty(); return

        # 统计卡
        stats = QFrame()
        stats.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
        sl = QVBoxLayout(stats); sl.setContentsMargins(14,12,14,12); sl.setSpacing(8)
        lbl = QLabel(f"共发现 {len(all_issues)} 个问题")
        lbl.setStyleSheet(f"font-size:16px;font-weight:700;color:{DS['text_primary']};")
        sl.addWidget(lbl)
        counts = {}
        for issue in all_issues: counts[issue.get("risk_level","")] = counts.get(issue.get("risk_level",""),0)+1
        pr = QHBoxLayout(); pr.setSpacing(8)
        for lvl in ["严重安全隐患","一般安全隐患","严重质量缺陷","一般质量缺陷"]:
            cnt = counts.get(lvl,0)
            if cnt:
                st = RISK_STYLE[lvl]
                p = QLabel(f"{st['icon']} {lvl[:4]}  {cnt}个")
                p.setStyleSheet(f"background:{st['bg']};color:{st['border']};padding:5px 10px;border-radius:8px;font-size:12px;font-weight:600;border:1px solid {st['border']};")
                pr.addWidget(p)
        pr.addStretch(); sl.addLayout(pr)
        self.cl.addWidget(stats)

        sorted_issues = sorted(all_issues, key=lambda x: RISK_STYLE.get(x.get("risk_level",""),RISK_STYLE["一般质量缺陷"])["priority"])
        for i, issue in enumerate(sorted_issues, 1):
            src = QLabel(f"  📷 {issue.get('_src','')}")
            src.setStyleSheet(f"font-size:11px;color:{DS['text_hint']};padding:2px 4px;")
            self.cl.addWidget(src)
            card = RiskCard(issue, i)
            card.delete_requested.connect(self.delete_issue)
            card.card_clicked.connect(self.show_detail)  # 连接点击信号
            self.cl.addWidget(card)

        self.cl.addStretch()


# ==================== 底部导航 ====================
class NavBar(QWidget):
    tab_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(68)
        self.current = 0
        self.setStyleSheet(f"background:{DS['surface']};border-top:1px solid {DS['border']};")
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,6); lay.setSpacing(0)
        self.btns = []
        for i, (icon, label) in enumerate([("🏠","主页"),("📊","汇总"),("➕","添加"),("⚙️","设置")]):
            btn = QPushButton(f"{icon}\n{label}")
            btn.setMinimumHeight(60)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self.tab_changed.emit(idx))
            lay.addWidget(btn)
            self.btns.append(btn)
        self._refresh(0)

    def _refresh(self, active):
        for i, btn in enumerate(self.btns):
            color = DS['nav_active'] if i==active else DS['nav_inactive']
            w = '700' if i==active else '500'
            btn.setStyleSheet(f"background:transparent;color:{color};border:none;font-size:11px;font-weight:{w};padding-top:6px;")

    def set_active(self, idx):
        self.current = idx
        self._refresh(idx)


# ==================== 主窗口 ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager.load()
        self.tasks: List[Dict] = []
        self.workers = []
        self.total_task = 0
        self.done_task = 0
        self._detail_page = None

        self.setWindowTitle("安全质检助手 V4.6")
        self.resize(390, 844)

        root = QWidget()
        self.setCentralWidget(root)
        rl = QVBoxLayout(root); rl.setContentsMargins(0,0,0,0); rl.setSpacing(0)

        self.stack = QStackedWidget()
        self.home = HomePage()
        self.home.open_detail.connect(self._open_detail)
        self.home.req_add.connect(self.add_files)
        self.home.req_analyze.connect(self.start_analysis)
        self.home.req_copy_all.connect(self.copy_all)
        self.home.req_clear.connect(self.clear_queue)
        self.home.cbo_prompt.currentTextChanged.connect(self._save_prompt)

        self.summary = SummaryPage()
        self.summary.copy_all.connect(self.copy_all)
        self.summary.delete_issue.connect(self._delete_from_summary)
        self.summary.show_detail.connect(self._show_issue_detail)  # 连接详情信号

        self.stack.addWidget(self.home)     # 0
        self.stack.addWidget(self.summary)  # 1

        rl.addWidget(self.stack, 1)

        self.nav = NavBar()
        self.nav.tab_changed.connect(self._on_nav)
        rl.addWidget(self.nav)

        last = self.config.get("last_prompt","V4.6 安全质量双聚焦")
        if last in DEFAULT_PROMPTS:
            self.home.cbo_prompt.setCurrentText(last)

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        try:
            # 停止所有工作线程
            for w in self.workers:
                if w.isRunning():
                    w.terminate()
                    w.wait(100)  # 等待 100ms
        except:
            pass  # 忽略关闭错误
        event.accept()

    def _on_nav(self, idx):
        if idx == 0:
            if self._detail_page:
                self._close_detail()
            else:
                self.stack.setCurrentIndex(0)
                self.nav.set_active(0)
        elif idx == 1:
            self.summary.refresh(self.tasks)
            self.stack.setCurrentIndex(1)
            self.nav.set_active(1)
        elif idx == 2:
            self.add_files()
            self.nav.set_active(0)
        elif idx == 3:
            self._open_settings()
            self.nav.set_active(0)

    def _open_detail(self, task):
        if self._detail_page:
            self.stack.removeWidget(self._detail_page)
            self._detail_page.deleteLater()
        page = DetailPage(task)
        page.back.connect(self._close_detail)
        page.copy_issue.connect(self._copy_single)
        page.edit_issue.connect(self._edit_single)
        page.delete_issue.connect(self._delete_single)
        page.show_detail.connect(self._show_issue_detail)  # 连接详情信号
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self._detail_page = page
        self.nav.set_active(0)

    def _close_detail(self):
        if self._detail_page:
            self.stack.setCurrentIndex(0)
            self.stack.removeWidget(self._detail_page)
            self._detail_page.deleteLater()
            self._detail_page = None

    def _save_prompt(self, text):
        self.config["last_prompt"] = text
        ConfigManager.save(self.config)

    def _open_settings(self):
        dlg = SettingsDialog(self, self.config)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.config = dlg.get_config()
            ConfigManager.save(self.config)
            self._toast("设置已保存 ✓")

    def add_files(self):
        current = len(self.tasks)
        if current >= MAX_IMAGES:
            QMessageBox.warning(self, "已达上限", f"最多 {MAX_IMAGES} 张，请先清空部分图片。")
            return
        remaining = MAX_IMAGES - current
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"选择图片（还能选 {remaining} 张）", "", "图片 (*.jpg *.jpeg *.png *.webp)")
        if not paths: return
        if len(paths) > remaining: paths = paths[:remaining]
        added = 0
        for path in paths:
            if any(t['path']==path for t in self.tasks): continue
            task = {"id": f"{time.time()}_{os.path.basename(path)}", "path": path,
                    "name": os.path.basename(path), "status": "waiting", "data": None}
            self.tasks.append(task)
            self.home.add_task(task)
            added += 1
        self.home.update_count(len(self.tasks))
        if added: self._toast(f"已添加 {added} 张图片")
        self.stack.setCurrentIndex(0)
        self.nav.set_active(0)

    def start_analysis(self):
        if not self.config.get("api_key"):
            self._toast("请先在⚙设置中配置 API Key", success=False)
            self._open_settings()
            return
        waiting = [t for t in self.tasks if t['status'] in ('waiting','error')]
        if not waiting:
            self._toast("没有待分析的图片", success=False)
            return
        self.total_task = len(waiting)
        self.done_task = 0
        self.home.set_progress(0, True)
        prompt_name = self.home.cbo_prompt.currentText()
        prompt_text = self.config.get("prompts", DEFAULT_PROMPTS).get(prompt_name, list(DEFAULT_PROMPTS.values())[0])

        for task in waiting:
            task['status'] = 'analyzing'
            self.home.update_task_status(task['id'], 'analyzing')
            w = AnalysisWorker(task, self.config, prompt_text)
            w.finished.connect(self._on_done)
            w.progress_msg.connect(self._on_progress)
            w.start()
            self.workers.append(w)

        self.home.set_status(f"正在分析 {len(waiting)} 张...")
        self._toast(f"开始分析 {len(waiting)} 张图片")

    def _on_progress(self, task_id, msg):
        task = next((t for t in self.tasks if t['id']==task_id), None)
        if task: task['progress_msg'] = msg
        self.home.update_task_status(task_id, 'analyzing', msg)
        if self._detail_page and self._detail_page.task['id'] == task_id:
            self._detail_page.refresh()

    def _on_done(self, task_id, data):
        task = next((t for t in self.tasks if t['id']==task_id), None)
        if not task: return
        if isinstance(data, dict) and 'error' in data:
            task['status'] = 'error'; task['error'] = data['error']
            self.home.update_task_status(task_id, 'error', data['error'][:35])
        else:
            task['status'] = 'done'; task['data'] = data
            cnt = len(data) if data else 0
            self.home.update_task_status(task_id, 'done', f"发现 {cnt} 个问题" if cnt else "未发现问题")
            self.done_task += 1
            self.home.set_progress(int(self.done_task / self.total_task * 100))

        if self._detail_page and self._detail_page.task['id'] == task_id:
            self._detail_page.refresh()

        if self.done_task >= self.total_task:
            self.home.set_progress(100, False)
            total = sum(len(t.get('data') or []) for t in self.tasks if t['status']=='done')
            self.home.set_status(f"分析完成，共 {total} 个问题")
            self._toast(f"分析完成！发现 {total} 个问题")

    def _copy_single(self, issue):
        text = (f"【{issue.get('risk_level','')}】\n{issue.get('issue','')}\n\n"
                f"📋 规范依据：{issue.get('regulation','')}\n"
                f"✅ 整改措施：{issue.get('correction','')}\n"
                f"🎯 置信度：{int(issue.get('confidence',0)*100)}%")
        QApplication.clipboard().setText(text)
        self._toast("已复制到剪贴板")

    def _edit_single(self, issue):
        """编辑单个问题"""
        try:
            dlg = EditIssueDialog(self, issue)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                updated = dlg.get_updated_item()
                # 更新任务数据
                task = self._detail_page.task if self._detail_page else None
                if task and task.get('data'):
                    for i, item in enumerate(task['data']):
                        if item is issue or (item.get('issue') == issue.get('issue') and item.get('category') == issue.get('category')):
                            task['data'][i] = updated
                            break
                # 刷新详情页
                if self._detail_page:
                    self._detail_page.refresh()
                self._toast("✓ 已保存修改")
        except Exception as e:
            self._toast(f"编辑失败：{str(e)}", success=False)

    def _delete_single(self, issue):
        """删除单个问题"""
        try:
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除这个问题吗？\n\n{issue.get('issue', '')[:50]}...",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # 从任务数据中删除
                task = self._detail_page.task if self._detail_page else None
                if task and task.get('data'):
                    task['data'] = [item for item in task['data'] 
                                    if not (item is issue or (item.get('issue') == issue.get('issue') and item.get('category') == issue.get('category')))]
                # 刷新详情页
                if self._detail_page:
                    self._detail_page.refresh()
                self._toast("✓ 已删除")
        except Exception as e:
            self._toast(f"删除失败：{str(e)}", success=False)

    def _delete_from_summary(self, issue):
        """从汇总页删除问题"""
        try:
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除这个问题吗？\n\n{issue.get('issue', '')[:50]}...",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # 从所有任务数据中删除
                for task in self.tasks:
                    if task.get('data'):
                        task['data'] = [item for item in task['data']
                                        if not (item.get('issue') == issue.get('issue') and
                                                item.get('category') == issue.get('category') and
                                                item.get('_src') == issue.get('_src'))]
                # 刷新汇总页
                self.summary.refresh(self.tasks)
                # 如果详情页打开，也刷新
                if self._detail_page:
                    self._detail_page.refresh()
                self._toast("✓ 已删除")
        except Exception as e:
            self._toast(f"删除失败：{str(e)}", success=False)

    def _show_issue_detail(self, issue):
        """显示问题详情弹窗"""
        try:
            dlg = IssueDetailDialog(self, issue)
            dlg.exec()
        except Exception as e:
            self._toast(f"显示详情失败：{str(e)}", success=False)

    def copy_all(self):
        all_issues = []
        for t in self.tasks:
            if t['status']=='done' and t.get('data'):
                for issue in t['data']:
                    issue['_src'] = t['name']; all_issues.append(issue)
        if not all_issues:
            self._toast("暂无可复制的问题", success=False); return
        priority = {"严重安全隐患":0,"一般安全隐患":1,"严重质量缺陷":2,"一般质量缺陷":3}
        sorted_issues = sorted(all_issues, key=lambda x: priority.get(x.get('risk_level',''),4))
        lines = [
            "🏗️ 质量安全检查问题清单",
            f"检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"分析图片：{len([t for t in self.tasks if t['status']=='done'])} 张",
            f"发现问题：{len(all_issues)} 个",
            "="*40, ""
        ]
        for i, issue in enumerate(sorted_issues, 1):
            lines += [f"{i}. 【{issue.get('risk_level','')}】",
                      f"   来源：{issue.get('_src','')}",
                      f"   {issue.get('issue','')}",
                      f"   📋 依据：{issue.get('regulation','')}",
                      f"   ✅ 整改：{issue.get('correction','')}", ""]
        QApplication.clipboard().setText("\n".join(lines))
        self._toast(f"已复制 {len(all_issues)} 个问题")

    def clear_queue(self):
        if not self.tasks: return
        reply = QMessageBox.question(self, "确认清空", "确定要清空所有图片吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._close_detail()
            self.tasks.clear()
            self.home.clear_all()
            self._toast("队列已清空")

    def _toast(self, text, success=True):
        """简单状态栏 Toast，不用动画，稳定可靠"""
        color = DS['success'] if success else DS['danger']
        self.home.set_status(f"{'✓' if success else '✕'}  {text}")
        # 2.5 秒后恢复
        QTimer.singleShot(2500, lambda: self.home.set_status("就绪"))


# ==================== 入口 ====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont()
    font.setFamilies(["PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC"])
    font.setPointSize(10)
    app.setFont(font)
   # app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
