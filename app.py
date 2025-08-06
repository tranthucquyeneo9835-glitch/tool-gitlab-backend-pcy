import traceback
from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

LOG_FILE = "upload.log"
ERROR_LOG_FILE = "error.log"

def log_error(msg):
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

@app.errorhandler(Exception)
def handle_exception(e):
    error_msg = f"Exception: {str(e)}\n{traceback.format_exc()}"
    log_error(error_msg)
    return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/")
def home():
    return "✅ GitLab Multi Uploader with Slug is running."

@app.route("/upload", methods=["POST"])
def upload():
    try:
        tokens = request.form.getlist("token")
        group_ids = request.form.getlist("group_id")
        slug_prefix = request.form.get("slug")
        files = request.files.getlist("files")

        if not tokens or not group_ids or not slug_prefix or not files:
            return jsonify({"error": "Missing token, group_id, slug or files"}), 400

        if len(tokens) != len(group_ids):
            return jsonify({"error": "Number of tokens and group IDs must match"}), 400

        open(LOG_FILE, "w", encoding="utf-8").close()  # Clear log

        results = []
        files_sorted = sorted(files, key=lambda f: f.filename)

        slug_counter = 1

        for acc_index, (token, group_id) in enumerate(zip(tokens, group_ids), start=1):
            headers = {"PRIVATE-TOKEN": token}
            print(f"🔐 Processing account {acc_index}...")

            for file in files_sorted:
                original_filename = os.path.basename(file.filename)
                project_name = os.path.splitext(original_filename)[0]
                slug = f"{slug_prefix}{slug_counter}"
                slug_counter += 1

                try:
                    content = file.read().decode("utf-8")
                    file.stream.seek(0)  # Reset pointer for next token if reused
                except Exception as e:
                    log_error(f"❌ Error reading file {original_filename}: {e}")
                    continue

                # Create project
                create_url = "https://gitlab.com/api/v4/projects"
                payload = {
                    "name": project_name,
                    "path": slug,
                    "namespace_id": group_id,
                    "initialize_with_readme": True,
                    "visibility": "public"
                }

                try:
                    r = requests.post(create_url, headers=headers, json=payload, timeout=15)
                    r.raise_for_status()
                    r_json = r.json()
                except requests.RequestException as e:
                    log_error(f"❌ Failed to create project {project_name}: {e} - {getattr(e.response, 'text', '')}")
                    continue

                project_id = r_json.get("id")
                web_url = r_json.get("web_url", f"https://gitlab.com/{slug}")

                with open(LOG_FILE, "a", encoding="utf-8") as logf:
                    logf.write(f"{web_url}\n")

                # Update README
                update_url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/files/README.md"
                update_payload = {
                    "branch": "main",
                    "content": content,
                    "commit_message": "Update README.md from uploaded file"
                }

                try:
                    r2 = requests.put(update_url, headers=headers, json=update_payload, timeout=15)
                    r2.raise_for_status()
                except requests.RequestException as e:
                    log_error(f"❌ Failed to update README {project_name}: {e} - {getattr(e.response, 'text', '')}")
                    continue

                results.append({
                    "account": acc_index,
                    "file": original_filename,
                    "slug": slug,
                    "url": web_url
                })

        return jsonify({
            "status": "✅ Upload completed",
            "projects": results
        })

    except Exception as e:
        log_error(f"❌ Upload system error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🚀 Flask server running on port", port)
    app.run(host="0.0.0.0", port=port, debug=False)
