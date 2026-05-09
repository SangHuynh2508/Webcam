# Hướng dẫn Chạy Anti-Cheat Webcam System

## 📋 Tính năng đã hoàn thành

### ✅ Phase 1-3: Hoàn thiện
- AI Engine load 3 models (ArcFace, MediaPipe, YOLOv8) vào RAM
- Anchors database (186 students) được load tự động
- Backend API endpoints: `/api/health`, `/api/process_frame`, `/api/add_student`

### ✅ Phase 5: CSV Logging (MỚI)
- **Module `csv_logger.py`**: Ghi dữ liệu frame vào file CSV
- **Endpoints mới:**
  - `GET /api/logs` — Lấy dữ liệu đã ghi (CSV rows)
  - `GET /api/logs/stats` — Thống kê exam session
  - `GET /api/logs/sessions` — Liệt kê tất cả sessions
  
- **CSV Format:**
  ```
  timestamp,mssv,name,identity_status,similarity_score,alerts
  2026-05-07 10:30:45,23001,Nguyen Van A,Match,0.7234,"✅ MATCH: Nguyen Van A (similarity: 0.7234)"
  2026-05-07 10:31:00,23002,Tran Thi B,Unknown,0.3421,"⚠️ NGƯỜI LẠ (similarity: 0.3421)"
  ```

---

## 🚀 Cách chạy hệ thống

### 1. Cài đặt môi trường (Lần đầu)
```bash
cd c:\TH\Webcam
pip install -r requirements.txt
```

### 2. Khởi chạy Backend Server
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Output mong đợi:**
```
============================================================
STARTING Anti-Cheat System...
============================================================
[ArcFace] Model loaded successfully.
[MediaPipe] FaceMesh loaded successfully.
[YOLOv8] Model loaded successfully.
[Anchor] Loaded: 186 | Skipped: 0 | Total in DB: 186
Anchors loaded: 186
System READY. Waiting for connections...
============================================================
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 3. Kiểm tra hệ thống
- Health check: `http://localhost:8000/api/health`
- Frontend: `http://localhost:8000`

---

## 📊 API Endpoints

### Endpoint gốc (Phases 1-3)
```
GET  /api/health              — Kiểm tra server status
POST /api/process_frame       — Xử lý frame từ webcam
POST /api/add_student         — Đăng ký thí sinh mới
```

### Endpoints mới (Phase 5)
```
GET  /api/logs                — Lấy raw log data
GET  /api/logs/stats          — Thống kê session
GET  /api/logs/sessions       — Liệt kê sessions
```

### Ví dụ: Process Frame
```bash
curl -X POST http://localhost:8000/api/process_frame \
  -H "Content-Type: application/json" \
  -d '{
    "mssv": "23001",
    "frame": "data:image/jpeg;base64,...base64_encoded_image..."
  }'
```

**Response:**
```json
{
  "identity": {
    "status": "Match",
    "name": "Nguyen Van A",
    "similarity": 0.7234
  },
  "head_pose": null,
  "objects": null,
  "alerts": ["✅ MATCH: Nguyen Van A (similarity: 0.7234)"],
  "timestamp": "2026-05-07 10:30:45"
}
```

### Ví dụ: Get Logs
```bash
curl "http://localhost:8000/api/logs?limit=10"
```

**Response:**
```json
{
  "status": "ok",
  "session_id": "20260507",
  "total_rows": 245,
  "data": [
    {
      "timestamp": "2026-05-07 10:30:45",
      "mssv": "23001",
      "name": "Nguyen Van A",
      "identity_status": "Match",
      "similarity_score": "0.7234",
      "alerts": "✅ MATCH: Nguyen Van A (similarity: 0.7234)"
    },
    ...
  ]
}
```

### Ví dụ: Get Stats
```bash
curl "http://localhost:8000/api/logs/stats"
```

**Response:**
```json
{
  "status": "ok",
  "session_id": "20260507",
  "stats": {
    "total_frames": 245,
    "matched_count": 210,
    "unknown_count": 25,
    "no_face_count": 10,
    "students_tracked": ["23001", "23002", "23003", ...]
  }
}
```

---

## 📁 Cấu trúc Thư mục sau khi chạy

```
Webcam/
├── logs/
│   ├── session_20260507.csv       ← CSV log cho exam hôm nay
│   ├── session_20260506.csv       ← CSV log exam hôm qua
│   └── ...
├── data/anchor/
│   ├── 23001_Nguyen_Van_A.jpg
│   ├── 23002_Tran_Thi_B.jpg
│   └── ... (186 files)
├── backend/
│   ├── main.py                    ← FastAPI server (cập nhật Phase 5)
│   ├── ai_engine.py               ← AI models + logic
│   ├── config.py                  ← Configuration
│   ├── schemas.py                 ← Pydantic models
│   └── csv_logger.py              ← CSV Logger (MỚI)
└── ...
```

---

## 🔍 CSV Logger Chi tiết

### Class: `CSVLogger`

```python
from backend.csv_logger import CSVLogger

# Khởi tạo
logger = CSVLogger(log_dir="./logs")

# Ghi frame
logger.log_frame({
    "timestamp": "2026-05-07 10:30:45",
    "mssv": "23001",
    "name": "Nguyen Van A",
    "identity_status": "Match",
    "similarity_score": 0.7234,
    "alerts": ["✅ MATCH: Nguyen Van A (similarity: 0.7234)"]
})

# Lấy thống kê
stats = logger.get_session_stats(session_id="20260507")
# Returns: {
#   "total_frames": 245,
#   "matched_count": 210,
#   "unknown_count": 25,
#   "no_face_count": 10,
#   "students_tracked": ["23001", "23002", ...]
# }

# Lấy raw data
data = logger.get_session_data(limit=50)  # 50 rows gần nhất

# Liệt kê sessions
sessions = logger.list_sessions()
```

---

## ✨ Điểm cải thiện từ Phase 4 → Phase 5

| Tính năng | Trước | Sau |
|-----------|-------|-----|
| **CSV Logging** | ❌ Không có | ✅ Tự động ghi |
| **Audit Trail** | ❌ Mất dữ liệu | ✅ Lưu CSV |
| **Post-exam Review** | ❌ Không thể | ✅ Có thể review |
| **Thống kê** | ❌ Không có | ✅ API stats |
| **Log Management** | ❌ N/A | ✅ Multifile support |

---

## 🐛 Troubleshooting

### Lỗi: "No module named 'insightface'"
→ Cài lại: `pip install insightface onnxruntime`

### Lỗi: "CUDA not available"
→ Sử dụng CPU (mặc định, chậm hơn nhưng chạy được)

### CSV file không được tạo
→ Kiểm tra folder `logs/` có tồn tại & có write permission

### Không kết nối được server
→ Kiểm tra: `curl http://localhost:8000/api/health`

---

## 📚 Next Steps (Phases 6+)

- **Phase 4** (hoàn thiện): Frontend JS để bắt webcam & gọi API
- **Phase 6**: Dashboard để visualize logs (charts, timeline)
- **Phase 7**: Database backend (SQLite/PostgreSQL) thay CSV
- **Phase 8**: Authentication & role-based access control

