import os
import subprocess
from flask import Flask, request, render_template_string, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)

# アップロードフォルダー（隠しフォルダー）
UPLOAD_FOLDER = ".uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>FFmpeg Web Converter</title>

    <!-- シンプルなボタンスタイル -->
    <style> 
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #f3f4f6;
        margin: 0;
        padding: 30px;
    }

    h1 {
        font-size: 24px;
        margin-bottom: 20px;
        text-align: left;
    }

    form,
    .result {
    background: #ffffff;
    padding: 20px 25px;
    border-radius: 12px;
    box-shadow: 0 3px 12px rgba(0,0,0,0.08);
    margin-bottom: 25px;
    }

    input[type="file"],
    input[type="text"] {
        width: 100%;
        padding: 10px 12px;
        box-sizing: border-box;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        font-size: 14px;
        margin-bottom: 16px;
    }

    button {
        padding: 10px 24px;
        background: #2563eb;
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 15px;
        font-weight: bold;
        cursor: pointer;
    }

    button:hover {
        background: #1e4fd0;
    }

    .button-link {
        display: inline-block;
        padding: 10px 20px;
        background-color: #4CAF50;
        color: white;
        text-decoration: none;
        border-radius: 6px;
        font-weight: bold;
        margin-top: 12px;
    }

    .button-link:hover {
        background-color: #45a049;
    }

    pre {
        background: #1f2937;
        color: #e5e7eb;
        padding: 14px;
        border-radius: 8px;
        max-height: 400px;
        overflow: auto;
        white-space: pre-wrap;
        box-shadow: inset 0 0 4px rgba(0,0,0,0.4);
    }

    .error {
        margin-top: 20px;
        padding: 14px;
        background: #fee2e2;
        color: #991b1b;
        border-radius: 6px;
        white-space: pre-wrap;
    }

    video {
        margin-top: 20px;
        border-radius: 8px;
        box-shadow: 0 3px 12px rgba(0,0,0,0.15);
    }
    </style>
</head>
<body>
    <h1>動画変換アプリケーション</h1>

    <form action="/convert" method="post" enctype="multipart/form-data">
        <p>（１）動画ファイルをアップロードしてください</p>
        <input type="file" name="file"><br><br>

        <p>（２）暗号化の場合のみ復号キーを入力してください</p>
        <input type="text" name="decrypt_key" placeholder="復号キー" size="60"><br><br>
        <p>（３）MP4 に変換する</p>
        <button type="submit">実行</button>
    </form>

    {% if error %}
    <h2>変換結果</h2>
            <div class="error">{{ error }}</div>
    {% endif %}

    {% if download_name %}
    <h2>変換結果</h2>
        <div class="result">
            <video controls width="640">
                <source src="{{ url_for('serve_video', filename=download_name) }}" type="video/mp4">
            </video><br><br>
            <a class="button-link" href="{{ url_for('download', filename=download_name) }}">
                変換されたファイルをダウンロード
            </a>
        </div>
    {% endif %}

    {% if log_text %}
        <h2>ログ</h2>
        <pre style="border:1px solid #ccc; padding:10px; white-space: pre-wrap; max-height:400px; overflow:auto;">
            {{ log_text }}
        </pre>
    {% endif %}

</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML, error=None, log_text=None, download_name=None)

def run_ffmpeg_once(ffmpeg_path, input_path, output_path,
                    decrypt_key=None, extra_opts=None):
    """
    通常:
        decrypt_key が None のときは、今まで通り 1 パターンだけ実行。

    暗号化:
        decrypt_key があるときは、
        - CENC モード（暗号化 MP4 想定）
        - TS + crypto モード（暗号化 TS 想定）
        の両方を試し、どちらか成功したほうを採用する。
    """

    # decrypt_key が無いときは、従来の挙動（シンプルモード）
    if not decrypt_key:
        cmd = [ffmpeg_path, "-y"]

        input_url = input_path

        cmd += ["-i", input_url]

        if extra_opts:
            cmd += extra_opts

        cmd += [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-profile:v", "high",
            "-level:v", "4.1",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path,
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        cmd_str = " ".join(cmd)
        log = f"$ {cmd_str}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}\n"
        return result.returncode, log

    # ここから decrypt_key がある場合（暗号化の可能性あり）

    ext = os.path.splitext(input_path)[1].lower()

    # 拡張子に応じて試行順を決める
    if ext in [".ts", ".m2ts", ".mts", ".m4t"]:
        modes = ["ts_crypto", "cenc"]   # TS 系なら TS 優先
    else:
        modes = ["cenc", "ts_crypto"]   # それ以外は CENC 優先

    full_log = ""
    last_rc = 1

    for idx, mode in enumerate(modes, start=1):
        if mode == "cenc":
            # CENC 暗号化 MP4 想定：普通のパス + -decryption_key
            input_url = input_path
            cmd = [
                ffmpeg_path,
                "-y",
                "-decryption_key", decrypt_key,
                "-i", input_url,
            ]
            mode_label = "CENC モード（暗号化 MP4 想定）"
        else:
            # TS + crypto モード：crypto: 経由で読む
            input_url = f"crypto:{input_path}"
            cmd = [
                ffmpeg_path,
                "-y",
                "-decryption_key", decrypt_key,
                "-i", input_url,
            ]
            mode_label = "TS + crypto モード（暗号化 TS 想定）"

        # リトライ用オプション（2 回目の呼び出し時など）
        if extra_opts:
            cmd += extra_opts

        # 出力設定（共通）
        cmd += [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-profile:v", "high",
            "-level:v", "4.1",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path,
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        cmd_str = " ".join(cmd)
        log = (
            f"=== {idx} 回目の試行: {mode_label} ===\n"
            f"$ {cmd_str}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}\n"
        )

        full_log += ("\n\n" + log)
        last_rc = result.returncode

        # 成功していて、かつ出力ファイルが存在するならそこで終了
        if result.returncode == 0 and os.path.exists(output_path):
            return 0, full_log

    # どちらのモードも失敗した場合
    return last_rc, full_log


@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        return render_template_string(
            HTML,
            error="ファイルが送信されていません。",
            log_text=None,
            download_name=None,
        )

    file = request.files["file"]

    if file.filename == "":
        return render_template_string(
            HTML,
            error="ファイルが選択されていません。",
            log_text=None,
            download_name=None,
        )

    decrypt_key = (request.form.get("decrypt_key") or "").strip() or None

    # 入力ファイル名を安全に
    original_filename = secure_filename(file.filename)
    input_path = os.path.join(app.config["UPLOAD_FOLDER"], original_filename)
    file.save(input_path)

    # 出力ファイル名（被らないように）
    name, _ext = os.path.splitext(original_filename)
    base_output_name = f"{name}_converted"
    output_filename = base_output_name + ".mp4"
    output_path = os.path.join(app.config["UPLOAD_FOLDER"], output_filename)

    counter = 1
    while os.path.exists(output_path):
        output_filename = f"{base_output_name}_{counter}.mp4"
        output_path = os.path.join(app.config["UPLOAD_FOLDER"], output_filename)
        counter += 1

    ffmpeg_path = "/opt/homebrew/bin/ffmpeg"

    # 1回目
    rc1, log1 = run_ffmpeg_once(
        ffmpeg_path=ffmpeg_path,
        input_path=input_path,
        output_path=output_path,
        decrypt_key=decrypt_key,
        extra_opts=None,
    )

    full_log = "=== 1回目の試行 ===\n" + log1

    if rc1 == 0 and os.path.exists(output_path):
        return render_template_string(
            HTML,
            error=None,
            log_text=full_log,
            download_name=output_filename,
        )

    # 2回目（タイムスタンプ調整）
    rc2, log2 = run_ffmpeg_once(
        ffmpeg_path=ffmpeg_path,
        input_path=input_path,
        output_path=output_path,
        decrypt_key=decrypt_key,
        extra_opts=[
            "-fflags", "+genpts",
            "-use_wallclock_as_timestamps", "1",
        ],
    )

    full_log += "\n\n=== 2回目の試行 ===\n" + log2

    if rc2 == 0 and os.path.exists(output_path):
        return render_template_string(
            HTML,
            error=None,
            log_text=full_log,
            download_name=output_filename,
        )

    # 2回失敗
    return render_template_string(
        HTML,
        error="ffmpeg での変換に 2 回失敗しました。（ログを確認してください）",
        log_text=full_log,
        download_name=None,
    )


@app.route("/download/<path:filename>")
def download(filename):
    safe_name = secure_filename(filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    return send_file(file_path, as_attachment=True, attachment_filename=safe_name)


@app.route("/video/<path:filename>")
def serve_video(filename):
    safe_name = secure_filename(filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    return send_file(file_path, mimetype="video/mp4")


if __name__ == "__main__":
    if os.name == "nt":
        os.system("start http://127.0.0.1:5000/")
    else:
        os.system("open http://127.0.0.1:5000/")

    app.run(debug=False)
​
    app.run(debug=False)
