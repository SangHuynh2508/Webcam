"""
csv_logger.py — Mô-đun ghi log CSV cho Phase 5: Ghi log & Hậu kiểm

Ghi lại kết quả phân tích từng frame vào file CSV để phục vụ
việc hậu kiểm sau kỳ thi (audit trail).
"""
import os
import csv
import logging
from datetime import datetime
from pathlib import Path

from backend.config import LOG_DIR

logger = logging.getLogger("anti_cheat.csv_logger")


class CSVLogger:
    """Xử lý ghi kết quả phân tích frame vào file CSV để tạo audit trail."""

    def __init__(self, log_dir: str = LOG_DIR):
        """
        Khởi tạo CSV logger.
        
        Args:
            log_dir: Thư mục lưu file CSV (mặc định: logs/)
        """
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Các cột tiêu đề trong file CSV
        self.fieldnames = [
            "timestamp",        # Thời gian
            "mssv",            # Mã số sinh viên
            "name",            # Tên sinh viên
            "identity_status", # Trạng thái nhận diện
            "similarity_score",# Điểm tương đồng
            "alerts",          # Danh sách cảnh báo
        ]
        
        logger.info(f"[CSVLogger] ✅ Đã khởi tạo. Thư mục log: {self.log_dir}")

    def get_csv_path(self, exam_session_id: str = None) -> str:
        """
        Sinh đường dẫn file CSV dựa trên phiên thi.
        
        Args:
            exam_session_id: Mã định danh phiên thi (mặc định: ngày hôm nay YYYYMMDD)
            
        Returns:
            Đường dẫn đầy đủ đến file CSV
        """
        if exam_session_id is None:
            exam_session_id = datetime.now().strftime("%Y%m%d")
        
        filename = f"session_{exam_session_id}.csv"
        return os.path.join(self.log_dir, filename)

    def log_frame(self, frame_data: dict, exam_session_id: str = None) -> bool:
        """
        Ghi kết quả phân tích 1 frame vào file CSV.
        
        Args:
            frame_data: Từ điển chứa:
                - timestamp: str (định dạng ISO)
                - mssv: str (Mã số sinh viên)
                - name: str (Tên sinh viên)
                - identity_status: str (Match/Unknown/No Face)
                - similarity_score: float (Tương đồng cosine)
                - alerts: list[str] (Danh sách cảnh báo)
            exam_session_id: ID phiên thi (mặc định: ngày hôm nay YYYYMMDD)
            
        Returns:
            True nếu thành công, False nếu lỗi
        """
        csv_path = self.get_csv_path(exam_session_id)
        
        try:
            # Kiểm tra file có tồn tại không để quyết định ghi header
            file_exists = os.path.isfile(csv_path)
            
            # Chuyển đổi danh sách alerts thành chuỗi (phân tách bằng |)
            alerts_str = " | ".join(frame_data.get("alerts", []))
            
            # Chuẩn bị dữ liệu hàng
            row_data = {
                "timestamp": frame_data.get("timestamp", ""),
                "mssv": frame_data.get("mssv", ""),
                "name": frame_data.get("name", ""),
                "identity_status": frame_data.get("identity_status", ""),
                "similarity_score": round(frame_data.get("similarity_score", 0.0), 4),
                "alerts": alerts_str,
            }
            
            # Ghi vào file CSV
            with open(csv_path, mode="a", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.fieldnames)
                
                # Ghi header nếu file mới
                if not file_exists:
                    writer.writeheader()
                    logger.info(f"[CSVLogger] 📝 Tạo file phiên mới: {csv_path}")
                
                writer.writerow(row_data)
            
            logger.debug(f"[CSVLogger] 📌 Đã ghi frame cho MSSV={frame_data.get('mssv')}")
            return True
            
        except Exception as e:
            logger.error(f"[CSVLogger] ❌ Lỗi ghi frame: {e}")
            return False

    def get_session_stats(self, exam_session_id: str = None) -> dict:
        """
        Lấy thống kê của một phiên thi cụ thể.
        
        Args:
            exam_session_id: ID phiên thi (mặc định: ngày hôm nay YYYYMMDD)
            
        Returns:
            Từ điển chứa thống kê:
                - total_frames: int (tổng số frame)
                - matched_count: int (số frame Match)
                - unknown_count: int (số frame Unknown)
                - no_face_count: int (số frame No Face)
                - students_tracked: list (danh sách sinh viên được theo dõi)
        """
        csv_path = self.get_csv_path(exam_session_id)
        
        if not os.path.isfile(csv_path):
            return {
                "total_frames": 0,
                "matched_count": 0,
                "unknown_count": 0,
                "no_face_count": 0,
                "students_tracked": [],
                "message": f"❌ Không tìm thấy dữ liệu cho phiên: {exam_session_id}",
            }
        
        try:
            stats = {
                "total_frames": 0,
                "matched_count": 0,
                "unknown_count": 0,
                "no_face_count": 0,
                "students_tracked": set(),
            }
            
            with open(csv_path, mode="r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row in reader:
                    stats["total_frames"] += 1
                    
                    status = row.get("identity_status", "").strip()
                    if status == "Match":
                        stats["matched_count"] += 1
                    elif status == "Unknown":
                        stats["unknown_count"] += 1
                    elif status == "No Face":
                        stats["no_face_count"] += 1
                    
                    mssv = row.get("mssv", "").strip()
                    if mssv:
                        stats["students_tracked"].add(mssv)
            
            stats["students_tracked"] = list(stats["students_tracked"])
            logger.info(f"[CSVLogger] 📊 Lấy thống kê phiên: {stats['total_frames']} frame")
            return stats
            
        except Exception as e:
            logger.error(f"[CSVLogger] ❌ Lỗi lấy thống kê: {e}")
            return {
                "total_frames": 0,
                "error": str(e),
            }

    def list_sessions(self) -> list:
        """
        Liệt kê tất cả các phiên thi (file CSV) trong thư mục log.
        
        Returns:
            Danh sách các tên file phiên thi
        """
        try:
            sessions = []
            for filename in os.listdir(self.log_dir):
                if filename.startswith("session_") and filename.endswith(".csv"):
                    sessions.append(filename)
            
            sessions.sort(reverse=True)  # Gần đây nhất ở đầu
            return sessions
            
        except Exception as e:
            logger.error(f"[CSVLogger] ❌ Lỗi liệt kê phiên: {e}")
            return []

    def get_session_data(self, exam_session_id: str = None, limit: int = None) -> list:
        """
        Lấy dữ liệu thô (raw) từ file CSV của một phiên thi.
        
        Args:
            exam_session_id: ID phiên thi (mặc định: ngày hôm nay YYYYMMDD)
            limit: Số dòng tối đa cần lấy (mặc định: None = tất cả)
            
        Returns:
            Danh sách các từ điển (các dòng từ CSV)
        """
        csv_path = self.get_csv_path(exam_session_id)
        
        if not os.path.isfile(csv_path):
            return []
        
        try:
            data = []
            with open(csv_path, mode="r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for i, row in enumerate(reader):
                    if limit and i >= limit:
                        break
                    data.append(row)
            
            return data
            
        except Exception as e:
            logger.error(f"[CSVLogger] ❌ Lỗi lấy dữ liệu phiên: {e}")
            return []
