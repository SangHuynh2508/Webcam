# 🎓 Hệ thống Giám sát Thi cử Chống Gian lận (Anti-Cheat Webcam)

Hệ thống giám sát phòng thi trực tuyến sử dụng AI qua webcam. Phân tích thời gian thực: nhận diện khuôn mặt, phát hiện tư thế đầu, nhận dạng vật thể cấm — tất cả tích hợp vào một dashboard dành cho giáo viên và sinh viên.

---

## ✨ Tính năng chính

| Tính năng | Chi tiết |
|---|---|
| **Nhận diện khuôn mặt** | ArcFace (InsightFace `buffalo_l`) — so khớp cosine similarity |
| **Phân tích tư thế đầu** | MediaPipe Face Landmarker — phát hiện quay ngang/dọc |
| **Nhận dạng vật thể** | YOLOv8n (COCO) + custom model `best.pt` (máy tính Casio) |
| **Quản lý phòng thi** | Teacher tạo phòng, enroll sinh viên theo MSSV |
| **Giám sát real-time** | Dashboard live, đếm vi phạm tích lũy, chụp ảnh bằng chứng |
| **Phân quyền** | JWT Auth — 3 role: `admin`, `teacher`, `student` |
| **Database** | MongoDB (Motor async) — lưu sessions, violations, anchors |

---

## 🗂️ Cấu trúc dự án

```
Webcam/
├── backend/
│   ├── main.py          # FastAPI app — tất cả API endpoints
│   ├── ai_engine.py     # AIEngine: ArcFace + MediaPipe + YOLOv8
│   ├── auth.py          # JWT authentication & RBAC
│   ├── config.py        # Ngưỡng AI, đường dẫn, cấu hình MongoDB
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── csv_logger.py    # Legacy CSV logging (fallback)
│   └── database/        # MongoDB Motor async layer
├── frontend/
│   ├── index.html       # Giao diện chính (single-page)
│   ├── app.js           # Logic webcam, API calls, dashboard
│   └── style.css        # Styling
├── data/
│   └── anchor/          # Ảnh khuôn mặt tham chiếu (*.jpg)
├── logs/
│   └── violations/      # Ảnh chụp vi phạm tự động lưu
├── best.pt              # Custom YOLO model (máy tính)
├── yolov8n.pt           # YOLOv8 nano (COCO 80 classes)
├── face_landmarker.task # MediaPipe Face Landmarker model
└── requirements.txt
```

---

## ⚙️ Cài đặt & Chạy

### 1. Yêu cầu hệ thống

- Python **3.10+**
- MongoDB đang chạy local (`mongodb://localhost:27017/`) hoặc Atlas URI
- Webcam

### 2. Cài thư viện

```bash
pip install -r requirements.txt
```

> ⚠️ `insightface` yêu cầu C++ Build Tools trên Windows.  
> Tải tại: https://visualstudio.microsoft.com/visual-cpp-build-tools/

### 3. Cấu hình môi trường (tuỳ chọn)

Mặc định kết nối `mongodb://localhost:27017/`. Để dùng URI khác:

```bash
# Windows PowerShell
$env:MONGODB_URI = "mongodb+srv://user:password@cluster.mongodb.net/"
$env:MONGODB_DB_NAME = "anti_cheat_db"
```

### 4. Chạy server

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Truy cập: **http://localhost:8000**

---

## 🚀 Luồng sử dụng

```
Teacher                          Student
   │                                │
   ├─ Đăng ký tài khoản            ├─ Đăng ký tài khoản (role: student)
   ├─ Đăng nhập                    ├─ Đăng nhập
   ├─ Tạo phòng thi                │
   ├─ Enroll sinh viên (MSSV)      ├─ Vào phòng thi (nhập room code)
   ├─ Xem dashboard live           ├─ Bắt đầu làm bài → webcam bật
   └─ Xem log vi phạm              └─ Nộp bài → kết thúc session
```

---

## 🔑 Tài khoản mặc định khi setup

Khi sinh viên được enroll qua `/api/add_student` mà chưa có tài khoản, hệ thống tự tạo:

| Field | Giá trị |
|---|---|
| Username | `sv_<MSSV>` |
| Password | `student123` |

> Đổi mật khẩu sau khi đăng nhập lần đầu.

---

## 📡 API chính

| Method | Endpoint | Mô tả | Role |
|---|---|---|---|
| POST | `/api/auth/register` | Đăng ký user | Public |
| POST | `/api/auth/login` | Đăng nhập, lấy JWT | Public |
| GET | `/api/auth/me` | Thông tin user hiện tại | All |
| POST | `/api/rooms/create` | Tạo phòng thi | Teacher/Admin |
| POST | `/api/rooms/enroll` | Enroll sinh viên | Teacher/Admin |
| POST | `/api/exam/start` | Bắt đầu phiên thi | Student |
| POST | `/api/exam/submit` | Nộp bài | Student |
| POST | `/api/process_frame` | Gửi frame webcam để AI phân tích | Student |
| GET | `/api/rooms/{code}/status` | Live status phòng thi | Teacher/Admin |
| GET | `/api/logs/violations` | Xem log vi phạm | Teacher/Admin |
| GET | `/api/settings` | Xem cấu hình AI | Teacher/Admin |
| PUT | `/api/settings` | Cập nhật ngưỡng AI | Teacher/Admin |

Docs tương tác: **http://localhost:8000/docs**

---

## 🤖 Cấu hình AI (có thể chỉnh runtime qua API)

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `face_similarity_threshold` | `0.55` | Cosine similarity tối thiểu để nhận diện |
| `yolo_confidence_threshold` | `0.65` | Độ tin cậy tối thiểu của YOLO |
| `head_yaw_threshold` | `30°` | Góc quay ngang tối đa |
| `head_pitch_threshold` | `15°` | Góc cúi/ngẩng tối đa |

---

## 📁 Thêm khuôn mặt sinh viên (Enrollment)

**Cách 1 — API (khuyến nghị):**
```bash
curl -X POST http://localhost:8000/api/add_student \
  -F "mssv=2380601889" \
  -F "name=Nguyen Van A" \
  -F "photo=@path/to/photo.jpg"
```

**Cách 2 — Thủ công:**  
Đặt ảnh vào `data/anchor/` theo định dạng: `{MSSV}_{TenKhongDau}.jpg`  
Ví dụ: `2380601889_NguyenVanA.jpg`

---

## 🛠️ Tech Stack

- **Backend**: FastAPI + Uvicorn (Python async)
- **AI**: InsightFace (ArcFace) · MediaPipe · YOLOv8 (Ultralytics)
- **Database**: MongoDB + Motor (async driver)
- **Auth**: JWT (PyJWT) + bcrypt
- **Frontend**: Vanilla HTML/CSS/JS (no framework)
