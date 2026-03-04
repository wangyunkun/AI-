#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建设工程质量安全检查助手 - 手机版 V5.0
可编译为 Android/iOS 应用
基于 PyQt6 + Qwen-VL
"""

import sys, os, json, base64, time, re
from datetime import datetime
from typing import Dict, List
from openai import OpenAI

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QPixmap, QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QFrame, QFileDialog,
    QProgressBar, QMessageBox, QDialog, QLineEdit, QComboBox,
    QSizePolicy, QStackedWidget, QGraphicsDropShadowEffect,
    QDialogButtonBox
)

# ==================== 全局配置 ====================
CONFIG_FILE = "app_config.json"
MAX_IMAGES = 20

# 主题色
DS = {
    "primary": "#1A56DB",
    "primary_light": "#EBF0FF",
    "danger": "#E02424",
    "danger_light": "#FDE8E8",
    "success": "#057A55",
    "success_light": "#DEF7EC",
    "bg": "#F3F4F6",
    "surface": "#FFFFFF",
    "text_primary": "#111928",
    "text_secondary": "#6B7280",
    "text_hint": "#9CA3AF",
    "border": "#E5E7EB",
}

# 风险样式
RISK_STYLE = {
    "严重安全隐患": {"bg": "#FDE8E8", "border": "#E02424", "icon": "🔴", "priority": 0},
    "一般安全隐患": {"bg": "#FEF3C7", "border": "#D03801", "icon": "🟠", "priority": 1},
    "严重质量缺陷": {"bg": "#FFFBEB", "border": "#B45309", "icon": "🟡", "priority": 2},
    "一般质量缺陷": {"bg": "#E1EFFE", "border": "#1A56DB", "icon": "🔵", "priority": 3},
}

# AI 提供商
PROVIDER_PRESETS = {
    "阿里百炼 (Qwen-VL-Max)": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-vl-max"},
    "阿里百炼 (Qwen2.5-VL)": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen2.5-vl-72b"},
    "硅基流动 (Qwen2-VL)": {"base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen2-VL-72B-Instruct"},
}

# 提示词
DEFAULT_PROMPTS = {
    "V4.6 安全质量双聚焦": "聚焦安全隐患 + 质量问题",
    "安全隐患专项": "仅识别安全隐患",
    "质量问题专项": "仅识别质量问题",
}

# 知识库（简化版，适合手机端）
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


# ==================== 配置管理器 ====================
class ConfigManager:
    @staticmethod
    def load():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
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
        except:
            pass


# ==================== 分析线程 ====================
class AnalysisWorker(QThread):
    finished = pyqtSignal(str, object)
    progress = pyqtSignal(str, str)

    def __init__(self, task, config, prompt_text):
        super().__init__()
        self.task = task
        self.config = config
        self.prompt_text = prompt_text

    def run(self):
        try:
            p_name = self.config.get("current_provider", "阿里百炼 (Qwen2.5-VL)")
            api_key = self.config.get("api_key", "")
            p_conf = PROVIDER_PRESETS.get(p_name, {})
            base_url = p_conf.get("base_url", "")
            model = p_conf.get("model", "")

            if not api_key:
                self.finished.emit(self.task['id'], {"error": "未配置 API Key"})
                return
            if not base_url or not model:
                self.finished.emit(self.task['id'], {"error": "未配置模型"})
                return

            client = OpenAI(api_key=api_key, base_url=base_url)
            with open(self.task['path'], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            self.progress.emit(self.task['id'], "🔍 智能分诊中...")
            rr = client.chat.completions.create(
                model=model, temperature=0.1,
                messages=[{"role": "system", "content": ROUTER_PROMPT},
                          {"role": "user", "content": [
                              {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                              {"type": "text", "text": "请分析施工内容并选派专家"}]}])
            
            roles = self._parse_roles(rr.choices[0].message.content)
            if not roles:
                roles = ["安全"]
            if "安全" not in roles:
                roles.append("安全")

            all_issues = []
            for idx, role in enumerate(roles):
                self.progress.emit(self.task['id'], f"🔬 {role}专家分析 ({idx+1}/{len(roles)})")
                kb = REGULATION_DB.get(role, REGULATION_DB["安全"])
                resp = client.chat.completions.create(
                    model=model, temperature=0.3, max_tokens=4096,
                    messages=[{"role": "system", "content": self._build_prompt(role, kb)},
                              {"role": "user", "content": [
                                  {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                  {"type": "text", "text": "请分析图片，找出所有问题。输出 JSON 数组。"}]}])
                all_issues.extend(self._parse_issues(resp.choices[0].message.content, role))

            self.finished.emit(self.task['id'], all_issues)
        except Exception as e:
            self.finished.emit(self.task['id'], {"error": str(e)})

    def _parse_roles(self, text):
        try:
            m = re.search(r'\[.*?\]', text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except:
            pass
        return []

    def _build_prompt(self, role, kb):
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

    def _parse_issues(self, text, role):
        issues = []
        try:
            clean = text.replace("```json", "").replace("```", "").strip()
            s, e = clean.find('['), clean.rfind(']') + 1
            if s != -1 and e:
                for item in json.loads(clean[s:e]):
                    if isinstance(item, dict):
                        item["category"] = role
                        issues.append(item)
        except:
            pass
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
    card_clicked = pyqtSignal(dict)

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
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        # 头行
        hrow = QHBoxLayout()
        hrow.setSpacing(8)

        num = QLabel(str(index))
        num.setFixedSize(24, 24)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet(f"background:{st['border']};color:white;border-radius:12px;font-size:11px;font-weight:700;")
        hrow.addWidget(num)

        badge = QLabel(f"{st['icon']} {level}")
        badge.setStyleSheet(f"background:{st['border']};color:white;padding:3px 9px;border-radius:7px;font-size:12px;font-weight:700;")
        hrow.addWidget(badge)

        cat = item.get("category", "")
        if cat:
            cl = QLabel(cat)
            cl.setStyleSheet(f"background:{DS['surface']};color:{DS['text_secondary']};padding:3px 9px;border-radius:7px;font-size:11px;border:1px solid {DS['border']};")
            hrow.addWidget(cl)

        hrow.addStretch()

        # 按钮
        btn_edit = QPushButton("编辑")
        btn_edit.setFixedSize(48, 30)
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setStyleSheet(f"background:{DS['info_light']};color:{DS['primary']};border:none;border-radius:6px;font-size:12px;font-weight:600;")
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

        # 问题描述
        issue_text = item.get("issue", "")
        if len(issue_text) > 60:
            issue_text = issue_text[:60] + "..."
        lbl = QLabel(issue_text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"font-size:14px;color:{DS['text_primary']};font-weight:500;")
        lay.addWidget(lbl)

        # 提示
        hint = QLabel("💬 点击查看详情")
        hint.setStyleSheet(f"font-size:11px;color:{DS['text_hint']};font-style:italic;")
        lay.addWidget(hint)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color:{DS['border']};")
        lay.addWidget(line)

        # 依据和整改
        has_reg = bool(item.get("regulation", ""))
        has_corr = bool(item.get("correction", ""))
        if has_reg or has_corr:
            info_row = QHBoxLayout()
            info_row.setSpacing(10)
            if has_reg:
                info_row.addWidget(QLabel("📋"))
            if has_corr:
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
        super().mousePressEvent(event)
        self.card_clicked.emit(self.item)


class TaskRow(QWidget):
    clicked = pyqtSignal(dict)
    STATUS = {
        "waiting": ("⏳", DS["text_hint"], "等待中"),
        "analyzing": ("🔄", DS["primary"], "分析中"),
        "done": ("✅", DS["success"], "完成"),
        "error": ("❌", DS["danger"], "失败"),
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
                sc = pix.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                x = (sc.width() - 50) // 2
                y = (sc.height() - 50) // 2
                self.thumb.setPixmap(sc.copy(x, y, 50, 50))
        except:
            self.thumb.setText("📷")
        lay.addWidget(self.thumb)

        # 文字
        info = QVBoxLayout()
        info.setSpacing(3)
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
            t = QLineEdit()
            t.setMinimumHeight(42)
            t.setStyleSheet(f"""
                QLineEdit {{
                    background:{DS['bg']};border:1.5px solid {DS['border']};
                    border-radius:10px;padding:8px 12px;font-size:14px;
                }}
                QLineEdit:focus {{ border-color:{DS['primary']}; }}
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
        self.edt_issue.setText(item.get("issue", ""))
        lay.addWidget(self.edt_issue)

        # 规范依据
        lay.addWidget(label("规范依据"))
        self.edt_regulation = textedit()
        self.edt_regulation.setText(item.get("regulation", ""))
        lay.addWidget(self.edt_regulation)

        # 整改措施
        lay.addWidget(label("整改措施"))
        self.edt_correction = textedit()
        self.edt_correction.setText(item.get("correction", ""))
        lay.addWidget(self.edt_correction)

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
        return {
            **self.item,
            "risk_level": self.cbo_level.currentText(),
            "issue": self.edt_issue.text().strip(),
            "regulation": self.edt_regulation.text().strip(),
            "correction": self.edt_correction.text().strip(),
        }


# ==================== 详情弹窗 ====================
class IssueDetailDialog(QDialog):
    def __init__(self, parent, item):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle("📋 问题详情")
        self.setMinimumWidth(360)
        self.setMinimumHeight(400)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 16)

        # 标题
        level = item.get("risk_level", "一般质量缺陷")
        st = RISK_STYLE.get(level, RISK_STYLE["一般质量缺陷"])
        title = QLabel(f"{st['icon']} {level}")
        title.setStyleSheet(f"background:{st['border']};color:white;padding:10px;border-radius:8px;font-size:14px;font-weight:700;")
        lay.addWidget(title)

        # 滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        content = QWidget()
        content.setStyleSheet(f"background:{DS['bg']};")
        content_lay = QVBoxLayout(content)
        content_lay.setSpacing(10)

        # 问题描述
        desc_frame = QFrame()
        desc_frame.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
        desc_lay = QVBoxLayout(desc_frame)
        desc_lay.setContentsMargins(14, 12, 14, 12)
        desc_lay.setSpacing(8)
        desc_lay.addWidget(QLabel("📝 问题描述"))
        desc_text = QLabel(item.get("issue", ""))
        desc_text.setWordWrap(True)
        desc_text.setStyleSheet(f"font-size:14px;color:{DS['text_primary']};")
        desc_lay.addWidget(desc_text)
        content_lay.addWidget(desc_frame)

        # 规范依据
        if item.get("regulation"):
            reg_frame = QFrame()
            reg_frame.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
            reg_lay = QVBoxLayout(reg_frame)
            reg_lay.setContentsMargins(14, 12, 14, 12)
            reg_lay.setSpacing(8)
            reg_lay.addWidget(QLabel("📋 规范依据"))
            reg_text = QLabel(item.get("regulation", ""))
            reg_text.setWordWrap(True)
            reg_text.setStyleSheet(f"font-size:13px;color:{DS['text_secondary']};")
            reg_lay.addWidget(reg_text)
            content_lay.addWidget(reg_frame)

        # 整改措施
        if item.get("correction"):
            corr_frame = QFrame()
            corr_frame.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
            corr_lay = QVBoxLayout(corr_frame)
            corr_lay.setContentsMargins(14, 12, 14, 12)
            corr_lay.setSpacing(8)
            corr_lay.addWidget(QLabel("✅ 整改措施"))
            corr_text = QLabel(item.get("correction", ""))
            corr_text.setWordWrap(True)
            corr_text.setStyleSheet(f"font-size:13px;color:{DS['success']};")
            corr_lay.addWidget(corr_text)
            content_lay.addWidget(corr_frame)

        content_lay.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(100, 44)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"background:{DS['primary']};color:white;border:none;border-radius:10px;font-size:15px;font-weight:600;")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn)


# ==================== 设置对话框 ====================
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
        lay.addWidget(section("🔑 API KEY"))
        self.fld_key = field()
        self.fld_key.setPlaceholderText("粘贴您的 API Key...")
        self.fld_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.fld_key.setText(config.get("api_key", ""))
        lay.addWidget(self.fld_key)

        # 模型
        lay.addWidget(section("🤖 模型厂商"))
        self.cbo = combo()
        self.cbo.addItems(list(PROVIDER_PRESETS.keys()))
        self.cbo.setCurrentText(config.get("current_provider", "阿里百炼 (Qwen2.5-VL)"))
        lay.addWidget(self.cbo)

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
        return c


# ==================== 详情页 ====================
class DetailPage(QWidget):
    back = pyqtSignal()
    copy_issue = pyqtSignal(dict)
    edit_issue = pyqtSignal(dict)
    delete_issue = pyqtSignal(dict)
    show_detail = pyqtSignal(dict)

    def __init__(self, task):
        super().__init__()
        self.task = task
        self.setStyleSheet(f"background:{DS['bg']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 顶栏
        top = QWidget()
        top.setFixedHeight(56)
        top.setStyleSheet(f"background:{DS['primary']};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(10, 0, 16, 0)

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
                img_lbl.setPixmap(pix.scaled(390, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except:
            img_lbl.setText("📷 图片加载失败")
        lay.addWidget(img_lbl)

        # 结果
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;background:transparent;")
        rw = QWidget()
        rw.setStyleSheet(f"background:{DS['bg']};")
        self.rl = QVBoxLayout(rw)
        self.rl.setContentsMargins(12, 12, 12, 12)
        self.rl.setSpacing(10)
        self._render()
        scroll.setWidget(rw)
        lay.addWidget(scroll)

    def _render(self):
        task = self.task
        if task['status'] == 'waiting':
            self._state("⏳", "等待分析", "点击主页「▶ 开始分析」", DS['text_hint'])
        elif task['status'] == 'analyzing':
            self._state("🔄", "正在分析...", task.get('progress_msg', ''), DS['primary'])
        elif task['status'] == 'done':
            data = task.get('data') or []
            if not data:
                self._state("✅", "未发现问题", "该图片未检测到明显安全质量隐患", DS['success'])
            else:
                summary = QFrame()
                summary.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
                sl = QHBoxLayout(summary)
                sl.setContentsMargins(14, 10, 14, 10)
                sl.setSpacing(10)
                sl.addWidget(QLabel(f"共 {len(data)} 个问题"))
                sl.addStretch()
                counts = {}
                for item in data:
                    counts[item.get("risk_level", "")] = counts.get(item.get("risk_level", ""), 0) + 1
                for lvl, cnt in counts.items():
                    st = RISK_STYLE.get(lvl, RISK_STYLE["一般质量缺陷"])
                    p = QLabel(f"{st['icon']} {cnt}")
                    p.setStyleSheet(f"background:{st['bg']};color:{st['border']};padding:3px 9px;border-radius:7px;font-size:13px;font-weight:700;")
                    sl.addWidget(p)
                self.rl.addWidget(summary)

                sorted_data = sorted(data, key=lambda x: RISK_STYLE.get(x.get("risk_level", ""), RISK_STYLE["一般质量缺陷"])["priority"])
                for i, item in enumerate(sorted_data, 1):
                    card = RiskCard(item, i)
                    card.copy_requested.connect(self.copy_issue)
                    card.edit_requested.connect(self.edit_issue)
                    card.delete_requested.connect(self.delete_issue)
                    card.card_clicked.connect(self.show_detail)
                    self.rl.addWidget(card)
        elif task['status'] == 'error':
            self._state("❌", "分析失败", task.get('error', '未知错误'), DS['danger'])
        self.rl.addStretch()

    def _state(self, icon, title, sub, color):
        w = QFrame()
        w.setStyleSheet(f"background:{DS['surface']};border-radius:14px;border:1px solid {DS['border']};")
        wl = QVBoxLayout(w)
        wl.setContentsMargins(20, 30, 20, 30)
        wl.setSpacing(10)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for text, style in [(icon, "font-size:48px;"), (title, f"font-size:17px;font-weight:700;color:{color};"), (sub, f"font-size:13px;color:{DS['text_secondary']};")]:
            l = QLabel(text)
            l.setStyleSheet(style)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setWordWrap(True)
            wl.addWidget(l)
        self.rl.addWidget(w)

    def refresh(self):
        while self.rl.count():
            w = self.rl.takeAt(0)
            if w.widget():
                w.widget().deleteLater()
        self._render()


# ==================== 主页 ====================
class HomePage(QWidget):
    open_detail = pyqtSignal(dict)
    req_add = pyqtSignal()
    req_analyze = pyqtSignal()
    req_copy_all = pyqtSignal()
    req_clear = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.task_rows: Dict[str, TaskRow] = {}
        self.setStyleSheet(f"background:{DS['bg']};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 顶栏
        top = QWidget()
        top.setFixedHeight(56)
        top.setStyleSheet(f"background:{DS['primary']};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        title = QLabel("🏗️ 安全质检助手 V5.0")
        title.setStyleSheet("color:white;font-size:17px;font-weight:700;")
        tl.addWidget(title)
        tl.addStretch()
        self.lbl_count = QLabel("0/20")
        self.lbl_count.setStyleSheet("background:rgba(255,255,255,0.2);color:white;padding:4px 12px;border-radius:10px;font-size:13px;font-weight:600;")
        tl.addWidget(self.lbl_count)
        lay.addWidget(top)

        # 场景选择
        scene = QWidget()
        scene.setFixedHeight(52)
        scene.setStyleSheet(f"background:{DS['surface']};border-bottom:1px solid {DS['border']};")
        sl = QHBoxLayout(scene)
        sl.setContentsMargins(14, 0, 14, 0)
        sl.setSpacing(10)
        sl.addWidget(QLabel("检查场景"))
        self.cbo_prompt = QComboBox()
        self.cbo_prompt.addItems(list(DEFAULT_PROMPTS.keys()))
        self.cbo_prompt.setMinimumHeight(38)
        sl.addWidget(self.cbo_prompt, 1)
        lay.addWidget(scene)

        # 空状态
        self.empty = QWidget()
        self.empty.setStyleSheet(f"background:{DS['bg']};")
        el = QVBoxLayout(self.empty)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.setSpacing(12)
        for text, style in [("📷", "font-size:60px;"), ("添加施工图片", f"font-size:19px;font-weight:700;color:{DS['text_primary']};"), ("点击下方 ➕ 添加图片", f"font-size:14px;color:{DS['text_secondary']};")]:
            l = QLabel(text)
            l.setStyleSheet(style)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setWordWrap(True)
            el.addWidget(l)
        lay.addWidget(self.empty, 1)

        # 任务列表
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setStyleSheet("border:none;background:transparent;")
        self.list_scroll.hide()
        lc = QWidget()
        lc.setStyleSheet(f"background:{DS['bg']};")
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

        # 操作栏
        bottom = QWidget()
        bottom.setFixedHeight(68)
        bottom.setStyleSheet(f"background:{DS['surface']};border-top:1px solid {DS['border']};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(10)

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

        # 状态标签
        self.status_lbl = QLabel("就绪")
        self.status_lbl.setStyleSheet(f"font-size:12px;color:{DS['text_secondary']};padding:3px 14px;")
        lay.insertWidget(lay.count() - 1, self.status_lbl)

    def add_task(self, task):
        self.empty.hide()
        self.list_scroll.show()
        row = TaskRow(task)
        row.clicked.connect(self.open_detail)
        card = QFrame()
        card.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
        shadow(card, blur=5, y=1, alpha=12)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(row)
        self.list_lay.insertWidget(self.list_lay.count() - 1, card)
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
        if visible:
            self.progress.setValue(val)

    def clear_all(self):
        while self.list_lay.count() > 1:
            w = self.list_lay.takeAt(0)
            if w.widget():
                w.widget().deleteLater()
        self.task_rows.clear()
        self.empty.show()
        self.list_scroll.hide()
        self.update_count(0)
        self.set_status("就绪")


# ==================== 汇总页 ====================
class SummaryPage(QWidget):
    copy_all = pyqtSignal()
    delete_issue = pyqtSignal(dict)
    show_detail = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background:{DS['bg']};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        top = QWidget()
        top.setFixedHeight(56)
        top.setStyleSheet(f"background:{DS['primary']};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 0, 16, 0)
        tl.addWidget(QLabel("📊 问题汇总"))
        lay.addWidget(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;")
        self.cw = QWidget()
        self.cw.setStyleSheet(f"background:{DS['bg']};")
        self.cl = QVBoxLayout(self.cw)
        self.cl.setContentsMargins(12, 12, 12, 80)
        self.cl.setSpacing(10)
        scroll.setWidget(self.cw)
        lay.addWidget(scroll, 1)

        bottom = QWidget()
        bottom.setFixedHeight(68)
        bottom.setStyleSheet(f"background:{DS['surface']};border-top:1px solid {DS['border']};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(12, 10, 12, 10)
        btn = QPushButton("📋 复制全部问题")
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
            if w.widget():
                w.widget().deleteLater()
        w = QFrame()
        w.setStyleSheet(f"background:{DS['surface']};border-radius:14px;border:1px solid {DS['border']};")
        wl = QVBoxLayout(w)
        wl.setContentsMargins(30, 40, 30, 40)
        wl.setSpacing(10)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for text, style in [("📊", "font-size:52px;"), ("暂无分析结果", f"font-size:17px;font-weight:700;color:{DS['text_primary']};"), ("请先主页添加并分析图片", f"font-size:13px;color:{DS['text_secondary']};")]:
            l = QLabel(text)
            l.setStyleSheet(style)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(l)
        self.cl.addWidget(w)
        self.cl.addStretch()

    def refresh(self, tasks):
        while self.cl.count():
            w = self.cl.takeAt(0)
            if w.widget():
                w.widget().deleteLater()

        all_issues = []
        for t in tasks:
            if t['status'] == 'done' and t.get('data'):
                for issue in t['data']:
                    issue['_src'] = t['name']
                    all_issues.append(issue)

        if not all_issues:
            self._show_empty()
            return

        # 统计卡
        stats = QFrame()
        stats.setStyleSheet(f"background:{DS['surface']};border-radius:12px;border:1px solid {DS['border']};")
        sl = QVBoxLayout(stats)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(8)
        lbl = QLabel(f"共发现 {len(all_issues)} 个问题")
        lbl.setStyleSheet(f"font-size:16px;font-weight:700;color:{DS['text_primary']};")
        sl.addWidget(lbl)
        counts = {}
        for issue in all_issues:
            counts[issue.get("risk_level", "")] = counts.get(issue.get("risk_level", ""), 0) + 1
        pr = QHBoxLayout()
        pr.setSpacing(8)
        for lvl in ["严重安全隐患", "一般安全隐患", "严重质量缺陷", "一般质量缺陷"]:
            cnt = counts.get(lvl, 0)
            if cnt:
                st = RISK_STYLE[lvl]
                p = QLabel(f"{st['icon']} {lvl[:4]} {cnt}个")
                p.setStyleSheet(f"background:{st['bg']};color:{st['border']};padding:5px 10px;border-radius:8px;font-size:12px;font-weight:600;")
                pr.addWidget(p)
        pr.addStretch()
        sl.addLayout(pr)
        self.cl.addWidget(stats)

        sorted_issues = sorted(all_issues, key=lambda x: RISK_STYLE.get(x.get("risk_level", ""), RISK_STYLE["一般质量缺陷"])["priority"])
        for i, issue in enumerate(sorted_issues, 1):
            src = QLabel(f"📷 {issue.get('_src', '')}")
            src.setStyleSheet(f"font-size:11px;color:{DS['text_hint']};padding:2px 4px;")
            self.cl.addWidget(src)
            card = RiskCard(issue, i)
            card.delete_requested.connect(self.delete_issue)
            card.card_clicked.connect(self.show_detail)
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
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(0)
        self.btns = []
        for i, (icon, label) in enumerate([("🏠", "主页"), ("📊", "汇总"), ("➕", "添加"), ("⚙️", "设置")]):
            btn = QPushButton(f"{icon}\n{label}")
            btn.setMinimumHeight(60)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self.tab_changed.emit(idx))
            lay.addWidget(btn)
            self.btns.append(btn)
        self._refresh(0)

    def _refresh(self, active):
        for i, btn in enumerate(self.btns):
            color = DS['primary'] if i == active else DS['text_hint']
            w = '700' if i == active else '500'
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

        self.setWindowTitle("安全质检助手 V5.0")
        self.resize(390, 844)

        root = QWidget()
        self.setCentralWidget(root)
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

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
        self.summary.show_detail.connect(self._show_issue_detail)

        self.stack.addWidget(self.home)
        self.stack.addWidget(self.summary)

        rl.addWidget(self.stack, 1)

        self.nav = NavBar()
        self.nav.tab_changed.connect(self._on_nav)
        rl.addWidget(self.nav)

        last = self.config.get("last_prompt", "V4.6 安全质量双聚焦")
        if last in DEFAULT_PROMPTS:
            self.home.cbo_prompt.setCurrentText(last)

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
        page.show_detail.connect(self._show_issue_detail)
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

    def _show_issue_detail(self, issue):
        """显示问题详情"""
        try:
            dlg = IssueDetailDialog(self, issue)
            dlg.exec()
        except Exception as e:
            self._toast(f"显示详情失败：{str(e)}", success=False)

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
        paths, _ = QFileDialog.getOpenFileNames(self, f"选择图片（还能选 {remaining} 张）", "", "图片 (*.jpg *.jpeg *.png *.webp)")
        if not paths:
            return
        if len(paths) > remaining:
            paths = paths[:remaining]
        added = 0
        for path in paths:
            if any(t['path'] == path for t in self.tasks):
                continue
            task = {"id": f"{time.time()}_{os.path.basename(path)}", "path": path, "name": os.path.basename(path), "status": "waiting", "data": None}
            self.tasks.append(task)
            self.home.add_task(task)
            added += 1
        self.home.update_count(len(self.tasks))
        if added:
            self._toast(f"已添加 {added} 张图片")
        self.stack.setCurrentIndex(0)
        self.nav.set_active(0)

    def start_analysis(self):
        if not self.config.get("api_key"):
            self._toast("请先在⚙设置中配置 API Key", success=False)
            self._open_settings()
            return
        waiting = [t for t in self.tasks if t['status'] in ('waiting', 'error')]
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
            w.progress.connect(self._on_progress)
            w.start()
            self.workers.append(w)

        self.home.set_status(f"正在分析 {len(waiting)} 张...")
        self._toast(f"开始分析 {len(waiting)} 张图片")

    def _on_progress(self, task_id, msg):
        task = next((t for t in self.tasks if t['id'] == task_id), None)
        if task:
            task['progress_msg'] = msg
        self.home.update_task_status(task_id, 'analyzing', msg)
        if self._detail_page and self._detail_page.task['id'] == task_id:
            self._detail_page.refresh()

    def _on_done(self, task_id, data):
        task = next((t for t in self.tasks if t['id'] == task_id), None)
        if not task:
            return
        if isinstance(data, dict) and 'error' in data:
            task['status'] = 'error'
            task['error'] = data['error']
            self.home.update_task_status(task_id, 'error', data['error'][:35])
        else:
            task['status'] = 'done'
            task['data'] = data
            cnt = len(data) if data else 0
            self.home.update_task_status(task_id, 'done', f"发现 {cnt} 个问题" if cnt else "未发现问题")
            self.done_task += 1
            self.home.set_progress(int(self.done_task / self.total_task * 100))

        if self._detail_page and self._detail_page.task['id'] == task_id:
            self._detail_page.refresh()

        if self.done_task >= self.total_task:
            self.home.set_progress(100, False)
            total = sum(len(t.get('data') or []) for t in self.tasks if t['status'] == 'done')
            self.home.set_status(f"分析完成，共 {total} 个问题")
            self._toast(f"分析完成！发现 {total} 个问题")

    def _copy_single(self, issue):
        text = f"【{issue.get('risk_level', '')}】\n{issue.get('issue', '')}\n\n📋 规范依据：{issue.get('regulation', '')}\n✅ 整改措施：{issue.get('correction', '')}"
        QApplication.clipboard().setText(text)
        self._toast("已复制到剪贴板")

    def _edit_single(self, issue):
        """编辑单个问题"""
        try:
            dlg = EditIssueDialog(self, issue)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                updated = dlg.get_updated_item()
                task = self._detail_page.task if self._detail_page else None
                if task and task.get('data'):
                    for i, item in enumerate(task['data']):
                        if item.get('issue') == issue.get('issue') and item.get('category') == issue.get('category'):
                            task['data'][i] = updated
                            break
                if self._detail_page:
                    self._detail_page.refresh()
                self._toast("✓ 已保存修改")
        except Exception as e:
            self._toast(f"编辑失败：{str(e)}", success=False)

    def _delete_single(self, issue):
        """删除单个问题"""
        try:
            reply = QMessageBox.question(self, "确认删除", f"确定要删除这个问题吗？\n\n{issue.get('issue', '')[:50]}...", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                task = self._detail_page.task if self._detail_page else None
                if task and task.get('data'):
                    task['data'] = [item for item in task['data'] if not (item.get('issue') == issue.get('issue') and item.get('category') == issue.get('category'))]
                if self._detail_page:
                    self._detail_page.refresh()
                self._toast("✓ 已删除")
        except Exception as e:
            self._toast(f"删除失败：{str(e)}", success=False)

    def _delete_from_summary(self, issue):
        """从汇总页删除问题"""
        try:
            reply = QMessageBox.question(self, "确认删除", f"确定要删除这个问题吗？\n\n{issue.get('issue', '')[:50]}...", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                for task in self.tasks:
                    if task.get('data'):
                        task['data'] = [item for item in task['data'] if not (item.get('issue') == issue.get('issue') and item.get('category') == issue.get('category'))]
                self.summary.refresh(self.tasks)
                if self._detail_page:
                    self._detail_page.refresh()
                self._toast("✓ 已删除")
        except Exception as e:
            self._toast(f"删除失败：{str(e)}", success=False)

    def copy_all(self):
        all_issues = []
        for t in self.tasks:
            if t['status'] == 'done' and t.get('data'):
                for issue in t['data']:
                    issue['_src'] = t['name']
                    all_issues.append(issue)
        if not all_issues:
            self._toast("暂无可复制的问题", success=False)
            return
        priority = {"严重安全隐患": 0, "一般安全隐患": 1, "严重质量缺陷": 2, "一般质量缺陷": 3}
        sorted_issues = sorted(all_issues, key=lambda x: priority.get(x.get('risk_level', ''), 4))
        lines = ["🏗️ 质量安全检查问题清单", f"检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", f"分析图片：{len([t for t in self.tasks if t['status'] == 'done'])} 张", f"发现问题：{len(all_issues)} 个", "=" * 40, ""]
        for i, issue in enumerate(sorted_issues, 1):
            lines += [f"{i}. 【{issue.get('risk_level', '')}】", f"   来源：{issue.get('_src', '')}", f"   {issue.get('issue', '')}", f"   📋 依据：{issue.get('regulation', '')}", f"   ✅ 整改：{issue.get('correction', '')}", ""]
        QApplication.clipboard().setText("\n".join(lines))
        self._toast(f"已复制 {len(all_issues)} 个问题")

    def clear_queue(self):
        if not self.tasks:
            return
        reply = QMessageBox.question(self, "确认清空", "确定要清空所有图片吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._close_detail()
            self.tasks.clear()
            self.home.clear_all()
            self._toast("队列已清空")

    def _toast(self, text, success=True):
        color = DS['success'] if success else DS['danger']
        self.home.set_status(f"{'✓' if success else '✕'}  {text}")
        QTimer.singleShot(2500, lambda: self.home.set_status("就绪"))

    def closeEvent(self, event):
        """处理窗口关闭"""
        try:
            for w in self.workers:
                if w.isRunning():
                    w.terminate()
                    w.wait(100)
        except:
            pass
        event.accept()


# ==================== 入口 ====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont()
    font.setFamilies(["Microsoft YaHei", "Noto Sans CJK SC"])
    font.setPointSize(10)
    app.setFont(font)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
