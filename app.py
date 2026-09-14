#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================
  ระบบจดบันทึกทุกอย่างในชีวิตประจำวัน (Daily Life Logger)
  ----------------------------------------------------------------
  จดบันทึก: ค่าใช้จ่าย / เมนูอาหาร / การดื่มน้ำ / การออกกำลังกาย
  พร้อมเชื่อมโยง "ค่าใช้จ่าย" เข้ากับทุกกิจกรรม (ทุกบันทึกมีช่อง
  จำนวนเงินของตัวเอง เช่น ค่าอาหาร ค่าฟิตเนส ค่าน้ำดื่มบรรจุขวด ฯลฯ
  แล้วนำมารวมสรุปในหน้า "ค่าใช้จ่าย" และหน้าแดชบอร์ด)

  วิธีรัน:
      pip install flask
      python app.py
  แล้วเปิดเบราว์เซอร์ไปที่ http://127.0.0.1:5000

  ไฟล์เดียวจบ (Single File) - ใช้ SQLite เก็บข้อมูล (life_log.db
  จะถูกสร้างขึ้นอัตโนมัติในโฟลเดอร์เดียวกับไฟล์นี้)
  ใช้ Tailwind CSS ผ่าน CDN สำหรับหน้าตา ไม่ต้องติดตั้งอะไรเพิ่ม
=====================================================================
"""

import os
import sqlite3
from datetime import datetime, date
from flask import (
    Flask, g, request, redirect, url_for, flash, render_template_string
)
from jinja2 import DictLoader

# ---------------------------------------------------------------------------
# การตั้งค่าเบื้องต้น
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "life_log.db")
WATER_GOAL_ML = 2000  # เป้าหมายดื่มน้ำต่อวัน (มล.)

app = Flask(__name__)
app.secret_key = "dev-secret-key-life-logger"  # ใช้สำหรับ flash message เท่านั้น

EXPENSE_CATEGORIES = ["อาหาร", "เดินทาง", "ของใช้", "บันเทิง", "สุขภาพ", "บิล/ค่าใช้จ่ายประจำ", "อื่นๆ"]
MEAL_TYPES = ["มื้อเช้า", "มื้อกลางวัน", "มื้อเย็น", "ของว่าง"]
EXERCISE_SUGGESTIONS = ["วิ่ง", "เดิน", "ปั่นจักรยาน", "ยกน้ำหนัก", "โยคะ", "ว่ายน้ำ", "แอโรบิก"]

ENTRY_TYPE_LABELS = {
    "expense": "ค่าใช้จ่ายทั่วไป",
    "food": "อาหาร",
    "water": "ดื่มน้ำ",
    "exercise": "ออกกำลังกาย",
}
ENTRY_TYPE_ICONS = {
    "expense": "💰",
    "food": "🍽️",
    "water": "💧",
    "exercise": "🏃",
}
ENTRY_TYPE_COLORS = {
    "expense": "bg-amber-500",
    "food": "bg-orange-500",
    "water": "bg-sky-500",
    "exercise": "bg-emerald-500",
}


# ---------------------------------------------------------------------------
# การเชื่อมต่อฐานข้อมูล
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type TEXT NOT NULL CHECK(entry_type IN ('expense','food','water','exercise')),
            entry_date TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT,
            detail TEXT,
            amount REAL NOT NULL DEFAULT 0,
            water_ml REAL,
            exercise_minutes REAL,
            calories REAL,
            created_at TEXT NOT NULL
        )
    """)
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# ฟังก์ชันช่วยเหลือ
# ---------------------------------------------------------------------------
def today_str():
    return date.today().isoformat()


def now_time_str():
    return datetime.now().strftime("%H:%M")


def add_entry(entry_type, entry_date, entry_time, title, category=None, detail=None,
              amount=0.0, water_ml=None, exercise_minutes=None, calories=None):
    db = get_db()
    db.execute(
        """INSERT INTO entries
           (entry_type, entry_date, entry_time, title, category, detail,
            amount, water_ml, exercise_minutes, calories, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (entry_type, entry_date, entry_time, title, category, detail,
         amount, water_ml, exercise_minutes, calories,
         datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()


def fnum(value, default=0.0):
    """แปลงค่าจากฟอร์มเป็นตัวเลขอย่างปลอดภัย"""
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@app.template_filter("thb")
def thb_filter(value):
    try:
        return "{:,.2f}".format(float(value or 0))
    except (TypeError, ValueError):
        return "0.00"


@app.template_filter("num")
def num_filter(value):
    try:
        v = float(value or 0)
        if v == int(v):
            return "{:,.0f}".format(v)
        return "{:,.1f}".format(v)
    except (TypeError, ValueError):
        return "0"


app.jinja_env.globals.update(
    ENTRY_TYPE_LABELS=ENTRY_TYPE_LABELS,
    ENTRY_TYPE_ICONS=ENTRY_TYPE_ICONS,
    ENTRY_TYPE_COLORS=ENTRY_TYPE_COLORS,
    today_str=today_str,
)


# ---------------------------------------------------------------------------
# Templates (ใช้ DictLoader เพื่อรองรับ {% extends %} ในไฟล์เดียว)
# ---------------------------------------------------------------------------
TEMPLATES = {}

TEMPLATES["base.html"] = """
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}สมุดบันทึกชีวิตประจำวัน{% endblock %}</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: 'Segoe UI', 'Leelawadee UI', 'Sarabun', sans-serif; }
</style>
</head>
<body class="bg-slate-100 text-slate-800 min-h-screen">

  <nav class="bg-white shadow sticky top-0 z-10">
    <div class="max-w-5xl mx-auto px-4">
      <div class="flex items-center justify-between h-16">
        <a href="{{ url_for('dashboard') }}" class="flex items-center gap-2 font-bold text-lg text-indigo-600">
          <span class="text-2xl">📔</span> สมุดบันทึกชีวิตประจำวัน
        </a>
        <div class="hidden sm:flex gap-1 text-sm font-medium">
          {% set nav_items = [
            ('dashboard', 'แดชบอร์ด', '🏠'),
            ('expenses', 'ค่าใช้จ่าย', '💰'),
            ('food', 'อาหาร', '🍽️'),
            ('water', 'ดื่มน้ำ', '💧'),
            ('exercise', 'ออกกำลังกาย', '🏃'),
          ] %}
          {% for endpoint, label, icon in nav_items %}
            <a href="{{ url_for(endpoint) }}"
               class="px-3 py-2 rounded-lg transition {{ 'bg-indigo-600 text-white' if request.endpoint == endpoint else 'text-slate-600 hover:bg-slate-100' }}">
              {{ icon }} {{ label }}
            </a>
          {% endfor %}
        </div>
      </div>
      <div class="flex sm:hidden gap-1 text-xs font-medium pb-2 overflow-x-auto">
        {% for endpoint, label, icon in [
            ('dashboard', 'แดชบอร์ด', '🏠'),
            ('expenses', 'ค่าใช้จ่าย', '💰'),
            ('food', 'อาหาร', '🍽️'),
            ('water', 'ดื่มน้ำ', '💧'),
            ('exercise', 'ออกกำลังกาย', '🏃'),
          ] %}
          <a href="{{ url_for(endpoint) }}"
             class="px-3 py-1.5 rounded-lg whitespace-nowrap {{ 'bg-indigo-600 text-white' if request.endpoint == endpoint else 'bg-slate-100 text-slate-600' }}">
            {{ icon }} {{ label }}
          </a>
        {% endfor %}
      </div>
    </div>
  </nav>

  <main class="max-w-5xl mx-auto px-4 py-6">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        <div class="mb-4 space-y-2">
        {% for m in messages %}
          <div class="bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm px-4 py-2.5 rounded-lg">
            ✅ {{ m }}
          </div>
        {% endfor %}
        </div>
      {% endif %}
    {% endwith %}

    {% block content %}{% endblock %}
  </main>

  <footer class="text-center text-xs text-slate-400 py-6">
    บันทึกทุกอย่าง เชื่อมทุกค่าใช้จ่าย · Daily Life Logger
  </footer>
</body>
</html>
"""

TEMPLATES["dashboard.html"] = """
{% extends "base.html" %}
{% block title %}แดชบอร์ด - สมุดบันทึกชีวิตประจำวัน{% endblock %}
{% block content %}

<h1 class="text-2xl font-bold mb-1">👋 ภาพรวมวันนี้</h1>
<p class="text-slate-500 text-sm mb-6">{{ today }}</p>

<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
  <div class="bg-white rounded-2xl shadow p-4">
    <div class="text-2xl">💰</div>
    <div class="text-xs text-slate-500 mt-1">ค่าใช้จ่ายวันนี้</div>
    <div class="text-xl font-bold text-amber-600">{{ today_expense|thb }} ฿</div>
  </div>
  <div class="bg-white rounded-2xl shadow p-4">
    <div class="text-2xl">💧</div>
    <div class="text-xs text-slate-500 mt-1">น้ำดื่มวันนี้</div>
    <div class="text-xl font-bold text-sky-600">{{ today_water|num }} มล.</div>
    <div class="w-full bg-sky-100 rounded-full h-1.5 mt-2">
      <div class="bg-sky-500 h-1.5 rounded-full" style="width: {{ water_pct }}%"></div>
    </div>
    <div class="text-[11px] text-slate-400 mt-1">เป้าหมาย {{ water_goal }} มล.</div>
  </div>
  <div class="bg-white rounded-2xl shadow p-4">
    <div class="text-2xl">🏃</div>
    <div class="text-xs text-slate-500 mt-1">ออกกำลังกายวันนี้</div>
    <div class="text-xl font-bold text-emerald-600">{{ today_exercise_minutes|num }} นาที</div>
    <div class="text-[11px] text-slate-400 mt-1">เผาผลาญ {{ today_calories_burned|num }} kcal</div>
  </div>
  <div class="bg-white rounded-2xl shadow p-4">
    <div class="text-2xl">🍽️</div>
    <div class="text-xs text-slate-500 mt-1">มื้ออาหารวันนี้</div>
    <div class="text-xl font-bold text-orange-600">{{ today_food_count }} มื้อ</div>
    <div class="text-[11px] text-slate-400 mt-1">{{ today_food_calories|num }} kcal</div>
  </div>
</div>

<div class="grid md:grid-cols-2 gap-6 mb-8">
  <div class="bg-white rounded-2xl shadow p-5">
    <h2 class="font-semibold mb-3">ค่าใช้จ่ายวันนี้ แยกตามกิจกรรม</h2>
    {% if expense_breakdown %}
      <div class="space-y-3">
      {% for row in expense_breakdown %}
        <div>
          <div class="flex justify-between text-sm mb-1">
            <span>{{ ENTRY_TYPE_ICONS[row.entry_type] }} {{ ENTRY_TYPE_LABELS[row.entry_type] }}</span>
            <span class="font-medium">{{ row.total|thb }} ฿</span>
          </div>
          <div class="w-full bg-slate-100 rounded-full h-2">
            <div class="{{ ENTRY_TYPE_COLORS[row.entry_type] }} h-2 rounded-full" style="width: {{ row.pct }}%"></div>
          </div>
        </div>
      {% endfor %}
      </div>
    {% else %}
      <p class="text-sm text-slate-400">ยังไม่มีค่าใช้จ่ายวันนี้</p>
    {% endif %}
    <div class="mt-4 pt-3 border-t text-sm flex justify-between">
      <span class="text-slate-500">รวมค่าใช้จ่ายเดือนนี้</span>
      <span class="font-semibold">{{ month_expense|thb }} ฿</span>
    </div>
  </div>

  <div class="bg-white rounded-2xl shadow p-5">
    <h2 class="font-semibold mb-3">รายการล่าสุด</h2>
    {% if recent %}
      <ul class="space-y-2 text-sm max-h-64 overflow-y-auto">
      {% for e in recent %}
        <li class="flex items-center justify-between border-b border-slate-50 pb-2">
          <div>
            <span>{{ ENTRY_TYPE_ICONS[e.entry_type] }}</span>
            <span class="font-medium">{{ e.title }}</span>
            <span class="text-slate-400 text-xs">· {{ e.entry_date }} {{ e.entry_time }}</span>
          </div>
          {% if e.amount %}
            <span class="text-amber-600 font-medium whitespace-nowrap ml-2">{{ e.amount|thb }} ฿</span>
          {% endif %}
        </li>
      {% endfor %}
      </ul>
    {% else %}
      <p class="text-sm text-slate-400">ยังไม่มีรายการบันทึก เริ่มบันทึกได้จากเมนูด้านบน</p>
    {% endif %}
  </div>
</div>

<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
  <a href="{{ url_for('expenses') }}" class="bg-amber-500 hover:bg-amber-600 text-white rounded-xl p-4 text-center font-medium shadow">+ ค่าใช้จ่าย</a>
  <a href="{{ url_for('food') }}" class="bg-orange-500 hover:bg-orange-600 text-white rounded-xl p-4 text-center font-medium shadow">+ อาหาร</a>
  <a href="{{ url_for('water') }}" class="bg-sky-500 hover:bg-sky-600 text-white rounded-xl p-4 text-center font-medium shadow">+ น้ำดื่ม</a>
  <a href="{{ url_for('exercise') }}" class="bg-emerald-500 hover:bg-emerald-600 text-white rounded-xl p-4 text-center font-medium shadow">+ ออกกำลังกาย</a>
</div>

{% endblock %}
"""

TEMPLATES["expenses.html"] = """
{% extends "base.html" %}
{% block title %}ค่าใช้จ่าย - สมุดบันทึกชีวิตประจำวัน{% endblock %}
{% block content %}

<h1 class="text-2xl font-bold mb-6">💰 ค่าใช้จ่าย</h1>

<div class="grid md:grid-cols-3 gap-6">
  <div class="md:col-span-1">
    <div class="bg-white rounded-2xl shadow p-5 mb-6">
      <h2 class="font-semibold mb-4">บันทึกค่าใช้จ่ายใหม่</h2>
      <form method="post" action="{{ url_for('expenses') }}" class="space-y-3">
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-xs text-slate-500">วันที่</label>
            <input type="date" name="entry_date" value="{{ today }}" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
          <div>
            <label class="text-xs text-slate-500">เวลา</label>
            <input type="time" name="entry_time" value="{{ now_time }}" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
        </div>
        <div>
          <label class="text-xs text-slate-500">รายการ</label>
          <input type="text" name="title" placeholder="เช่น ค่าตัดผม, ค่าน้ำมัน" required
                 class="w-full border rounded-lg px-3 py-2 text-sm">
        </div>
        <div>
          <label class="text-xs text-slate-500">หมวดหมู่</label>
          <select name="category" class="w-full border rounded-lg px-3 py-2 text-sm">
            {% for c in categories %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
          </select>
        </div>
        <div>
          <label class="text-xs text-slate-500">จำนวนเงิน (บาท)</label>
          <input type="number" step="0.01" min="0" name="amount" placeholder="0.00" required
                 class="w-full border rounded-lg px-3 py-2 text-sm">
        </div>
        <div>
          <label class="text-xs text-slate-500">รายละเอียดเพิ่มเติม</label>
          <textarea name="detail" rows="2" class="w-full border rounded-lg px-3 py-2 text-sm"></textarea>
        </div>
        <button class="w-full bg-amber-500 hover:bg-amber-600 text-white rounded-lg py-2.5 font-medium">
          บันทึกค่าใช้จ่าย
        </button>
      </form>
    </div>

    <div class="bg-white rounded-2xl shadow p-5">
      <h2 class="font-semibold mb-3">สรุปตามหมวดหมู่ ({{ month_label }})</h2>
      {% if by_category %}
        <div class="space-y-3">
        {% for row in by_category %}
          <div>
            <div class="flex justify-between text-sm mb-1">
              <span>{{ row.category or 'ไม่ระบุ' }}</span>
              <span class="font-medium">{{ row.total|thb }} ฿</span>
            </div>
            <div class="w-full bg-slate-100 rounded-full h-2">
              <div class="bg-amber-500 h-2 rounded-full" style="width: {{ row.pct }}%"></div>
            </div>
          </div>
        {% endfor %}
        </div>
      {% else %}
        <p class="text-sm text-slate-400">ไม่มีข้อมูลในเดือนนี้</p>
      {% endif %}
      <div class="mt-4 pt-3 border-t text-sm flex justify-between font-semibold">
        <span>รวมทั้งหมด</span><span>{{ month_total|thb }} ฿</span>
      </div>
    </div>
  </div>

  <div class="md:col-span-2">
    <div class="bg-white rounded-2xl shadow p-5">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 class="font-semibold">ทุกค่าใช้จ่าย (เชื่อมโยงจากทุกกิจกรรม)</h2>
        <form method="get" class="flex items-center gap-2">
          <input type="month" name="month" value="{{ month_value }}"
                 class="border rounded-lg px-2 py-1 text-sm" onchange="this.form.submit()">
        </form>
      </div>
      {% if entries %}
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-slate-400 border-b">
              <th class="py-2 pr-2">วันที่/เวลา</th>
              <th class="py-2 pr-2">กิจกรรม</th>
              <th class="py-2 pr-2">รายการ</th>
              <th class="py-2 pr-2">หมวดหมู่</th>
              <th class="py-2 pr-2 text-right">จำนวนเงิน</th>
              <th class="py-2 pl-2"></th>
            </tr>
          </thead>
          <tbody>
          {% for e in entries %}
            <tr class="border-b border-slate-50 hover:bg-slate-50">
              <td class="py-2 pr-2 whitespace-nowrap text-slate-500">{{ e.entry_date }}<br>{{ e.entry_time }}</td>
              <td class="py-2 pr-2 whitespace-nowrap">{{ ENTRY_TYPE_ICONS[e.entry_type] }} {{ ENTRY_TYPE_LABELS[e.entry_type] }}</td>
              <td class="py-2 pr-2">{{ e.title }}{% if e.detail %}<div class="text-xs text-slate-400">{{ e.detail }}</div>{% endif %}</td>
              <td class="py-2 pr-2 text-slate-500">{{ e.category or '-' }}</td>
              <td class="py-2 pr-2 text-right font-medium text-amber-600 whitespace-nowrap">{{ e.amount|thb }} ฿</td>
              <td class="py-2 pl-2 text-right">
                <form method="post" action="{{ url_for('delete_entry', entry_id=e.id) }}"
                      onsubmit="return confirm('ลบรายการนี้?');">
                  <input type="hidden" name="next" value="{{ url_for('expenses', month=month_value) }}">
                  <button class="text-slate-300 hover:text-red-500" title="ลบ">✕</button>
                </form>
              </td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
        <p class="text-sm text-slate-400">ไม่มีค่าใช้จ่ายในเดือนนี้</p>
      {% endif %}
    </div>
  </div>
</div>

{% endblock %}
"""

TEMPLATES["food.html"] = """
{% extends "base.html" %}
{% block title %}อาหาร - สมุดบันทึกชีวิตประจำวัน{% endblock %}
{% block content %}

<h1 class="text-2xl font-bold mb-6">🍽️ เมนูอาหาร</h1>

<div class="grid md:grid-cols-3 gap-6">
  <div class="md:col-span-1">
    <div class="bg-white rounded-2xl shadow p-5">
      <h2 class="font-semibold mb-4">บันทึกมื้ออาหาร</h2>
      <form method="post" action="{{ url_for('food') }}" class="space-y-3">
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-xs text-slate-500">วันที่</label>
            <input type="date" name="entry_date" value="{{ today }}" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
          <div>
            <label class="text-xs text-slate-500">เวลา</label>
            <input type="time" name="entry_time" value="{{ now_time }}" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
        </div>
        <div>
          <label class="text-xs text-slate-500">มื้อ</label>
          <select name="category" class="w-full border rounded-lg px-3 py-2 text-sm">
            {% for m in meal_types %}<option value="{{ m }}">{{ m }}</option>{% endfor %}
          </select>
        </div>
        <div>
          <label class="text-xs text-slate-500">ชื่อเมนู</label>
          <input type="text" name="title" placeholder="เช่น ข้าวผัดกะเพราไก่" required
                 class="w-full border rounded-lg px-3 py-2 text-sm">
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-xs text-slate-500">แคลอรี่ (kcal)</label>
            <input type="number" step="1" min="0" name="calories" placeholder="ไม่บังคับ"
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
          <div>
            <label class="text-xs text-slate-500">ค่าใช้จ่าย (บาท)</label>
            <input type="number" step="0.01" min="0" name="amount" placeholder="0.00"
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
        </div>
        <div>
          <label class="text-xs text-slate-500">รายละเอียดเพิ่มเติม</label>
          <textarea name="detail" rows="2" class="w-full border rounded-lg px-3 py-2 text-sm"></textarea>
        </div>
        <button class="w-full bg-orange-500 hover:bg-orange-600 text-white rounded-lg py-2.5 font-medium">
          บันทึกมื้ออาหาร
        </button>
      </form>
    </div>
  </div>

  <div class="md:col-span-2">
    <div class="bg-white rounded-2xl shadow p-5">
      <h2 class="font-semibold mb-4">ประวัติการกิน (ล่าสุด)</h2>
      {% if entries %}
      <ul class="divide-y divide-slate-50">
        {% for e in entries %}
        <li class="py-3 flex items-start justify-between gap-3">
          <div>
            <div class="font-medium">{{ e.title }} <span class="text-xs text-slate-400 font-normal">· {{ e.category }}</span></div>
            <div class="text-xs text-slate-400">{{ e.entry_date }} {{ e.entry_time }}
              {% if e.calories %}· {{ e.calories|num }} kcal{% endif %}
              {% if e.detail %}· {{ e.detail }}{% endif %}
            </div>
          </div>
          <div class="flex items-center gap-3 whitespace-nowrap">
            {% if e.amount %}<span class="text-amber-600 font-medium text-sm">{{ e.amount|thb }} ฿</span>{% endif %}
            <form method="post" action="{{ url_for('delete_entry', entry_id=e.id) }}" onsubmit="return confirm('ลบรายการนี้?');">
              <input type="hidden" name="next" value="{{ url_for('food') }}">
              <button class="text-slate-300 hover:text-red-500">✕</button>
            </form>
          </div>
        </li>
        {% endfor %}
      </ul>
      {% else %}
        <p class="text-sm text-slate-400">ยังไม่มีบันทึกอาหาร</p>
      {% endif %}
    </div>
  </div>
</div>

{% endblock %}
"""

TEMPLATES["water.html"] = """
{% extends "base.html" %}
{% block title %}ดื่มน้ำ - สมุดบันทึกชีวิตประจำวัน{% endblock %}
{% block content %}

<h1 class="text-2xl font-bold mb-6">💧 การดื่มน้ำ</h1>

<div class="bg-white rounded-2xl shadow p-5 mb-6">
  <div class="flex items-center justify-between mb-2">
    <span class="text-sm text-slate-500">วันนี้ดื่มไปแล้ว</span>
    <span class="text-sm font-semibold text-sky-600">{{ today_water|num }} / {{ water_goal }} มล.</span>
  </div>
  <div class="w-full bg-sky-100 rounded-full h-3">
    <div class="bg-sky-500 h-3 rounded-full transition-all" style="width: {{ water_pct }}%"></div>
  </div>
  <div class="flex flex-wrap gap-2 mt-4">
    {% for ml in [250, 350, 500, 1000] %}
    <form method="post" action="{{ url_for('quick_water') }}">
      <input type="hidden" name="ml" value="{{ ml }}">
      <button class="bg-sky-50 hover:bg-sky-100 text-sky-700 border border-sky-200 rounded-lg px-4 py-2 text-sm font-medium">
        + {{ ml }} มล.
      </button>
    </form>
    {% endfor %}
  </div>
</div>

<div class="grid md:grid-cols-3 gap-6">
  <div class="md:col-span-1">
    <div class="bg-white rounded-2xl shadow p-5">
      <h2 class="font-semibold mb-4">บันทึกแบบกำหนดเอง</h2>
      <form method="post" action="{{ url_for('water') }}" class="space-y-3">
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-xs text-slate-500">วันที่</label>
            <input type="date" name="entry_date" value="{{ today }}" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
          <div>
            <label class="text-xs text-slate-500">เวลา</label>
            <input type="time" name="entry_time" value="{{ now_time }}" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
        </div>
        <div>
          <label class="text-xs text-slate-500">ปริมาณ (มล.)</label>
          <input type="number" step="1" min="1" name="water_ml" placeholder="เช่น 300" required
                 class="w-full border rounded-lg px-3 py-2 text-sm">
        </div>
        <div>
          <label class="text-xs text-slate-500">ค่าใช้จ่าย (บาท) เช่น น้ำดื่มบรรจุขวด</label>
          <input type="number" step="0.01" min="0" name="amount" placeholder="0.00"
                 class="w-full border rounded-lg px-3 py-2 text-sm">
        </div>
        <div>
          <label class="text-xs text-slate-500">หมายเหตุ</label>
          <input type="text" name="detail" placeholder="เช่น น้ำเปล่า, น้ำแร่"
                 class="w-full border rounded-lg px-3 py-2 text-sm">
        </div>
        <button class="w-full bg-sky-500 hover:bg-sky-600 text-white rounded-lg py-2.5 font-medium">
          บันทึกการดื่มน้ำ
        </button>
      </form>
    </div>
  </div>

  <div class="md:col-span-2">
    <div class="bg-white rounded-2xl shadow p-5">
      <h2 class="font-semibold mb-4">ประวัติการดื่มน้ำ (ล่าสุด)</h2>
      {% if entries %}
      <ul class="divide-y divide-slate-50">
        {% for e in entries %}
        <li class="py-3 flex items-start justify-between gap-3">
          <div>
            <div class="font-medium">{{ e.water_ml|num }} มล.{% if e.detail %} <span class="text-xs text-slate-400 font-normal">· {{ e.detail }}</span>{% endif %}</div>
            <div class="text-xs text-slate-400">{{ e.entry_date }} {{ e.entry_time }}</div>
          </div>
          <div class="flex items-center gap-3 whitespace-nowrap">
            {% if e.amount %}<span class="text-amber-600 font-medium text-sm">{{ e.amount|thb }} ฿</span>{% endif %}
            <form method="post" action="{{ url_for('delete_entry', entry_id=e.id) }}" onsubmit="return confirm('ลบรายการนี้?');">
              <input type="hidden" name="next" value="{{ url_for('water') }}">
              <button class="text-slate-300 hover:text-red-500">✕</button>
            </form>
          </div>
        </li>
        {% endfor %}
      </ul>
      {% else %}
        <p class="text-sm text-slate-400">ยังไม่มีบันทึกการดื่มน้ำ</p>
      {% endif %}
    </div>
  </div>
</div>

{% endblock %}
"""

TEMPLATES["exercise.html"] = """
{% extends "base.html" %}
{% block title %}ออกกำลังกาย - สมุดบันทึกชีวิตประจำวัน{% endblock %}
{% block content %}

<h1 class="text-2xl font-bold mb-6">🏃 การออกกำลังกาย</h1>

<div class="grid md:grid-cols-3 gap-6">
  <div class="md:col-span-1">
    <div class="bg-white rounded-2xl shadow p-5">
      <h2 class="font-semibold mb-4">บันทึกการออกกำลังกาย</h2>
      <form method="post" action="{{ url_for('exercise') }}" class="space-y-3">
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-xs text-slate-500">วันที่</label>
            <input type="date" name="entry_date" value="{{ today }}" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
          <div>
            <label class="text-xs text-slate-500">เวลา</label>
            <input type="time" name="entry_time" value="{{ now_time }}" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
        </div>
        <div>
          <label class="text-xs text-slate-500">ประเภทกิจกรรม</label>
          <input list="exercise-suggestions" name="title" placeholder="เช่น วิ่ง, โยคะ" required
                 class="w-full border rounded-lg px-3 py-2 text-sm">
          <datalist id="exercise-suggestions">
            {% for s in suggestions %}<option value="{{ s }}">{% endfor %}
          </datalist>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-xs text-slate-500">ระยะเวลา (นาที)</label>
            <input type="number" step="1" min="0" name="exercise_minutes" placeholder="30" required
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
          <div>
            <label class="text-xs text-slate-500">แคลอรี่ที่เผาผลาญ (kcal)</label>
            <input type="number" step="1" min="0" name="calories" placeholder="ไม่บังคับ"
                   class="w-full border rounded-lg px-3 py-2 text-sm">
          </div>
        </div>
        <div>
          <label class="text-xs text-slate-500">ค่าใช้จ่าย (บาท) เช่น ค่าฟิตเนส/อุปกรณ์</label>
          <input type="number" step="0.01" min="0" name="amount" placeholder="0.00"
                 class="w-full border rounded-lg px-3 py-2 text-sm">
        </div>
        <div>
          <label class="text-xs text-slate-500">รายละเอียดเพิ่มเติม</label>
          <textarea name="detail" rows="2" class="w-full border rounded-lg px-3 py-2 text-sm"></textarea>
        </div>
        <button class="w-full bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg py-2.5 font-medium">
          บันทึกการออกกำลังกาย
        </button>
      </form>
    </div>
  </div>

  <div class="md:col-span-2">
    <div class="bg-white rounded-2xl shadow p-5">
      <h2 class="font-semibold mb-4">ประวัติการออกกำลังกาย (ล่าสุด)</h2>
      {% if entries %}
      <ul class="divide-y divide-slate-50">
        {% for e in entries %}
        <li class="py-3 flex items-start justify-between gap-3">
          <div>
            <div class="font-medium">{{ e.title }}</div>
            <div class="text-xs text-slate-400">{{ e.entry_date }} {{ e.entry_time }} ·
              {{ e.exercise_minutes|num }} นาที
              {% if e.calories %}· {{ e.calories|num }} kcal{% endif %}
              {% if e.detail %}· {{ e.detail }}{% endif %}
            </div>
          </div>
          <div class="flex items-center gap-3 whitespace-nowrap">
            {% if e.amount %}<span class="text-amber-600 font-medium text-sm">{{ e.amount|thb }} ฿</span>{% endif %}
            <form method="post" action="{{ url_for('delete_entry', entry_id=e.id) }}" onsubmit="return confirm('ลบรายการนี้?');">
              <input type="hidden" name="next" value="{{ url_for('exercise') }}">
              <button class="text-slate-300 hover:text-red-500">✕</button>
            </form>
          </div>
        </li>
        {% endfor %}
      </ul>
      {% else %}
        <p class="text-sm text-slate-400">ยังไม่มีบันทึกการออกกำลังกาย</p>
      {% endif %}
    </div>
  </div>
</div>

{% endblock %}
"""

app.jinja_loader = DictLoader(TEMPLATES)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    db = get_db()
    t = today_str()
    month_prefix = t[:7]  # YYYY-MM

    today_expense = db.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM entries WHERE entry_date=?", (t,)
    ).fetchone()["s"]

    month_expense = db.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM entries WHERE entry_date LIKE ?", (month_prefix + "%",)
    ).fetchone()["s"]

    today_water = db.execute(
        "SELECT COALESCE(SUM(water_ml),0) s FROM entries WHERE entry_type='water' AND entry_date=?", (t,)
    ).fetchone()["s"]

    today_exercise_minutes = db.execute(
        "SELECT COALESCE(SUM(exercise_minutes),0) s FROM entries WHERE entry_type='exercise' AND entry_date=?", (t,)
    ).fetchone()["s"]

    today_calories_burned = db.execute(
        "SELECT COALESCE(SUM(calories),0) s FROM entries WHERE entry_type='exercise' AND entry_date=?", (t,)
    ).fetchone()["s"]

    today_food_row = db.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(calories),0) s FROM entries WHERE entry_type='food' AND entry_date=?", (t,)
    ).fetchone()
    today_food_count = today_food_row["c"]
    today_food_calories = today_food_row["s"]

    breakdown_rows = db.execute(
        """SELECT entry_type, COALESCE(SUM(amount),0) total FROM entries
           WHERE entry_date=? AND amount > 0 GROUP BY entry_type ORDER BY total DESC""",
        (t,),
    ).fetchall()
    max_b = max([r["total"] for r in breakdown_rows], default=0)
    expense_breakdown = [
        {"entry_type": r["entry_type"], "total": r["total"],
         "pct": round((r["total"] / max_b) * 100) if max_b else 0}
        for r in breakdown_rows
    ]

    recent = db.execute(
        "SELECT * FROM entries ORDER BY entry_date DESC, entry_time DESC, id DESC LIMIT 10"
    ).fetchall()

    water_pct = min(round((today_water / WATER_GOAL_ML) * 100), 100) if WATER_GOAL_ML else 0

    return render_template_string(
        TEMPLATES["dashboard.html"],
        today=t,
        today_expense=today_expense,
        month_expense=month_expense,
        today_water=today_water,
        water_goal=WATER_GOAL_ML,
        water_pct=water_pct,
        today_exercise_minutes=today_exercise_minutes,
        today_calories_burned=today_calories_burned,
        today_food_count=today_food_count,
        today_food_calories=today_food_calories,
        expense_breakdown=expense_breakdown,
        recent=recent,
    )


@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("กรุณากรอกชื่อรายการ")
            return redirect(url_for("expenses"))
        add_entry(
            entry_type="expense",
            entry_date=request.form.get("entry_date") or today_str(),
            entry_time=request.form.get("entry_time") or now_time_str(),
            title=title,
            category=request.form.get("category"),
            detail=request.form.get("detail", "").strip() or None,
            amount=fnum(request.form.get("amount")),
        )
        flash("บันทึกค่าใช้จ่ายเรียบร้อยแล้ว")
        return redirect(url_for("expenses", month=request.form.get("entry_date", today_str())[:7]))

    month_value = request.args.get("month") or today_str()[:7]
    month_label = month_value

    entries = db.execute(
        """SELECT * FROM entries WHERE amount > 0 AND entry_date LIKE ?
           ORDER BY entry_date DESC, entry_time DESC, id DESC""",
        (month_value + "%",),
    ).fetchall()

    month_total = sum(e["amount"] for e in entries)

    cat_rows = db.execute(
        """SELECT COALESCE(category,'ไม่ระบุ') category, COALESCE(SUM(amount),0) total
           FROM entries WHERE amount > 0 AND entry_date LIKE ?
           GROUP BY category ORDER BY total DESC""",
        (month_value + "%",),
    ).fetchall()
    max_c = max([r["total"] for r in cat_rows], default=0)
    by_category = [
        {"category": r["category"], "total": r["total"],
         "pct": round((r["total"] / max_c) * 100) if max_c else 0}
        for r in cat_rows
    ]

    return render_template_string(
        TEMPLATES["expenses.html"],
        today=today_str(),
        now_time=now_time_str(),
        categories=EXPENSE_CATEGORIES,
        entries=entries,
        month_value=month_value,
        month_label=month_label,
        month_total=month_total,
        by_category=by_category,
    )


@app.route("/food", methods=["GET", "POST"])
def food():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("กรุณากรอกชื่อเมนู")
            return redirect(url_for("food"))
        add_entry(
            entry_type="food",
            entry_date=request.form.get("entry_date") or today_str(),
            entry_time=request.form.get("entry_time") or now_time_str(),
            title=title,
            category=request.form.get("category"),
            detail=request.form.get("detail", "").strip() or None,
            amount=fnum(request.form.get("amount")),
            calories=fnum(request.form.get("calories"), None) if request.form.get("calories") else None,
        )
        flash("บันทึกมื้ออาหารเรียบร้อยแล้ว")
        return redirect(url_for("food"))

    entries = db.execute(
        "SELECT * FROM entries WHERE entry_type='food' ORDER BY entry_date DESC, entry_time DESC, id DESC LIMIT 100"
    ).fetchall()

    return render_template_string(
        TEMPLATES["food.html"],
        today=today_str(),
        now_time=now_time_str(),
        meal_types=MEAL_TYPES,
        entries=entries,
    )


@app.route("/water", methods=["GET", "POST"])
def water():
    db = get_db()
    if request.method == "POST":
        ml = fnum(request.form.get("water_ml"))
        if ml <= 0:
            flash("กรุณากรอกปริมาณน้ำให้ถูกต้อง")
            return redirect(url_for("water"))
        add_entry(
            entry_type="water",
            entry_date=request.form.get("entry_date") or today_str(),
            entry_time=request.form.get("entry_time") or now_time_str(),
            title="ดื่มน้ำ",
            detail=request.form.get("detail", "").strip() or None,
            amount=fnum(request.form.get("amount")),
            water_ml=ml,
        )
        flash("บันทึกการดื่มน้ำเรียบร้อยแล้ว")
        return redirect(url_for("water"))

    t = today_str()
    today_water = db.execute(
        "SELECT COALESCE(SUM(water_ml),0) s FROM entries WHERE entry_type='water' AND entry_date=?", (t,)
    ).fetchone()["s"]
    water_pct = min(round((today_water / WATER_GOAL_ML) * 100), 100) if WATER_GOAL_ML else 0

    entries = db.execute(
        "SELECT * FROM entries WHERE entry_type='water' ORDER BY entry_date DESC, entry_time DESC, id DESC LIMIT 100"
    ).fetchall()

    return render_template_string(
        TEMPLATES["water.html"],
        today=t,
        now_time=now_time_str(),
        today_water=today_water,
        water_goal=WATER_GOAL_ML,
        water_pct=water_pct,
        entries=entries,
    )


@app.route("/water/quick", methods=["POST"])
def quick_water():
    ml = fnum(request.form.get("ml"))
    if ml > 0:
        add_entry(
            entry_type="water",
            entry_date=today_str(),
            entry_time=now_time_str(),
            title="ดื่มน้ำ",
            water_ml=ml,
        )
        flash(f"บันทึกการดื่มน้ำ {int(ml)} มล. เรียบร้อยแล้ว")
    return redirect(url_for("water"))


@app.route("/exercise", methods=["GET", "POST"])
def exercise():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("กรุณากรอกประเภทกิจกรรม")
            return redirect(url_for("exercise"))
        add_entry(
            entry_type="exercise",
            entry_date=request.form.get("entry_date") or today_str(),
            entry_time=request.form.get("entry_time") or now_time_str(),
            title=title,
            detail=request.form.get("detail", "").strip() or None,
            amount=fnum(request.form.get("amount")),
            exercise_minutes=fnum(request.form.get("exercise_minutes")),
            calories=fnum(request.form.get("calories"), None) if request.form.get("calories") else None,
        )
        flash("บันทึกการออกกำลังกายเรียบร้อยแล้ว")
        return redirect(url_for("exercise"))

    entries = db.execute(
        "SELECT * FROM entries WHERE entry_type='exercise' ORDER BY entry_date DESC, entry_time DESC, id DESC LIMIT 100"
    ).fetchall()

    return render_template_string(
        TEMPLATES["exercise.html"],
        today=today_str(),
        now_time=now_time_str(),
        suggestions=EXERCISE_SUGGESTIONS,
        entries=entries,
    )


@app.route("/delete/<int:entry_id>", methods=["POST"])
def delete_entry(entry_id):
    db = get_db()
    db.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    db.commit()
    flash("ลบรายการเรียบร้อยแล้ว")
    next_url = request.form.get("next") or url_for("dashboard")
    return redirect(next_url)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
