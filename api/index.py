from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote

app = Flask(__name__)
CORS(app)

BASE_URL = "https://cn.bzmanga.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
    "Referer": "https://cn.bzmanga.com"
}

@app.route('/config')
def get_config():
    return jsonify({
        "包子漫画": {
            "name": "包子漫画",
            "apiUrl": request.url_root.rstrip('/'),
            "detailPath": "/comic/",
            "photoPath": "/chapter/<id>/<chapter>",
            "searchPath": "/search/<keyword>/<page>",
            "type": "bzmanga"
        }
    })

@app.route('/comic/<id>')
def get_comic_detail(id):
    try:
        url = f"{BASE_URL}/comics/{id}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        name = soup.select_one('h1').text.strip() if soup.select_one('h1') else "未知漫画"
        cover = ""
        img = soup.select_one('.comics-cover img, .cover img')
        if img:
            cover = img.get('src') or img.get('data-src') or ""
            if cover.startswith('//'):
                cover = 'https:' + cover
            elif cover.startswith('/'):
                cover = BASE_URL + cover
        
        chapters = []
        for a in soup.select('.comics-chapters a, .chapter-list a'):
            href = a.get('href', '')
            match = re.search(r'/comics/[^/]+/([^/]+)', href)
            if match:
                chapters.append({"id": match.group(1), "name": a.text.strip() or f"第{len(chapters)+1}话"})
        
        return jsonify({
            "item_id": id,
            "name": name,
            "page_count": first_chapter_image_count,
            "cover": cover,
            "tags": [],
            "total_chapters": len(chapters),
            "chapters": chapters[:50]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chapter/<id>/<chapter>')
def get_chapter_images(id, chapter):
    try:
        url = f"{BASE_URL}/comics/{id}/{chapter}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        images = []
        for img in soup.select('.comics-image img, amp-img, img[data-src]'):
            src = img.get('src') or img.get('data-src')
            if src and not src.startswith('data:'):
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = BASE_URL + src
                images.append({"url": f"{src}?width=600&quality=50"})
        
        return jsonify({"title": f"第{chapter}章", "images": images})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/search/<keyword>/<page>')
def search_comics(keyword, page):
    try:
        page_num = int(page) if page.isdigit() else 1
        encoded = quote(keyword)
        url = f"{BASE_URL}/search?q={encoded}&page={page_num}"
        
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        results = []
        for item in soup.select('.comics-card, .search-result-item'):
            a = item.select_one('a')
            if not a:
                continue
            
            href = a.get('href', '')
            comic_id = href.split('/')[-1] if '/' in href else href
            
            title_elem = item.select_one('.title, h3, h4') or a
            title = title_elem.text.strip() if title_elem else ""
            
            img = item.select_one('img')
            cover = img.get('src') or img.get('data-src') if img else ""
            if cover:
                if cover.startswith('//'):
                    cover = 'https:' + cover
                elif cover.startswith('/'):
                    cover = BASE_URL + cover
                cover = f"{cover｝?width=150&quality=50"
            
            if comic_id and title:
                results.append({
                    "comic_id": comic_id, 
                    "title": title[:50], 
                    "cover_url": cover, 
                    "pages": 0
                })
        
        return jsonify({"page": page_num, "has_more": len(results) >= 20, "results": results[:20]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    return jsonify({"status": "腕上漫画-包子漫画API运行中", "docs": "访问 /config 查看配置"})


