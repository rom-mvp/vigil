from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import datetime

app = Flask(__name__)
CORS(app)
LOG_STORE = []

@app.route('/')
def home():
    with open('dashboard.html', 'r') as f:
        # Force Localhost usage by clearing API_BASE
        html = f.read().replace(
            'const API_BASE = "https://2mhtzu4ve4.execute-api.us-east-2.amazonaws.com/dev";',
            'const API_BASE = "";' 
        )
    return render_template_string(html)

@app.route('/ingest', methods=['POST'])
def ingest_log():
    data = request.json
    data['ingest_time'] = datetime.datetime.utcnow().isoformat()
    LOG_STORE.append(data)
    return jsonify({"status": "received"}), 200

@app.route('/admin/dashboard', methods=['GET'])
def get_stats():
    blocked = [l for l in LOG_STORE if "BLOCKED" in l.get('status', '')]
    redacted = [l for l in LOG_STORE if l.get('details', {}).get('redacted')]
    return jsonify({
        "role": "CEO",
        "tenant": {"id": "LOCAL_ENTERPRISE", "plan": "enterprise_plus"},
        "stats": {
            "total_requests": len(LOG_STORE),
            "blocked_attacks": len(blocked),
            "redacted_events": len(redacted),
            "unique_tenants": 1
        },
        "recent_logs": sorted(LOG_STORE, key=lambda x: x['timestamp'], reverse=True)[:50]
    })

if __name__ == '__main__':
    print("🚀 Command Center running on http://0.0.0.0:3000")
    app.run(host='0.0.0.0', port=3000)
