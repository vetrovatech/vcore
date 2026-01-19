"""
AWS Lambda handler for VCore Flask application
"""
from app import app
from werkzeug.middleware.proxy_fix import ProxyFix
import awsgi

# Configure app for Lambda/API Gateway
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


def handler(event, context):
    """AWS Lambda handler function"""
    return awsgi.response(app, event, context)

