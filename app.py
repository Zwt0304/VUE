# metacog_backend/app.py
# --------------------------------------------------------------
# 说明：
#   1. 保留你原有的 /api/analyze 逻辑（已合并在下方）
#   2. 保留聊天蓝图 chat_bp
#   3. 新增 /api/face_login，依赖 face_recognition_module.py
# --------------------------------------------------------------

import os
import numpy as np
import pandas as pd
import joblib
from flask import Flask, request, jsonify
from flask_cors import CORS
from sklearn.preprocessing import MinMaxScaler

# ---------- Flask & CORS 初始化 ----------
app = Flask(__name__)
CORS(app)

# ---------- 引入聊天 Blueprint ----------
from chat_api import bp as chat_bp
app.register_blueprint(chat_bp)

# ---------- 引入人脸识别工具 ----------
from face_recognition_module import match_face_from_base64

# ---------- 模型及列配置 ----------
BASE_DIR = os.path.dirname(__file__)
MODEL_DIR = os.path.join(BASE_DIR, "models")

behavior_freq_cols = ['CEM','CLT','VC','RA','DI','TC','PM','LR']
behavior_seq_cols = [
    'CEM→CEM','CLT→VC','CLT→TC','CLT→LR',
    'VC→CLT','VC→VC','RA→CEM','RA→RA',
    'DI→DI','DI→LR','TC→TC','TC→PM',
    'PM→VC','PM→TC','PM→PM','LR→LR'
]
emotion_cols   = ['Affect','PosEmo']
cognition_cols = ['CogMech','Insight']

column_name_map = {
    'CEM':'明确评价方式','CLT':'明确学习任务','VC':'查看课程','RA':'资源访问',
    'DI':'讨论互动','TC':'任务完成','PM':'过程监控','LR':'学习反思',
    'Affect':'情感体验','PosEmo':'积极情绪',
    'CogMech':'认知能力','Insight':'反省能力'
}

# ---------- NumPy → Python 原生 ----------
def to_py(x):
    return x.item() if isinstance(x, np.generic) else x

# ---------- 选择模型 ----------
def select_model(cols):
    keys = []
    if any(c in cols for c in behavior_freq_cols): keys.append('freq')
    if any(c in cols for c in behavior_seq_cols): keys.append('seq')
    if any(c in cols for c in emotion_cols):      keys.append('sentiment')
    if any(c in cols for c in cognition_cols):    keys.append('cognitive')
    path = os.path.join(MODEL_DIR, '_'.join(keys) + '.joblib')
    return path if os.path.exists(path) else None

# ---------- 归一化 ----------
def norm(vals):
    arr = np.array(vals, dtype=float)
    if arr.ptp() == 0:
        return [0.5]*len(arr)
    return MinMaxScaler().fit_transform(arr.reshape(-1,1)).flatten().tolist()

# ---------- 人脸登录接口 ----------
@app.route("/api/face_login", methods=["POST"])
def face_login():
    """
    前端发送 JSON: { "image": "<base64_without_prefix>" }
    成功返回 { success: True, username: .., role: 'student'|'teacher' }
    """
    data = request.get_json(silent=True) or {}
    img_b64 = data.get("image", "")
    if not img_b64:
        return jsonify({"success": False, "msg": "未接收到图像"}), 400

    match = match_face_from_base64(img_b64)
    if match:
        return jsonify({"success": True, **match})
    return jsonify({"success": False, "msg": "人脸识别失败"}), 401

# ---------- 分析接口 ----------
@app.route('/api/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files:
        return jsonify({'error':'未检测到上传文件'}), 400
    try:
        df = pd.read_excel(request.files['file'], engine='openpyxl')
    except Exception as e:
        return jsonify({'error':f'Excel读取失败：{e}'}), 500

    # 归一化开关
    norm_flag = str(request.form.get('normalize','')).lower() in ('true','1','yes')

    # 选择模型
    model_path = select_model(df.columns.tolist())
    if not model_path:
        return jsonify({'error':'无法匹配模型文件'}), 400
    model = joblib.load(model_path)

    feats = [c for c in df.columns
             if c in behavior_freq_cols + behavior_seq_cols + emotion_cols + cognition_cols]
    df['预测元认知能力'] = model.predict(df[feats])

    # ---------- 教师端 ----------
    if all(c in df.columns for c in ('姓名','性别','年级')):
        df[['姓名','性别','年级']] = df[['姓名','性别','年级']].fillna('未知')

        students = [{
            '姓名': to_py(r['姓名']),
            '性别': to_py(r['性别']),
            '年级': to_py(r['年级']),
            '预测元认知能力': to_py(r['预测元认知能力'])
        } for _, r in df.iterrows()]

        gender_stat = { to_py(k): to_py(v) for k,v in df['性别'].value_counts().items() }
        grade_stat  = { to_py(k): to_py(v) for k,v in df['年级'].value_counts().items() }
        features    = df.applymap(to_py).to_dict(orient='list')

        return jsonify({
            'role': 'teacher',
            'students': students,
            'gender_stat': gender_stat,
            'grade_stat': grade_stat,
            'features': features,
            'columns': [to_py(c) for c in df.columns]
        })

    # ---------- 学生端 ----------
    row = df.iloc[0]
    freq = [row[c] for c in behavior_freq_cols if c in df.columns]
    seq  = [row[c] for c in behavior_seq_cols if c in df.columns]
    emo  = [row[c] for c in emotion_cols   if c in df.columns]
    cog  = [row[c] for c in cognition_cols if c in df.columns]
    if norm_flag:
        freq, seq, emo, cog = map(norm, (freq, seq, emo, cog))

    def pair(cols, vals, use_map=True):
        res = []
        for c, v in zip(cols, vals):
            if c in df.columns:
                name = column_name_map[c] if use_map else c
                res.append([name, to_py(v)])
        return res

    return jsonify({
        'role': 'student',
        'ability': to_py(row['预测元认知能力']),
        'normalize': norm_flag,
        'behavior_freq': pair(behavior_freq_cols, freq),
        'behavior_seq': pair(behavior_seq_cols, seq, False),
        'emotion':      pair(emotion_cols, emo),
        'cognition':    pair(cognition_cols, cog)
    })

# ---------- 根路由 ----------
@app.route('/')
def index():
    return 'METACOG Flask 后端运行中'

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
