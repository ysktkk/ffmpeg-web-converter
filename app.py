import os
import subprocess
from flask import Flask, request, render_template_string, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ベースディレクトリ（この app.py がある場所）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# アップロードフォルダー（隠しフォルダー）
UPLOAD_FOLDER = os.path.join(BASE_DIR, ".uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ★ ffmpeg のパス（OSごとに切り替え）
if os.name == "nt":
    # Windows のとき → 将来 exe にするときは bin\ffmpeg.exe を使うイメージ
    FFMPEG_PATH = os.path.join(BASE_DIR, "bin", "ffmpeg.exe")
else:
    # 今のあなたの Mac 環境
    FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>FFmpeg Web Converter</title>
</head>
<body>
    <h1>動画変換アプリケーション</h1>

    <form action="{{ url_for('convert') }}" method="post" enctype="multipart/form-data">
        <p>（１）動画ファイルをアップロードしてください</p>
        <input type="file" name="file"><br><br>
        <p>（２）出力拡張子を指定して下さい</p>
        <input type="text" name="style" placeholder="（例: mp4, avi, webm）" size="50"><br><br>
        <p>（３）実行する</p>
        <button type="submit">変換</button>
    </form>

    {% if error %}
        <p style="color:red;">{{ error }}</p>
    {% endif %}

    {% if log_text %}
        <h2>ffmpeg ログ</h2>
        <pre style="border:1px solid #ccc; padding:10px; white-space: pre-wrap; max-height:400px; overflow:auto;">
{{ log_text }}
        </pre>
    {% endif %}

    {% if download_name %}
        <p>
            <a href="{{ url_for('download', filename=download_name) }}">
                変換されたファイルをダウンロード
            </a>
        </p>
    {% endif %}
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML, error=None, log_text=None, download_name=None)

@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        return render_template_string(HTML, error="ファイルが送信されていません。", log_text=None, download_name=None)

    file = request.files["file"]

    if file.filename == "":
        return render_template_string(HTML, error="ファイルが選択されていません。", log_text=None, download_name=None)

    style = (request.form.get("style") or "mp4").strip()

    filename = secure_filename(file.filename)
    input_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(input_path)

    output_filename = f"output.{style}"
    output_path = os.path.join(app.config["UPLOAD_FOLDER"], output_filename)

    if os.path.exists(output_path):
        os.remove(output_path)

    # ここで FFMPEG_PATH を使う
    result = subprocess.run(
        [
            FFMPEG_PATH,
            "-y",
            "-i", input_path,
            output_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    log_text = (result.stdout or "") + "\n" + (result.stderr or "")

    if result.returncode != 0:
        return render_template_string(
            HTML,
            error="ffmpeg エラーが発生しました。",
            log_text=log_text,
            download_name=None,
        )

    return render_template_string(
        HTML,
        error=None,
        log_text=log_text,
        download_name=output_filename,
    )

@app.route("/download/<path:filename>")
def download(filename):
    safe_name = secure_filename(filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    return send_file(file_path, as_attachment=True, attachment_filename=safe_name)

# ★ ここから自動ブラウザ起動
if __name__ == "__main__":
    import threading
    import webbrowser

    def open_browser():
        webbrowser.open("http://127.0.0.1:5000")

    # ★ 本当に動いている側のプロセスだけブラウザを開く
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1, open_browser).start()

    app.run(debug=True)