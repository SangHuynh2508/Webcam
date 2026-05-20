# PLAN: Trùng tu (Refactor) Stack Anti-Cheat Webcam

## Mục tiêu (Goal)
Nâng cấp kiến trúc phần mềm (Stack) của hệ thống Giám sát thi Anti-Cheat từ cơ bản (Vanilla JS + Polling API + Local Files) lên một cấu trúc chuyên nghiệp, thực tế và có khả năng mở rộng cao hơn. Vẫn **giữ lại sức mạnh AI của Python (FastAPI)** nhưng kết hợp với **công nghệ Web hiện đại**.

---

## Mở cổng Socratic (Open Questions - Cần User xác nhận)

> [!WARNING]
> **Trước khi chốt Plan, mình cần bạn xác nhận 3 câu hỏi sau:**
> 1. **MongoDB:** Bạn muốn dùng MongoDB Local (cài trên máy) hay MongoDB Atlas (trên cloud, miễn phí 512MB)?
> 2. **Kiến trúc UI mới:** Ở Frontend bằng React, bạn chỉ muốn làm đúng 1 màn hình Webcam (như cũ) hay muốn làm thêm một màn hình "Dashboard Giám Thị" (để xem được log/webcam của nhiều sinh viên cùng lúc)?
> 3. **Tần suất gửi ảnh:** Với WebSocket, tốc độ truyền tải cực nhanh. Bạn muốn duy trì gửi 2 giây/frame hay muốn tăng tốc độ lên 5-10 khung hình/giây (real-time mượt nhưng tốn CPU Backend)?

---

## Đề xuất Kiến trúc mới (Proposed Architecture)

| Thành phần | Cũ (Hiện tại) | Mới (Sau trùng tu) | Lý do nâng cấp |
| :--- | :--- | :--- | :--- |
| **Frontend** | Vanilla JS, HTML, CSS | **React.js (Vite) + Tailwind CSS** | Dễ quản lý component, UI đẹp và chuyên nghiệp hơn, sẵn sàng mở rộng quy mô. |
| **Backend** | Python (FastAPI) | **Python (FastAPI)** | Đang làm rất tốt nhiệm vụ xử lý AI. Không cần đổi sang Node.js. |
| **Database** | File `.jpg` và `.csv` | **MongoDB (Motor/PyMongo)** | Dễ dàng query, lưu trữ an toàn, tránh lỗi đọc/ghi khi nhiều người cùng kết nối. |
| **Giao tiếp** | HTTP POST (`setInterval` 2s) | **FastAPI WebSockets** | Truyền tải ảnh liên tục theo luồng (stream), giảm độ trễ (latency), tiết kiệm overhead HTTP. |
| **AI Models** | InsightFace, YOLOv8, MediaPipe | **Giữ nguyên** | Các model hiện tại đang hoạt động hiệu quả. |

---

## Phân rã Công việc (Task Breakdown)

### Phase 1: Nâng cấp Cơ sở dữ liệu (MongoDB)
*Đại diện AI: `@backend-specialist` & `@database-design`*
- [ ] Cài đặt kết nối MongoDB vào FastAPI.
- [ ] Refactor API `/api/add_student`: Lưu ảnh face embedding và thông tin sinh viên vào MongoDB thay vì lưu file `.jpg` vào thư mục `data/anchor`.
- [ ] Tạo module lưu trữ Log cảnh báo vào MongoDB thay vì ghi file `.csv`.

### Phase 2: Nâng cấp Giao thức truyền tải (WebSockets)
*Đại diện AI: `@backend-specialist`*
- [ ] Thêm WebSocket endpoint `/ws/monitor/{mssv}` vào `main.py`.
- [ ] Chuyển logic của `process_frame` từ HTTP POST sang nhận luồng bytes trực tiếp qua WebSocket.
- [ ] Trả kết quả (Bounding box, Alert) ngược lại cho Frontend ngay lập tức qua WebSocket.

### Phase 3: Khởi tạo Frontend React.js
*Đại diện AI: `@frontend-specialist`*
- [ ] Khởi tạo dự án React bằng Vite (`npm create vite@latest`).
- [ ] Thiết lập Tailwind CSS.
- [ ] Xây dựng lại giao diện: Form đăng ký, Khung Webcam, và Bảng điều khiển Console Log.
- [ ] Tích hợp lại MediaPipe Face Mesh vào trong React Component để vẽ bounding box ở client-side.

### Phase 4: Tích hợp và Tối ưu (Integration & Optimization)
*Đại diện AI: `@orchestrator`*
- [ ] Viết hook `useWebSocket` trong React để kết nối liên tục với Backend.
- [ ] Xử lý logic nén ảnh trước khi gửi qua WebSocket để tiết kiệm băng thông.
- [ ] Chạy thử nghiệm E2E (End-to-End) và sửa lỗi.

---

## Kế hoạch Xác minh (Verification Plan)
- **Database Test:** Đăng ký 1 sinh viên mới, kiểm tra data có nằm trong MongoDB (dùng Compass) thay vì thư mục `data`.
- **WebSocket Test:** Bật Network tab ở browser, đảm bảo dữ liệu chạy qua luồng `ws://` thay vì `http://`.
- **Stress Test:** Thử cho camera quay liên tục xem tốc độ phản hồi có mượt hơn so với 2 giây hiện tại hay không.
