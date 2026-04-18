# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from flask import Flask, jsonify, request
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)

with open('source.json', 'r', encoding='utf-8') as f:
    SOURCE_JSON = json.load(f)

from parser import YiciyuanParser
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
    try:
        return jsonify(parser.search(keyword, int(page)))
    except Exception as e:
        return jsonify({"error": str(e), "results": []}), 500

@app.route('/comic/<id>')
def comic_detail(id):
    try:
        result = parser.get_detail(id)
        if not result:
            return jsonify({"error": "未找到"}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chapter/<id>/<chapter>')
def chapter_images(id, chapter):
    try:
        return jsonify(parser.get_images(id, chapter))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    return jsonify({
        "status": f"{SOURCE_JSON.get('bookSourceName')} API运行中",
        "docs": "/config"
    })

if __name__ == '__main__':
    app.run(debug=True)
