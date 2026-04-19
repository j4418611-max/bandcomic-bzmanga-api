# -*- coding: utf-8 -*-
import json
import re
import os
import sys
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote

app = Flask(__name__)
CORS(app)

# ---------- 加载异次元源 JSON ----------
def load_source():
    # 尝试多个可能的路径（Vercel 环境下实际部署在 /var/task）
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "source.json"),
        os.path.join(os.path.dirname(__file__), "source.json"),
        "source.json",
        "/var/task/source.json"
    ]
    for path in possible_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except FileNotFoundError:
            continue
    raise FileNotFoundError("source.json 未找到，请确保文件已上传到项目根目录")

SOURCE = load_source()
BASE_URL = SOURCE.get("bookSourceUrl", "https://cn.bzmanga.com")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL
}

# ---------- 工具函数 ----------
def fetch_html(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

def apply_rule(soup, rule_str, base_url=BASE_URL):
    """执行异次元规则（支持 &&, @属性, ##正则）"""
    if not rule_str or not soup:
        return ""
    rules = rule_str.split("&&")
    for rule in rules:
        rule = rule.strip()
        if not rule:
            continue
        # 分离选择器与属性
        if "@" in rule:
            selector, attr = rule.rsplit("@", 1)
        else:
            selector, attr = rule, "text"
        # 如果选择器为空，直接用 soup
        if selector == "":
            el = soup
        else:
            try:
                el = soup.select_one(selector)
            except:
                el = None
        if not el:
            continue
        # 提取内容
        if attr == "text":
            value = el.get_text(strip=True)
        elif attr in ("href", "src", "data-src", "data-original"):
            value = el.get(attr, "")
        else:
            value = el.get(attr, "")
        if value and attr in ("href", "src"):
            value = urljoin(base_url, value)
        # 简单正则替换
        if "##" in rule_str:
            match = re.search(r"##(.*?)##", rule_str)
            if match:
                value = re.sub(match.group(1), "", value)
        if value:
            return value
    return ""

def parse_list(soup, rule_str, base_url=BASE_URL):
    if not rule_str or not soup:
        return []
    selector = rule_str.split("@")[0].strip()
    try:
        return soup.select(selector)
    except:
        return []

# ---------- API 路由 ----------
@app.route("/")
def index():
    return "腕上漫画 API 运行中"

@app.route("/api/search")
def search():
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return jsonify({"code": -1, "msg": "缺少关键词"})
    search_rule = SOURCE.get("ruleSearch", {})
    search_url = search_rule.get("url", "").replace("${keyword}", quote(keyword))
    soup = fetch_html(search_url)
    if not soup:
        return jsonify({"code": -1, "msg": "搜索请求失败"})
    items = parse_list(soup, search_rule.get("list", ""), BASE_URL)
    result = []
    for item in items:
        comic_id = apply_rule(item, search_rule.get("id", ""), BASE_URL)
        if not comic_id:
            continue
        name = apply_rule(item, search_rule.get("name", ""), BASE_URL)
        cover = apply_rule(item, search_rule.get("cover", ""), BASE_URL)
        author = apply_rule(item, search_rule.get("author", ""), BASE_URL)
        status = apply_rule(item, search_rule.get("status", ""), BASE_URL)
        result.append({
            "id": comic_id,
            "name": name,
            "cover": cover,
            "author": author,
            "status": status
        })
    return jsonify({"code": 0, "data": result})

@app.route("/api/comic/<path:comic_id>")
def comic_detail(comic_id):
    detail_rule = SOURCE.get("ruleBookInfo", {})
    detail_url = detail_rule.get("url", "").replace("${bookId}", comic_id)
    soup = fetch_html(detail_url)
    if not soup:
        return jsonify({"code": -1, "msg": "获取详情失败"})
    name = apply_rule(soup, detail_rule.get("name", ""), BASE_URL)
    cover = apply_rule(soup, detail_rule.get("cover", ""), BASE_URL)
    author = apply_rule(soup, detail_rule.get("author", ""), BASE_URL)
    intro = apply_rule(soup, detail_rule.get("intro", ""), BASE_URL)
    status = apply_rule(soup, detail_rule.get("status", ""), BASE_URL)
    chapter_rule = SOURCE.get("ruleChapter", {})
    chapter_items = parse_list(soup, chapter_rule.get("list", ""), BASE_URL)
    chapters = []
    for item in chapter_items:
        chap_id = apply_rule(item, chapter_rule.get("id", ""), BASE_URL)
        chap_name = apply_rule(item, chapter_rule.get("name", ""), BASE_URL)
        if chap_id:
            chapters.append({"id": chap_id, "name": chap_name or "未知章节"})
    return jsonify({
        "code": 0,
        "data": {
            "id": comic_id,
            "name": name,
            "cover": cover,
            "author": author,
            "intro": intro,
            "status": status,
            "chapters": chapters
        }
    })

@app.route("/api/chapter/<path:chapter_id>")
def chapter_images(chapter_id):
    content_rule = SOURCE.get("ruleContent", {})
    content_url = content_rule.get("url", "").replace("${chapterId}", chapter_id)
    soup = fetch_html(content_url)
    if not soup:
        return jsonify({"code": -1, "msg": "获取章节内容失败"})
    img_rule = content_rule.get("image", "")
    images = []
    if img_rule:
        img_items = parse_list(soup, img_rule.split("@")[0].strip(), BASE_URL)
        for el in img_items:
            img_url = apply_rule(el, img_rule, BASE_URL)
            if img_url:
                images.append(img_url)
        if not images:
            img_url = apply_rule(soup, img_rule, BASE_URL)
            if img_url:
                images = [img_url]
    return jsonify({"code": 0, "data": images})

# Vercel 入口（自动识别 Flask app）
if __name__ == "__main__":
    app.run()