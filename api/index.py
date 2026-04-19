# -*- coding: utf-8 -*-
import json
import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote

app = Flask(__name__)
CORS(app)

# ------------------ 加载异次元源 JSON ------------------
SOURCE_FILE = "source.json"          # 把下载的 819.json 放在项目根目录
SOURCE_URL = "https://www.yckceo.com/yiciyuan/tuyuan/json/id/819.json"

def load_source():
    # 尝试多个可能的路径（适配 Vercel 环境）
    possible_paths = [
        "source.json",                     # 项目根目录
        os.path.join(os.path.dirname(__file__), "..", "source.json"),
        "/var/task/source.json",           # Vercel 实际部署目录
    ]
    for path in possible_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"成功加载源文件: {path}")
                return data
        except FileNotFoundError:
            continue
    # 如果都没找到，抛出明确的错误
    raise FileNotFoundError("source.json 未找到，请确保已将其添加到项目根目录并提交到 Git")

SOURCE = load_source()
BASE_URL = SOURCE.get("bookSourceUrl", "https://cn.bzmanga.com")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": BASE_URL
}

# ------------------ 规则解析工具 ------------------
def fetch_html(url):
    """获取页面 BeautifulSoup 对象"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

def apply_rule(soup, rule_str, base_url=BASE_URL):
    """
    执行异次元规则字符串（简化版，支持常用语法）
    支持：
      - css选择器 如 ".class a@href"
      - 多个规则用 && 分隔（取第一个非空）
      - @text / @href / @src 等属性
      - ## 正则替换
    """
    if not rule_str or not soup:
        return ""

    # 按 && 分割，依次尝试
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

        # 如果选择器为空，直接用 soup 本身
        if selector == "" or selector == "text":
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

        # 处理相对路径
        if value and attr in ("href", "src"):
            value = urljoin(base_url, value)

        # 正则替换（如果规则中有 ## 部分）
        if "##" in rule_str:
            # 原规则整体可能包含替换，简化处理：提取正则部分
            match = re.search(r"##(.*?)##", rule_str)
            if match:
                pattern = match.group(1)
                # 这里只支持简单替换，可按需扩展
                value = re.sub(pattern, "", value)

        if value:
            return value

    return ""

def parse_list(soup, rule_str, base_url=BASE_URL):
    """解析列表规则，返回元素列表"""
    if not rule_str or not soup:
        return []

    # 例如： ".list li"
    selector = rule_str.split("@")[0].strip()
    try:
        return soup.select(selector)
    except:
        return []

# ------------------ API 路由 ------------------
@app.route("/api/search")
def search():
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return jsonify({"code": -1, "msg": "缺少关键词"})

    # 从源规则中获取搜索 URL 构造方式
    search_rule = SOURCE.get("ruleSearch", {})
    search_url = search_rule.get("url", "").replace("${keyword}", quote(keyword))

    soup = fetch_html(search_url)
    if not soup:
        return jsonify({"code": -1, "msg": "搜索请求失败"})

    # 获取列表元素
    list_rule = search_rule.get("list", "")
    items = parse_list(soup, list_rule, BASE_URL)

    result = []
    for item in items:
        comic_id = apply_rule(item, search_rule.get("id", ""), BASE_URL)
        name = apply_rule(item, search_rule.get("name", ""), BASE_URL)
        cover = apply_rule(item, search_rule.get("cover", ""), BASE_URL)
        author = apply_rule(item, search_rule.get("author", ""), BASE_URL)
        status = apply_rule(item, search_rule.get("status", ""), BASE_URL)

        if not comic_id:
            continue

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
    # 根据 comic_id 构造详情页 URL
    detail_rule = SOURCE.get("ruleBookInfo", {})
    detail_url = detail_rule.get("url", "").replace("${bookId}", comic_id)

    soup = fetch_html(detail_url)
    if not soup:
        return jsonify({"code": -1, "msg": "获取详情失败"})

    # 提取基本信息
    name = apply_rule(soup, detail_rule.get("name", ""), BASE_URL)
    cover = apply_rule(soup, detail_rule.get("cover", ""), BASE_URL)
    author = apply_rule(soup, detail_rule.get("author", ""), BASE_URL)
    intro = apply_rule(soup, detail_rule.get("intro", ""), BASE_URL)
    status = apply_rule(soup, detail_rule.get("status", ""), BASE_URL)

    # 提取章节列表
    chapter_rule = SOURCE.get("ruleChapter", {})
    chapter_list_rule = chapter_rule.get("list", "")
    chapter_items = parse_list(soup, chapter_list_rule, BASE_URL)

    chapters = []
    for idx, item in enumerate(chapter_items):
        chap_id = apply_rule(item, chapter_rule.get("id", ""), BASE_URL)
        chap_name = apply_rule(item, chapter_rule.get("name", ""), BASE_URL)
        if chap_id:
            chapters.append({
                "id": chap_id,
                "name": chap_name or f"第{idx+1}话"
            })

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
    # 章节图片页
    content_rule = SOURCE.get("ruleContent", {})
    content_url = content_rule.get("url", "").replace("${chapterId}", chapter_id)

    soup = fetch_html(content_url)
    if not soup:
        return jsonify({"code": -1, "msg": "获取章节内容失败"})

    # 图片列表规则
    img_rule = content_rule.get("image", "")
    if img_rule:
        # 可能是单张或列表，先尝试列表
        img_items = parse_list(soup, img_rule.split("@")[0].strip(), BASE_URL)
        images = []
        for el in img_items:
            img_url = apply_rule(el, img_rule, BASE_URL)
            if img_url:
                images.append(img_url)
        if not images:
            # 可能是直接取属性
            img_url = apply_rule(soup, img_rule, BASE_URL)
            if img_url:
                images = [img_url]
    else:
        images = []

    # 有时图片地址是 data-src 之类，已在 apply_rule 中处理

    return jsonify({"code": 0, "data": images})

@app.route("/")
def index():
    return "腕上漫画 API 运行中，请使用 /api/search、/api/comic/xxx、/api/chapter/xxx"

# Vercel 入口
def handler(environ, start_response):
    return app(environ, start_response)