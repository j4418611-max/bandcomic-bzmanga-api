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

# ========== 配置加载 ==========
def load_source():
    """加载书源配置，兼容本地和 Vercel 环境"""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'source.json'),
        os.path.join(os.path.dirname(__file__), 'source.json'),
        os.path.join(os.getcwd(), 'source.json'),
        '/var/task/source.json',
        '/var/task/api/source.json',
    ]
    
    for path in possible_paths:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"尝试加载 {path} 失败: {e}")
            continue
    
    # 如果文件找不到，返回硬编码的包子漫画配置（作为fallback）
    print("警告：使用内置默认配置")
    return get_default_source()

def get_default_source():
    """内置默认书源配置（包子漫画）"""
    return {
        "bookSourceUrl": "https://cn.bzmanga.com",
        "httpUserAgent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
        "ruleSearch": {
            "url": "https://cn.bzmanga.com/search?q=searchKey",
            "list": ".comics-card",
            "name": "h3@text",
            "author": "small@text",
            "cover": "amp-img[noloading^=\"\"]@src@Header:{Referer:host}",
            "status": ".tags@text|.tab@text",
            "id": "a@href"
        },
        "ruleBookInfo": {
            "url": "https://cn.bzmanga.com/comics/${bookId}",
            "name": ".comics-detail__title@text",
            "author": ".comics-detail__author@text",
            "cover": ".comics-detail__cover amp-img@src",
            "intro": ".comics-detail__desc@html",
            "status": ".tag-list@span@text",
            "chapterList": ".l-box@.pure-g!0@.comics-chapters||.pure-g@.comics-chapters",
            "chapterName": "a@text\\n@js:\\na = \"\" + result",
            "chapterUrl": "a@href"
        },
        "ruleContent": {
            "url": "https://cn.bzmanga.com/chapter/${chapterId}",
            "image": ".comic-contain amp-img@data-src||.comic-contain amp-img@src"
        }
    }

# 加载配置
SOURCE = load_source()
BASE_URL = SOURCE.get("bookSourceUrl", "https://cn.bzmanga.com")
HEADERS = {
    "User-Agent": SOURCE.get("httpUserAgent", 
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
    "Referer": BASE_URL
}

# ========== 工具函数 ==========
def fetch_html(url):
    """获取网页并解析为 BeautifulSoup"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        print(f"请求失败 [{url}]: {e}")
        return None

def apply_rule(element, rule_str, base_url=BASE_URL):
    """应用书源规则提取数据"""
    if not rule_str or not element:
        return ""
    
    # 处理 @js: 规则（简单实现）
    if "@js:" in rule_str:
        # 腕上漫画通常不需要复杂js，这里简化处理
        rule_str = rule_str.split("@js:")[0].strip()
    
    # 分离选择器和属性
    if "@" in rule_str:
        parts = rule_str.rsplit("@", 1)
        selector = parts[0].strip()
        attr = parts[1].strip()
    else:
        selector = rule_str
        attr = "text"
    
    # 查找元素
    try:
        if selector == "":
            el = element
        else:
            # 处理 || 多选择器
            if "||" in selector:
                selectors = [s.strip() for s in selector.split("||")]
                el = None
                for sel in selectors:
                    el = element.select_one(sel)
                    if el:
                        break
            else:
                el = element.select_one(selector)
    except Exception as e:
        print(f"选择器错误: {selector}, {e}")
        return ""
    
    if not el:
        return ""
    
    # 提取内容
    if attr == "text":
        value = el.get_text(strip=True)
    elif attr in ("href", "src", "data-src", "data-original"):
        value = el.get(attr, "")
    else:
        value = el.get(attr, "")
    
    # 补全URL
    if value and attr in ("href", "src", "data-src"):
        if value.startswith("//"):
            value = "https:" + value
        elif value.startswith("/"):
            value = urljoin(base_url, value)
        elif not value.startswith("http"):
            value = urljoin(base_url, value)
    
    return value

def parse_list(soup, rule_str):
    """解析列表"""
    if not rule_str or not soup:
        return []
    
    # 处理 || 多选择器
    if "||" in rule_str:
        selectors = [s.strip() for s in rule_str.split("||")]
        for sel in selectors:
            try:
                result = soup.select(sel)
                if result:
                    return result
            except:
                continue
        return []
    else:
        try:
            return soup.select(rule_str)
        except:
            return []

# ========== API 路由 ==========
@app.route("/")
def index():
    return jsonify({
        "code": 0,
        "msg": "腕上漫画API运行中",
        "source": SOURCE.get("bookSourceName", "包子漫画"),
        "base_url": BASE_URL
    })

@app.route("/api/search")
def search():
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return jsonify({"code": -1, "msg": "缺少关键词"}), 400
    
    search_rule = SOURCE.get("ruleSearch", {})
    search_url = search_rule.get("url", "").replace("searchKey", quote(keyword))
    
    # 兼容不同占位符
    search_url = search_url.replace("${key}", quote(keyword))
    
    soup = fetch_html(search_url)
    if not soup:
        return jsonify({"code": -1, "msg": "搜索请求失败"}), 500
    
    items = parse_list(soup, search_rule.get("list", ""))
    result = []
    
    for item in items:
        comic_id = apply_rule(item, search_rule.get("id", ""))
        if not comic_id:
            continue
            
        # 提取ID（从URL中提取）
        if "/" in comic_id:
            comic_id = comic_id.rstrip("/").split("/")[-1]
        
        name = apply_rule(item, search_rule.get("name", ""))
        cover = apply_rule(item, search_rule.get("cover", ""))
        author = apply_rule(item, search_rule.get("author", ""))
        status = apply_rule(item, search_rule.get("status", ""))
        
        result.append({
            "id": comic_id,
            "name": name,
            "cover": cover,
            "author": author,
            "status": status
        })
    
    return jsonify({
        "code": 0,
        "data": result,
        "total": len(result)
    })

@app.route("/api/comic/<path:comic_id>")
def comic_detail(comic_id):
    detail_rule = SOURCE.get("ruleBookInfo", {})
    detail_url = detail_rule.get("url", "").replace("${bookId}", comic_id)
    detail_url = detail_url.replace("bookId", comic_id)
    
    soup = fetch_html(detail_url)
    if not soup:
        return jsonify({"code": -1, "msg": "获取详情失败"}), 500
    
    name = apply_rule(soup, detail_rule.get("name", ""))
    cover = apply_rule(soup, detail_rule.get("cover", ""))
    author = apply_rule(soup, detail_rule.get("author", ""))
    intro = apply_rule(soup, detail_rule.get("intro", ""))
    status = apply_rule(soup, detail_rule.get("status", ""))
    
    # 解析章节列表
    chapter_rule = detail_rule
    chapter_items = parse_list(soup, chapter_rule.get("chapterList", ""))
    chapters = []
    
    for item in chapter_items:
        chap_id = apply_rule(item, chapter_rule.get("chapterUrl", ""))
        if chap_id:
            # 提取章节ID
            if "/" in chap_id:
                chap_id = chap_id.rstrip("/").split("/")[-1]
            
            chap_name = apply_rule(item, chapter_rule.get("chapterName", ""))
            chapters.append({
                "id": chap_id,
                "name": chap_name or "未知章节"
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
    content_rule = SOURCE.get("ruleContent", {})
    content_url = content_rule.get("url", "").replace("${chapterId}", chapter_id)
    content_url = content_url.replace("chapterId", chapter_id)
    
    soup = fetch_html(content_url)
    if not soup:
        return jsonify({"code": -1, "msg": "获取章节内容失败"}), 500
    
    img_rule = content_rule.get("image", "")
    images = []
    
    if img_rule:
        # 处理 || 多属性
        img_attrs = [a.strip() for a in img_rule.split("||")]
        
        for attr in img_attrs:
            if "@" in attr:
                selector = attr.rsplit("@", 1)[0].strip()
                img_attr = attr.rsplit("@", 1)[1].strip()
            else:
                selector = attr
                img_attr = "src"
            
            try:
                img_items = soup.select(selector)
                for el in img_items:
                    img_url = el.get(img_attr, "")
                    if img_url:
                        # 处理相对路径
                        if img_url.startswith("//"):
                            img_url = "https:" + img_url
                        elif img_url.startswith("/"):
                            img_url = urljoin(BASE_URL, img_url)
                        elif not img_url.startswith("http"):
                            img_url = urljoin(BASE_URL, img_url)
                        
                        if img_url not in images:
                            images.append(img_url)
            except Exception as e:
                print(f"解析图片失败: {e}")
                continue
    
    return jsonify({
        "code": 0,
        "data": images
    })

# Vercel 入口
if __name__ == "__main__":
    app.run(debug=True)
