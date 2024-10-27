from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import shutil
import os
import base64
from PIL import Image
import logging

VERSION = "2.0.0"

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads_v2'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

log = logging.getLogger('werkzeug')
log.disabled = True

log_filename = 'server.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_filename, 'a', 'utf-8'),
        logging.StreamHandler()
    ]
)

if os.path.exists('key.txt'):
    with open('key.txt', 'r') as f:
        SECRET_KEY = f.read().strip()
else:
    raise FileNotFoundError("key.txt 파일이 존재하지 않습니다.")


LEGACY_UPLOAD_FOLDER = 'uploads' # 1.x.x 데이터 컨버팅

try:
    if os.path.isdir(LEGACY_UPLOAD_FOLDER):
        for filename in os.listdir(LEGACY_UPLOAD_FOLDER):
            if filename.startswith('wallpaper-') and filename.endswith('.png'):
                xuid = filename.split('-')[1].split('.')[0]
                wallpaper_path = os.path.join(LEGACY_UPLOAD_FOLDER, filename)

                with Image.open(wallpaper_path) as skin_image:
                    face = skin_image.crop((8, 8, 16, 16)).resize((8, 8), Image.NEAREST)
                    icon_path = os.path.join(UPLOAD_FOLDER, f"{xuid}_icon.png")
                    face.save(icon_path, "PNG")

                    new_wallpaper_path = os.path.join(UPLOAD_FOLDER, f"{xuid}_wallpaper.png")
                    skin_image.save(new_wallpaper_path, "PNG")
                    logging.info(f"사진 변환 완료: {xuid}")

        shutil.rmtree(LEGACY_UPLOAD_FOLDER)
        logging.info("기존 데이터를 성공적으로 변환했습니다")
except Exception as e:
    logging.error(f"데이터 변환 중 오류 발생: {str(e)}")
    raise


@app.route('/get/<path:file_name>', methods=['GET'])
def get_image(file_name):
    try:
        response = send_from_directory(app.config['UPLOAD_FOLDER'], file_name)
        logging.info(f"[{request.method}] [{request.path}] [{request.remote_addr}] 성공")
        return response
    except Exception as e:
        logging.info(f"[{request.method}] [{request.path}] [{request.remote_addr}] {e}")
        return jsonify({'error': f"파일을 찾을 수 없습니다: {str(e)}"}), 404


@app.route('/create', methods=['POST'])
def create_images():
    data = request.json
    key = data.get("key")
    xuid = data.get("xuid")
    skin_data = data.get("skin")

    if key != SECRET_KEY:
        logging.info("인증되지 않은 접근 시도")
        return jsonify({'error': '올바른 인증 키가 필요합니다.'}), 403
    if not xuid or not skin_data:
        logging.info("xuid 또는 skin 데이터 누락")
        return jsonify({'error': 'xuid 및 skin 데이터가 필요합니다.'}), 400

    try:
        xuid = int(xuid)
        decoded_skin = base64.b64decode(skin_data)
        length = len(decoded_skin)
        if length == 64 * 32 * 4:
            skin_image = Image.frombytes('RGBA', (64, 32), decoded_skin)
        elif length == 64 * 64 * 4:
            skin_image = Image.frombytes('RGBA', (64, 64), decoded_skin)
        elif length == 128 * 64 * 4:
            skin_image = Image.frombytes('RGBA', (128, 64), decoded_skin)
        elif length == 128 * 128 * 4:
            skin_image = Image.frombytes('RGBA', (128, 128), decoded_skin)
        else:
            return jsonify({'error': '잘못된 스킨 데이터 크기입니다.'}), 400
    except Exception as e:
        logging.info(f"스킨 데이터 처리 오류: {str(e)}")
        return jsonify({'error': f"스킨 데이터 처리 오류: {str(e)}"}), 400

    # 기존 파일을 _old로 이름 변경
    for suffix in ["wallpaper", "icon"]:
        original = os.path.join(app.config['UPLOAD_FOLDER'], f"{xuid}_{suffix}.png")
        old = os.path.join(app.config['UPLOAD_FOLDER'], f"{xuid}_{suffix}_old.png")
        if os.path.exists(original):
            if os.path.exists(old):
                os.remove(old)
            os.rename(original, old)

    try:
        # 배경색 설정 및 이미지 생성
        area = skin_image.crop((8, 8, 16, 16))
        r_total = g_total = b_total = 0
        total = 0
        for pixel in area.getdata():
            r, g, b, _ = pixel
            r_total += r
            g_total += g
            b_total += b
            total += 1
        background_color = (
            int((r_total / total + 255) / 2),
            int((g_total / total + 255) / 2),
            int((b_total / total + 255) / 2)
        )

        face = skin_image.crop((8, 8, 16, 16)).resize((222, 222), Image.NEAREST)
        wallpaper = Image.new('RGBA', (854, 480), background_color)
        wallpaper.paste(face, ((854 - 222) // 2, (480 - 222) // 2), face)
        wallpaper_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{xuid}_wallpaper.png")
        wallpaper.save(wallpaper_path, "PNG")

        icon_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{xuid}_icon.png")
        face.resize((8, 8), Image.NEAREST).save(icon_path, "PNG")

        # 성공 시 _old 파일 삭제
        for suffix in ["wallpaper", "icon"]:
            old = os.path.join(app.config['UPLOAD_FOLDER'], f"{xuid}_{suffix}_old.png")
            if os.path.exists(old):
                os.remove(old)

        logging.info(f"이미지 생성 성공: {xuid}")
        return jsonify({'message': '이미지 생성 성공'}), 201

    except Exception as e:
        # 오류 발생 시 _old 파일 복원
        for suffix in ["wallpaper", "icon"]:
            old = os.path.join(app.config['UPLOAD_FOLDER'], f"{xuid}_{suffix}_old.png")
            original = os.path.join(app.config['UPLOAD_FOLDER'], f"{xuid}_{suffix}.png")
            if os.path.exists(old):
                if os.path.exists(original):
                    os.remove(original)
                os.rename(old, original)
        logging.info(f"이미지 생성 중 오류 발생: {str(e)}")
        return jsonify({'error': f"이미지 생성 중 오류가 발생했습니다: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
