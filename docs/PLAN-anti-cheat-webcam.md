# PLAN: Anti-Cheat Webcam — Hệ thống giám sát thi cử

> **Chiến lược:** Skeleton Architecture — Xây khung trước, đắp thịt sau.
> **Scope:** Single-user PoC (localhost, 1 thí sinh/thời điểm).

---

## Tổng quan Kiến trúc

```
┌─────────────────────┐                       ┌──────────────────────┐
│     Frontend        │  POST /api/frame      │   FastAPI Backend    │
│    (HTML/JS/CSS)    │ ─── (Base64+MSSV) ───►│                      │
│                     │ ◄── JSON Response ────│  ┌────────────────┐  │
│  ┌───────────────┐  │                       │  │   AI_Engine    │  │
│  │ Webcam Stream │  │  POST /api/add_student│  │  ┌──────────┐  │  │
│  │ Console Log   │  │ ─── (File+MSSV) ─────►│  │  │ ArcFace  │✅│  │
│  │ Enrollment    │  │ ◄── JSON Status ──────│  │  │ MediaPipe│🔲│  │
│  │   Form        │  │                       │  │  │ YOLOv8   │🔲│  │
│  └───────────────┘  │                       │  │  └──────────┘  │  │
└─────────────────────┘                       │  └────────────────┘  │
                                              │         │            │
                                              │    data/anchor/      │
                                              │    logs/*.csv        │
                                              └──────────────────────┘
✅ = Fully Implemented | 🔲 = Placeholder
```

---

## Cấu trúc Thư mục

```
Webcam/
├── data/
│   └── anchor/              # 186 ảnh: MSSV_HoTen.jpg
├── logs/                    # CSV output
├── backend/
│   ├── main.py              # FastAPI entry + lifespan
│   ├── ai_engine.py         # Class AI_Engine (3 models)
│   ├── config.py            # Thresholds & constants
│   └── schemas.py           # Pydantic request/response
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js               # WebRTC + capture + fetch
├── requirements.txt
└── README.md
```

---

## Phase 1: Project Setup & AI Initialization

### Mục tiêu
Cài đặt môi trường, tạo class `AIEngine` load **cả 3 model** vào RAM khi server khởi động.

### Tasks

- [ ] **1.1** Tạo cấu trúc thư mục + `requirements.txt`
  ```
  fastapi, uvicorn[standard], python-multipart
  insightface, onnxruntime
  mediapipe
  ultralytics
  opencv-python, numpy, scikit-learn
  ```
- [ ] **1.2** Tạo `backend/config.py` — constants & thresholds
- [ ] **1.3** Tạo `backend/ai_engine.py` — Class `AIEngine`:
  ```python
  class AIEngine:
      def __init__(self):
          self.face_analyzer = None    # insightface.app.FaceAnalysis
          self.face_landmarker = None  # mediapipe FaceLandmarker
          self.object_detector = None  # YOLO("yolov8n.pt")
          self.anchor_db = {}          # {MSSV: {name, embedding}}

      def load_models(self):
          """Load cả 3 model vào RAM — gọi 1 lần khi startup."""

      def load_anchors(self, anchor_dir: str):
          """Quét data/anchor/, trích xuất embedding ArcFace,
          lưu vào self.anchor_db = {MSSV: {name, embedding}}."""
  ```
- [ ] **1.4** Tạo `backend/main.py` — FastAPI app với `lifespan` event:
  - Khi startup: gọi `engine.load_models()` → `engine.load_anchors()`
  - Mount static files cho frontend
  - Tạo endpoint health check `GET /api/health`

### Verify
- Chạy `uvicorn backend.main:app` → server start, log hiển thị số lượng anchors loaded (186).
- `GET /api/health` trả `{"status": "ok", "anchors_loaded": 186}`

---

## Phase 2: Backend API Flow

### Mục tiêu
Endpoint `POST /api/process_frame` nhận ảnh + MSSV, gọi AI pipeline, trả JSON.

### Tasks

- [ ] **2.1** Tạo `backend/schemas.py`:
  ```python
  class FrameRequest(BaseModel):
      mssv: str           # Mã số sinh viên
      frame: str          # Base64 encoded JPEG

  class FrameResponse(BaseModel):
      identity: dict      # {verified, similarity, name}
      head_pose: dict | None   # placeholder
      objects: dict | None     # placeholder
      alerts: list[str]        # Danh sách cảnh báo
      timestamp: str
  ```
- [ ] **2.2** Tạo endpoint `POST /api/process_frame`:
  1. Nhận `FrameRequest`
  2. Decode base64 → numpy array (cv2.imdecode)
  3. Gọi `engine.verify_identity(frame, mssv)`
  4. Gọi `engine.analyze_head_pose(frame)` → trả `None` (placeholder)
  5. Gọi `engine.detect_objects(frame)` → trả `None` (placeholder)
  6. Tổng hợp alerts → trả `FrameResponse`
- [ ] **2.3** Tạo endpoint `POST /api/add_student` — **Dynamic Face Enrollment**:
  1. Nhận `UploadFile` (ảnh) + `Form(mssv)` + `Form(name)`
  2. Đọc file → decode → `engine.face_analyzer.get(img)`
  3. Trích xuất embedding → cập nhật `engine.anchor_db[mssv]`
  4. Lưu file ảnh vào `data/anchor/{MSSV}_{Name}.jpg` (backup)
  5. Trả `{"status": "ok", "mssv": ..., "total_anchors": ...}`
- [ ] **2.4** Thêm CORS middleware (cho localhost dev)

### Verify
- POST `/api/process_frame` → nhận JSON response có `identity.verified`.
- POST `/api/add_student` với file ảnh → anchor_db tăng thêm 1, file lưu trong `data/anchor/`.

---

## Phase 3: Anti-Cheat Logic (Skeleton)

### Mục tiêu
Implement **đầy đủ** ArcFace verification. MediaPipe & YOLO chỉ tạo **placeholder**.

### Thresholds (trong `config.py`)

| Model | Metric | Threshold | Cảnh báo |
|-------|--------|-----------|----------|
| **ArcFace** | Cosine Similarity | < 0.45 | ⚠️ "Không khớp danh tính" |
| **ArcFace** | No face detected | — | ⚠️ "Không phát hiện khuôn mặt" |
| MediaPipe | Yaw | > ±30° | 🔲 "Liếc bài" (placeholder) |
| MediaPipe | Pitch | > ±25° | 🔲 "Cúi đầu" (placeholder) |
| YOLO | Confidence | > 0.5 | 🔲 "Vật thể cấm" (placeholder) |

### Tasks

- [ ] **3.1** Implement `AIEngine.verify_identity(frame, mssv)`:
  ```python
  def verify_identity(self, frame, mssv) -> dict:
      """
      1. Detect face trong frame bằng self.face_analyzer.get(frame)
      2. Lấy embedding từ face detected
      3. So sánh cosine similarity với self.anchor_db[mssv]['embedding']
      4. Return {verified: bool, similarity: float, name: str}
      """
  ```
- [ ] **3.2** Implement placeholder `AIEngine.analyze_head_pose(frame)`:
  ```python
  def analyze_head_pose(self, frame) -> dict | None:
      # TODO: Implement MediaPipe head pose analysis
      return None
  ```
- [ ] **3.3** Implement placeholder `AIEngine.detect_objects(frame)`:
  ```python
  def detect_objects(self, frame) -> dict | None:
      # TODO: Implement YOLOv8 object detection
      return None
  ```
- [ ] **3.4** Tạo hàm `build_alerts()` tổng hợp kết quả → danh sách cảnh báo string

### Verify
- Gửi ảnh của SV có trong anchor → `verified: true`, similarity > 0.45
- Gửi ảnh người lạ → `verified: false`

---

## Phase 4: Frontend & Webcam Stream

### Mục tiêu
Giao diện tối giản: webcam preview + input MSSV + console log panel.

### Tasks

- [ ] **4.1** Tạo `frontend/index.html`:
  - **Khu vực Enrollment:** Form đăng ký thí sinh (input MSSV, input tên, chọn file ảnh, nút "Đăng ký")
  - **Khu vực Giám sát:** Input MSSV + nút "Bắt đầu giám sát" / "Dừng"
  - `<video>` element cho webcam stream
  - `<canvas>` ẩn để capture frame
  - `<div id="console-log">` hiển thị cảnh báo realtime
- [ ] **4.2** Tạo `frontend/style.css`:
  - Layout 2 cột: webcam bên trái, console bên phải
  - Enrollment form phía trên hoặc collapsible panel
  - Console log style giống terminal (nền đen, chữ xanh mono)
  - Tối giản, không cần đẹp, tập trung chức năng
- [ ] **4.3** Tạo `frontend/app.js`:
  ```
  Luồng hoạt động:
  A. Enrollment:
     1. User chọn ảnh + nhập MSSV + tên → click "Đăng ký"
     2. FormData upload → fetch('/api/add_student')
     3. Hiển thị kết quả đăng ký
  
  B. Giám sát:
     1. getUserMedia() → stream video vào <video>
     2. User nhập MSSV → click "Bắt đầu"
     3. setInterval(captureAndSend, 2000) — capture mỗi 2s (~0.5 FPS)
     4. captureAndSend():
        a. drawImage(video) lên canvas
        b. canvas.toDataURL('image/jpeg', 0.7) → base64
        c. fetch('/api/process_frame', {mssv, frame})
        d. Nhận response → render alerts vào console-log
     5. Nút "Dừng" → clearInterval
  ```
- [ ] **4.4** Console Log rendering:
  - Mỗi alert 1 dòng, có timestamp, color-coded (đỏ=nguy hiểm, vàng=cảnh báo, xanh=OK)
  - Auto-scroll xuống cuối

### Verify
- Mở browser → cho phép webcam → nhập MSSV → click Start → console hiển thị kết quả mỗi 2s.

---

## Phase 5: Logging & Hậu kiểm

### Mục tiêu
Ghi log mọi frame đã xử lý ra file CSV để giám thị xem lại.

### Tasks

- [ ] **5.1** Tạo module logging trong `backend/main.py` hoặc tách `backend/logger.py`:
  ```
  File: logs/session_{MSSV}_{YYYYMMDD_HHmmss}.csv
  Columns: timestamp, mssv, identity_verified, similarity,
           head_pose_alert, object_alert, raw_alerts
  ```
- [ ] **5.2** Mỗi lần xử lý frame → append 1 row vào CSV
- [ ] **5.3** Endpoint `GET /api/logs` — liệt kê các file log đã tạo (optional, tiện cho demo)

### Verify
- Sau phiên giám sát → kiểm tra file CSV trong `logs/` có đầy đủ dữ liệu.

---

## Tóm tắt Thứ tự Triển khai

| Phase | Nội dung | Output chính |
|-------|----------|-------------|
| 1 | Setup + Load 3 Models | Server start, 186 anchors in RAM |
| 2 | API endpoint | `POST /api/process_frame` hoạt động |
| 3 | ArcFace logic + placeholders | Face verification chạy đúng |
| 4 | Frontend webcam | Giao diện capture + console log |
| 5 | CSV logging | File log cho hậu kiểm |

---

> **Tiếp theo:** Trả lời **"Đồng ý"** để tôi bắt đầu triển khai Phase 1.
