# Project Status Report: Anti-Cheat Webcam

**Ngày tạo:** 02/05/2026

## 1. Tóm tắt Tổng quan (Executive Summary)
- **Trạng thái Server:** Uvicorn Server đã khởi chạy thành công. Các thư viện AI nặng (đặc biệt là `insightface` yêu cầu build C++) đã được cài đặt và load trơn tru vào RAM ở sự kiện startup (`lifespan`). Hệ thống hiện không có lỗi.
- **Tính năng lõi đã hoạt động:** 
  - Khởi tạo & nạp toàn bộ cấu trúc dữ liệu Face Embeddings (Anchors) vào RAM.
  - Các API endpoints (`/api/process_frame`, `/api/add_student`) đã sẵn sàng. 
  - Engine nhận diện khuôn mặt (ArcFace) đã có thể trích xuất khuôn mặt lớn nhất và đối chiếu 1:N với toàn bộ Database (Cosine Similarity Threshold = 0.55).

---

## 2. Chi tiết theo 5 Phase (Phase Status)

| Phase | Tên Phase | Trạng thái | Chi tiết hoàn thành | Missing (Còn thiếu) |
|:---:|---|---|---|---|
| **1** | Project Setup & AI Init | **[Đã xong]** | - Cấu trúc file/folder, `requirements.txt`, cài môi trường.<br>- Class `AIEngine` load 3 models & anchors vào RAM.<br>- Cấu hình constants trong `config.py`. | (Không có) |
| **2** | Backend API Flow | **[Đã xong]** | - Pydantic `schemas.py` validation.<br>- Endpoint `POST /api/process_frame`.<br>- Endpoint `POST /api/add_student` (Dynamic Enrollment). | (Không có) |
| **3** | Anti-Cheat Logic | **[Đang làm]** | - Logic Face Verification (ArcFace): Tìm khuôn mặt to nhất, so khớp 1:N để phân loại `Match`, `Unknown`, `No Face`. | - Hàm xử lý `analyze_head_pose` (MediaPipe) và `detect_objects` (YOLO) đang là Placeholder (`return None`). |
| **4** | Frontend & Webcam Stream | **[Đang làm]** | - Đã tạo `index.html` chứa layout form Đăng ký, Giám sát, màn hình Video và Console Log. | - CSS (`style.css`) để dàn trang.<br>- JS (`app.js`) để bắt luồng WebRTC, setInterval gọi API và render dữ liệu. |
| **5** | Logging & Hậu kiểm | **[Chưa làm]** | | - Module ghi dữ liệu frame ra file CSV.<br>- Endpoint `GET /api/logs`. |

---

## 3. Next Steps (Việc cần làm tiếp theo)
Để nhanh chóng có một bản Proof of Concept (PoC) hoàn chỉnh, dưới đây là 3 hành động kỹ thuật đề xuất thực hiện ngay tiếp theo:

1. **Xử lý luồng Frontend (`app.js` & `style.css`):** Viết logic WebRTC để bắt Webcam, dùng `canvas.toDataURL` capture khung hình gửi Base64 liên tục (interval 2s) xuống Backend, đồng thời xử lý kết quả để in ra màn hình Console. *(Phase 4)*
2. **Triển khai CSV Logger (Phase 5):** Thêm một utility nhỏ trong `main.py` hoặc tạo `logger.py` để ghi append kết quả của mỗi frame (thời gian, trạng thái Match/Unknown) vào file CSV nhằm phục vụ việc hậu kiểm (post-exam review).
3. **Thử nghiệm tích hợp End-to-End (E2E):** Test chạy thử luồng từ trình duyệt (Frontend) -> gọi API -> AI xử lý -> hiển thị Log -> ghi file CSV để xác nhận Data Pipeline không bị tắc nghẽn (bottleneck).
