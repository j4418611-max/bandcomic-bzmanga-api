# -*- coding: utf-8 -*-
import sys
import os
import json
sys.stdout.reconfigure(encoding='utf-8')

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
CORS(app)

# ========== 内嵌包子漫画源配置 ==========
SOURCE_JSON = {
    "bookSourceName": "包子漫画",
    "bookSourceUrl": "https://cn.bzmanga.com",
    "bookSourceGroup": "漫画",
    "httpUserAgent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
    "ruleSearchUrl": "https://cn.bzmanga.com/search?q=searchKey&page=searchPage",
    "ruleSearchList": ".comics-card",
    "ruleSearchName": "h3@text",
    "ruleSearchAuthor": "small@text",
    "ruleSearchCoverUrl": "img@src",
    "ruleSearchNoteUrl": "a@href",
    "ruleBookName": "h1@text",
    "ruleCoverUrl": ".comics-cover img@src",
    "ruleChapterList": ".comics-chapters a",
    "ruleChapterName": "@text",
    "ruleChapterUrl": "@href",
    "ruleContentUrl": ".comics-image img, amp-img, img[data-src]"
}

class YiciyuanParser:
    def __init__(self, source):
        self.source = source
        self.base_url = source.get('bookSourceUrl', '').rstrip('/')
        self.headers = {
            'User-Agent': source.get('httpUserAgent', 
                'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36')
        }
    
    def _get_html(self, url):
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.encoding = 'utf-8'
            return BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def _parse_rule(self, soup, rule, default=""):
        if not rule or not soup:
            return default
        
        try:
            if '@' in rule:
                selector, attr = rule.split('@', 1)
                elem = soup.select_one(selector.strip())
                if not elem:
                    return default
                
                if attr == 'text':
                    return elem.get_text(strip=True)
                else:
                    return elem.get(attr, default)
            else:
                elem = soup.select_one(rule)
                return elem.get_text(strip=True) if elem else default
        except Exception as e:
            print(f"Parse error: {e}")
            return default

    def search(self, keyword, page=1):
        try:
            search_url = self.source.get('ruleSearchUrl', '')
            url = search_url.replace('searchKey', keyword).replace('searchPage', str(page))
            if not url.startswith('http'):
                url = self.base_url + url
            
            soup = self._get_html(url)
            if not soup:
                return {"page": page, "has_more": False, "results": []}
            
            list_rule = self.source.get('ruleSearchList', '')
            items = soup.select(list_rule) if list_rule else []
            
            results = []
            for item in items:
                href = self._parse_rule(item, self.source.get('ruleSearchNoteUrl', 'a@href'), "")
                
                comic_id = ""
                if href:
                    for p in [r'/comics/(\d+)', r'/comic/(\d+)', r'/(\d+)\.html']:
                        m = re.search(p, href)
                        if m:
                            comic_id = m.group(1)
                            break
                
                title = self._parse_rule(item, self.source.get('ruleSearchName', 'h3@text'), "未知")
                
                cover = self._parse_rule(item, self.source.get('ruleSearchCoverUrl', 'img@src'), "")
                if cover.startswith('//'):
                    cover = 'https:' + cover
                elif cover.startswith('/'):
                    cover = self.base_url + cover
                
                if comic_id and title:
                    results.append({
                        "comic_id": comic_id,
                        "title": title[:50],
                        "cover_url": cover,
                        "pages": 0
                    })
            
            return {
                "page": page,
                "has_more": len(results) >= 20,
                "results": results[:20]
            }
        except Exception as e:
            print(f"Search error: {e}")
            return {"page": page, "has_more": False, "results": [], "error": str(e)}

    def get_detail(self, comic_id):
        try:
            urls = [
                f"{self.base_url}/comics/{comic_id}.html",
                f"{self.base_url}/comic/{comic_id}",
                f"{self.base_url}/comics/{comic_id}"
            ]
            
            soup = None
            for url in urls:
                soup = self._get_html(url)
                if soup:
                    break
            
            if not soup:
                return None
            
            name = self._parse_rule(soup, self.source.get('ruleBookName', 'h1@text'), "未知漫画")
            
            cover = self._parse_rule(soup, self.source.get('ruleCoverUrl', '.comics-cover img@src'), "")
            if cover.startswith('//'):
                cover = 'https:' + cover
            elif cover.startswith('/'):
                cover = self.base_url + cover
            
            chapter_rule = self.source.get('ruleChapterList', '.comics-chapters a')
            elems = soup.select(chapter_rule) if chapter_rule else []
            
            chapters = []
            for elem in elems:
                href = self._parse_rule(elem, self.source.get('ruleChapterUrl', 'a@href'), "")
                
                chapter_id = ""
                if href:
                    m = re.search(r'/(\d+)(?:\.html)?$', href)
                    if m:
                        chapter_id = m.group(1)
                
                ch_name = self._parse_rule(elem, self.source.get('ruleChapterName', 'a@text'), f"第{len(chapters)+1}话")
                
                if chapter_id:
                    chapters.append({
                        "id": chapter_id,
                        "name": ch_name
                    })
            
            return {
                "item_id": comic_id,
                "name": name,
                "cover": cover,
                "chapters": chapters[:50]
            }
        except Exception as e:
            print(f"Detail error: {e}")
            return None

    def get_images(self, comic_id, chapter_id):
        try:
            urls = [
                f"{self.base_url}/comics/{comic_id}/{chapter_id}",
                f"{self.base_url}/comic/{comic_id}/{chapter_id}.html",
                f"{self.base_url}/chapter/{comic_id}/{chapter_id}"
            ]
            
            soup = None
            for url in urls:
                soup = self._get_html(url)
                if soup:
                    break
            
            if not soup:
                return {"title": f"第{chapter_id}章", "images": []}
            
            content_rule = self.source.get('ruleContentUrl', '.comics-image img, amp-img, img[data-src]')
            elems = soup.select(content_rule) if content_rule else []
            
            images = []
            for elem in elems:
                src = elem.get('src') or elem.get('data-src') or elem.get('data-original')
                if src and not src.startswith('data:'):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = self.base_url + src
                    
                    images.append({"url": src})
            
            return {
                "title": f"第{chapter_id}章",
                "images": images
            }
        except Exception as e:
            print(f"Images error: {e}")
            return {"title": f"第{chapter_id}章", "images": [], "error": str(e)}

parser = YiciyuanParser(SOURCE_JSON)

@app.route('/config')
def get_config():
    return jsonify({
        "name": SOURCE_JSON.get('bookSourceName', '漫画源'),
        "apiUrl": request.url_root.rstrip('/'),
        "detailPath": "/comic/",
        "photoPath": "/chapter/<id>/<chapter>",
        "searchPath": "/search/<keyword>/<page>",
        "type": "yiciyuan"
    })

@app.route('/search/<keyword>/<page>')
def search(keyword, page):
    result = parser.search(keyword, int(page))
    return jsonify(result)

@app.route('/comic/<id>')
def comic_detail(id):
    result = parser.get_detail(id)
    if not result:
        return jsonify({"error": "not found"}), 404
    return jsonify(result)

@app.route('/chapter/<id>/<chapter>')
def chapter_images(id, chapter):
    result = parser.get_images(id, chapter)
    return jsonify(result)

@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "source": SOURCE_JSON.get('bookSourceName'),
        "endpoints": ["/config", "/search/<keyword>/<page>", "/comic/<id>", "/chapter/<id>/<chapter>"]
    })

if __name__ == '__main__':
    app.run(debug=True)
