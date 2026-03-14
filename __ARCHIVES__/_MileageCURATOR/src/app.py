import os
import json
from flask import Flask, jsonify, request, render_template
import os
from pathlib import Path
from werkzeug.utils import secure_filename
from src.database import get_db_connection
from src.ingestion import ingest_timeline_data

app = Flask(__name__)

SCHEMA_CONFIG_PATH = 'schema_config.json'

@app.route('/api/schema', methods=['GET', 'POST'])
def handle_schema():
    """Reads or updates the JSON structure mapping for Timeline.json"""
    if request.method == 'POST':
        data = request.json
        with open(SCHEMA_CONFIG_PATH, 'w') as f:
            json.dump(data, f, indent=4)
        return jsonify({"status": "success", "message": "Schema saved!"})

    # GET request: return existing schema if it exists
    if os.path.exists(SCHEMA_CONFIG_PATH):
        with open(SCHEMA_CONFIG_PATH, 'r') as f:
            return jsonify(json.load(f))

    # Default fallback schema if none exists
    return jsonify({
        "activity_segment": "activitySegment",
        "start_location": "startLocation",
        "end_location": "endLocation",
        "latitude": "latitudeE7",
        "longitude": "longitudeE7",
        "distance": "distance"
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    project_name = request.form.get('project_name')

    if file.filename == '' or not project_name:
        return jsonify({'error': 'No selected file or project name'}), 400

    # Create workspace
    safe_name = secure_filename(project_name)
    project_dir = Path('workspaces') / safe_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    file_path = project_dir / 'Timeline.json'
    file.save(file_path)

    # Crunch the data
    try:
        ingest_timeline_data(project_dir)
        return jsonify({'message': f'Workspace {safe_name} created and data ingested!'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    """Serves the main dashboard UI."""
    return render_template('index.html')

@app.route('/api/trips/<project_name>')
def get_trips(project_name):
    """Fetches trips for a specific workspace."""
    project_dir = Path('workspaces') / project_name
    if not (project_dir / 'mileage.db').exists():
        return jsonify({"error": "Project database not found"}), 404

    conn = get_db_connection(project_dir)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM trips ORDER BY date ASC, start_time ASC')
    trips = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(trips)

if __name__ == '__main__':
    print('Starting MileageCURATOR Backend on http://localhost:5000')
    app.run(port=5000, debug=True)