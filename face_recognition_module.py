import face_recognition
import os
import numpy as np
from PIL import Image
from io import BytesIO
import base64

# 图片库路径（你可统一将照片存放于 public/assets/faces/student/ 和 teacher/ 目录）
PHOTO_DIR = 'faces'  # 例如 faces/student/xxx.jpg

def load_known_faces():
    known_encodings = []
    known_users = []

    # 遍历 student/teacher 目录
    for role in ['student', 'teacher']:
        dir_path = os.path.join(PHOTO_DIR, role)
        if not os.path.exists(dir_path):
            continue
        for filename in os.listdir(dir_path):
            if filename.endswith('.jpg') or filename.endswith('.png'):
                user = filename.split('.')[0]
                img_path = os.path.join(dir_path, filename)
                image = face_recognition.load_image_file(img_path)
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    known_encodings.append(encodings[0])
                    known_users.append((user, role))  # (用户名, 类型)
    return known_encodings, known_users


def match_face_from_base64(base64_image):
    try:
        # 解码前端发来的 base64 图片
        img_data = base64.b64decode(base64_image)
        image = Image.open(BytesIO(img_data)).convert("RGB")
        np_image = np.array(image)

        # 提取摄像头图片中的人脸
        unknown_encodings = face_recognition.face_encodings(np_image)
        if not unknown_encodings:
            return None

        unknown_encoding = unknown_encodings[0]

        # 加载库中人脸
        known_encodings, known_users = load_known_faces()
        results = face_recognition.compare_faces(known_encodings, unknown_encoding, tolerance=0.5)

        for i, matched in enumerate(results):
            if matched:
                username, role = known_users[i]
                return {"username": username, "role": role}
        return None
    except Exception as e:
        print(f"Face matching error: {e}")
        return None
