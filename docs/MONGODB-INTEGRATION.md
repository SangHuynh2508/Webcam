# Hướng Dẫn Tích Hợp Cơ Sở Dữ Liệu MongoDB

Tài liệu này ghi lại toàn bộ thiết kế, cấu trúc cơ sở dữ liệu (schema) và các thành phần phần mềm được thêm mới để tích hợp cơ sở dữ liệu **MongoDB** vào hệ thống **Webcam Exam Cheating Detection**.

Tuân thủ nghiêm ngặt yêu cầu **không thay đổi mã nguồn gốc (SQLite)**, tất cả các thành phần MongoDB được tạo ra dưới dạng các file độc lập và module hóa cao, sẵn sàng cắm-và-chạy (plug-and-play) khi hệ thống cần chuyển đổi.

---

## 1. Nguyên Tắc Thiết Kế Cơ Sở Dữ Liệu MongoDB
Khác với mô hình quan hệ bảng phẳng (normalized tables) trong SQLite, MongoDB tận dụng tối đa mô hình tài liệu (document model):

* **Mô hình Nhúng (Embedded Model) cho Ghi danh Phòng thi (`exam_rooms.students`)**:
  - Thông tin sinh viên tham gia phòng thi, đường dẫn ảnh gốc (anchor path) và **vector đặc trưng khuôn mặt (face embedding 512 chiều từ ArcFace)** được nhúng trực tiếp vào mảng `students` trong mỗi tài liệu phòng thi.
  - *Lợi ích*: Khi sinh viên bắt đầu làm bài, AI Engine chỉ cần truy vấn **đúng 1 câu lệnh** là tải được toàn bộ cấu hình phòng thi và dữ liệu khuôn mặt đối chiếu của sinh viên trong phòng đó vào RAM, loại bỏ hoàn toàn các phép toán join phức tạp.
* **Mô hình Liên kết (Referenced Model) cho Session và Nhật ký Vi phạm (`exam_sessions`, `violation_logs`)**:
  - Dữ liệu lượt thi và nhật ký vi phạm phát sinh liên tục theo từng khung hình camera được lưu trong các collection riêng để tránh vượt quá giới hạn 16MB của tài liệu MongoDB và tối ưu hóa tốc độ ghi (insert).

---

## 2. Danh Sách Các File Thêm Mới

Hệ thống đã bổ sung **3 thành phần chính**:

### 2.1. File cấu hình & Seed dữ liệu: `mongodb_setup.py`
* **Đường dẫn**: [mongodb_setup.py](file:///d:/dieuly/%C4%91h/doan/Webcam/mongodb_setup.py)
* **Chức năng**:
  - Kết nối và kiểm tra tính sẵn sàng của máy chủ MongoDB.
  - Tạo các collection kèm theo luật ràng buộc dữ liệu **JSON Schema (`$jsonSchema`)** ở mức database để đảm bảo toàn vẹn dữ liệu (kiểu dữ liệu, các trường bắt buộc, giá trị enum).
  - Thiết lập các chỉ mục (indexes) tối ưu (unique index cho username/mssv, compound index cho dashboard giám sát thời gian thực).
  - Nạp dữ liệu mẫu (seed data) tương thích với SQLite:
    - Tài khoản Admin (`admin` / `admin123`)
    - Tài khoản Giáo viên (`gv_quang` / `teacher123`)
    - Tài khoản Sinh viên (`sv_sang` / `student123`, MSSV: `2380601889`)
    - Phòng thi mẫu: `ROOM_101` và `ROOM_102`. Ghi danh sinh viên Huỳnh Minh Sáng vào `ROOM_101` kèm đường dẫn ảnh anchor gốc.
    - Cấu hình ngưỡng AI động (`global_ai_config`).

### 2.2. Module Adapter kết nối Database: `backend/mongodb_database.py`
* **Đường dẫn**: [backend/mongodb_database.py](file:///d:/dieuly/%C4%91h/doan/Webcam/backend/mongodb_database.py)
* **Chức năng**: Lớp adapter `MongoDBHelper` thực thi tất cả các nghiệp vụ tương ứng 1:1 với SQLite:
  - **Đăng ký & Đăng nhập (`register_user`, `authenticate_user`)**: Kiểm tra trùng lặp thông tin, mã hóa mật khẩu bằng bcrypt.
  - **Phân phòng thi & Ghi danh (`create_room`, `enroll_student`, `get_room_students`)**: Tạo phòng thi và ghi danh sinh viên qua MSSV.
  - **Lưu trữ dữ liệu khuôn mặt (`update_student_face_data`)**: Cập nhật vector đặc trưng 512 floats và đường dẫn ảnh anchor vào thông tin ghi danh phòng thi.
  - **Giám sát lượt thi (`start_exam_session`, `submit_exam_session`)**: Quản lý trạng thái làm bài, tự động kết thúc phiên thi chưa đóng trước đó.
  - **Log vi phạm & Cảnh báo tích lũy (`log_violation`)**: Ghi nhận hành vi gian lận (thiết bị cấm, sai người, không có mặt, nhiều người). Đồng thời tự động cập nhật số lần vi phạm và nâng mức cảnh báo của sinh viên (`NORMAL` -> `SUSPICIOUS` -> `FLAGGED`) dựa trên ngưỡng cấu hình động từ database.
  - **Dashboard thời gian thực (`get_room_live_status`, `get_violation_logs`)**: Truy vấn lịch sử vi phạm, trạng thái hoạt động của toàn bộ phòng thi.

### 2.3. Tài liệu thiết kế chi tiết: `mongodb_design.md`
* **Đường dẫn**: [mongodb_design.md](file:///d:/dieuly/%C4%91h/doan/Webcam/mongodb_design.md)
* **Chức năng**: Tài liệu lưu trữ cấu trúc JSON đại diện của từng collection, giải thích cấu trúc index và logic hoạt động chi tiết của MongoDB.

---

## 3. Cấu Trúc Collection & Schema Chi Tiết

### 3.1. Collection `users`
Lưu trữ thông tin người dùng trong hệ thống.
```json
{
  "_id": "ObjectId",
  "username": "string (unique)",
  "hashed_password": "string",
  "role": "string (admin | teacher | student)",
  "full_name": "string",
  "mssv": "string (unique, sparse, nullable)",
  "created_at": "date"
}
```

### 3.2. Collection `exam_rooms`
Lưu trữ thông tin phòng thi và danh sách sinh viên ghi danh cùng dữ liệu khuôn mặt tham chiếu.
```json
{
  "_id": "ObjectId",
  "room_code": "string (unique)",
  "title": "string",
  "description": "string (nullable)",
  "teacher_id": "ObjectId (ref: users)",
  "students": [
    {
      "student_id": "ObjectId (ref: users)",
      "face_embedding": "array of 512 doubles (nullable)",
      "face_image_path": "string (nullable)",
      "enrolled_at": "date"
    }
  ],
  "created_at": "date"
}
```

### 3.3. Collection `exam_sessions`
Theo dõi các lượt thi đang diễn ra hoặc đã nộp bài của sinh viên.
```json
{
  "_id": "ObjectId",
  "room_id": "ObjectId (ref: exam_rooms)",
  "student_id": "ObjectId (ref: users)",
  "started_at": "date",
  "ended_at": "date (nullable)",
  "violation_count": "int (default 0)",
  "status": "string (NORMAL | SUSPICIOUS | FLAGGED)"
}
```

### 3.4. Collection `violation_logs`
Bảng nhật ký kiểm toán ghi lại chi tiết các hành vi vi phạm được phát hiện bởi AI.
```json
{
  "_id": "ObjectId",
  "session_id": "ObjectId (ref: exam_sessions)",
  "room_id": "ObjectId (ref: exam_rooms)",
  "student_id": "ObjectId (ref: users)",
  "timestamp": "date",
  "violation_type": "string (cell_phone | unknown_identity | no_face | multiple_persons | ...)",
  "severity": "string (CRITICAL | WARNING)",
  "similarity_score": "double (nullable)",
  "details": "string",
  "frame_image_path": "string (nullable)"
}
```

### 3.5. Collection `system_settings`
Lưu trữ ngưỡng cấu hình động cho AI Engine và cấp độ leo thang cảnh báo.
```json
{
  "_id": "global_ai_config",
  "face_similarity_threshold": 0.55,
  "head_yaw_threshold": 30.0,
  "head_pitch_threshold": 25.0,
  "yolo_confidence_threshold": 0.65,
  "max_violations_suspicious": 3, // Vi phạm >= 3 -> SUSPICIOUS
  "max_violations_flagged": 5,    // Vi phạm >= 5 -> FLAGGED
  "updated_at": "date"
}
```

---

## 4. Hướng Dẫn Sử Dụng

### Bước 1: Cài đặt thư viện kết nối MongoDB
Chạy lệnh sau để cài đặt `pymongo`:
```bash
pip install pymongo
```

### Bước 2: Thiết lập kết nối
Theo mặc định, hệ thống kết nối tới MongoDB local tại `mongodb://localhost:27017/` và sử dụng cơ sở dữ liệu `anti_cheat_db`. 
Nếu bạn muốn dùng MongoDB Atlas hoặc cổng khác, cấu hình biến môi trường trước khi chạy:
```powershell
# Trên Windows PowerShell
$env:MONGODB_URI="mongodb://localhost:27017/"
$env:MONGODB_DB_NAME="anti_cheat_db"
```

### Bước 3: Khởi tạo database và dữ liệu mẫu (Seeding)
Chạy script cài đặt tại thư mục gốc:
```bash
python mongodb_setup.py
```
*Lưu ý*: Script này sẽ tự động xóa các collection cũ (nếu có trùng tên), thiết lập các Schema Validation nghiêm ngặt, cấu hình các Index tăng tốc và chèn dữ liệu người dùng/phòng thi mẫu.

---

## 5. Bản Vẽ Tích Hợp Vào FastAPI Trong Tương Lai
Để thay thế SQLite bằng MongoDB trong mã nguồn backend của bạn, bạn chỉ cần thực hiện 2 thay đổi nhỏ mà không cần sửa đổi cấu trúc nghiệp vụ:

1. **Thay đổi DB Dependency trong `backend/main.py`**:
```python
from backend.mongodb_database import MongoDBHelper

# Khởi tạo instance kết nối duy nhất
mongo_db = MongoDBHelper()

def get_mongo_db():
    return mongo_db
```

2. **Chuyển đổi Endpoint**:
Các phương thức trong `MongoDBHelper` được thiết kế có tham số đầu vào và kiểu đầu ra đồng bộ hoàn toàn với SQLite. Ví dụ chuyển đổi endpoint Đăng ký:

*SQLite gốc*:
```python
@app.post("/api/auth/register")
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user: ...
    # ... logic thêm mới ...
```

*Chuyển sang MongoDB*:
```python
@app.post("/api/auth/register")
async def register(user_data: UserRegister, db: MongoDBHelper = Depends(get_mongo_db)):
    try:
        new_user = db.register_user(
            username=user_data.username,
            password_plain=user_data.password,
            role=user_data.role,
            full_name=user_data.full_name,
            mssv=user_data.mssv
        )
        new_user["id"] = str(new_user["_id"])  # Định dạng lại ID dạng chuỗi JSON
        return new_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```
