# -*- coding: utf-8 -*-
"""
Dashboard App - Flask 应用入口

启动看板服务：
    python -m dashboard.app
    
或：
    python main.py --mode dashboard

访问地址：http://127.0.0.1:5888
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from dashboard.routes import routes_bp


def create_app():
    """创建 Flask 应用实例"""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    )
    
    # 注册蓝图
    app.register_blueprint(routes_bp)
    
    # 配置
    app.config['JSON_AS_ASCII'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    
    return app


def main():
    """启动看板服务"""
    app = create_app()
    
    print("\n" + "="*50)
    print("A股动量趋势系统 v5.0 - 实时看板")
    print("="*50)
    print("访问地址: http://127.0.0.1:5888")
    print("按 Ctrl+C 停止服务")
    print("="*50 + "\n")
    
    # 使用 threaded=True 支持多并发请求
    app.run(host='127.0.0.1', port=5888, debug=False, threaded=True)


if __name__ == '__main__':
    main()
