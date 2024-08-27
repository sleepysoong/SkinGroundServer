from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_cors import CORS
import os
import urllib.parse
import logging

VERSION = "1.0.1"

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB 파일 크기 제한

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_secret_key():
    key_file = 'key.txt'
    if os.path.exists(key_file):
        with open(key_file, 'r') as f:
            return f.read().strip()
    else:
        raise FileNotFoundError("key.txt 파일이 존재하지 않습니다.")

SECRET_KEY = load_secret_key()
print("[로그] SECRET KEY를 로딩했습니다..")

@app.route('/upload', methods=['POST'])
def upload_file():
    key = request.form.get('key')  # key 검증
    if key != SECRET_KEY:
        log_request_info(request, is_error=True)
        return jsonify({'error': '올바른 인증 키가 필요합니다.'}), 403
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '파일 이름이 없습니다.'}), 400
    if not file.filename.lower().endswith('.png'):
        return jsonify({'error': 'png 파일만 업로드할 수 있습니다.'}), 400
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    try:
        file.save(file_path)
        file_link = url_for('get_file', filename=urllib.parse.quote(file.filename), _external=True)
        message = {'message': '파일이 업로드되었습니다.', 'filename': file.filename, 'file_link': file_link}
        log_request_info(request, is_error=False, response=message)
        return jsonify(message), 201
    except Exception as e:
        error_message = {'error': f'파일 저장 중 오류가 발생했습니다: {str(e)}'}
        log_request_info(request, is_error=True, response=error_message)
        return jsonify(error_message), 500

@app.route('/uploads/<path:filename>', methods=['GET'])
def get_file(filename):
    key = request.args.get('key')  # query parameter에서 key 검증
    if key != SECRET_KEY:
        log_request_info(request, is_error=True)
        return jsonify({'error': '올바른 인증 키가 필요합니다.'}), 403
    try:
        response = send_from_directory(app.config['UPLOAD_FOLDER'], filename)
        log_request_info(request, is_error=False)
        return response
    except Exception as e:
        error_message = {'error': f'파일을 찾을 수 없습니다: {str(e)}'}
        log_request_info(request, is_error=True, response=error_message)
        return jsonify(error_message), 404


def log_request_info(req, is_error=False, response=None):
    ip = req.remote_addr
    user_agent = req.headers.get('User-Agent')
    method = req.method
    url = req.url
    status = '오류' if is_error else '성공'
    if is_error:
        print(f" @@ 오류 발생: IP={ip}, Method={method}, URL={url}, User-Agent={user_agent}, Response={response}")
        logging.warning( f'올바르지 않은 인증 키가 사용되었습니다: IP={ip}, Method={method}, URL={url}, User-Agent={user_agent}, Response={response}')
        return
    logging.info(f' ## [요청] {status}: IP={ip}, Method={method}, URL={url}, User-Agent={user_agent}, Response={response}')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
