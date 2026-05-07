// --- DOM Elements ---
const enrollForm = document.getElementById('enrollForm');
const enrollStatus = document.getElementById('enroll-status');

const video = document.getElementById('webcam');
const canvas = document.getElementById('hidden-canvas');
const ctx = canvas.getContext('2d');
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const inputMonMssv = document.getElementById('mon-mssv');
const consoleLog = document.getElementById('console-log');
const consoleWrapper = document.getElementById('console-wrapper');

let stream = null;
let monitorInterval = null;

// ==========================================
// A. ENROLLMENT (ĐĂNG KÝ)
// ==========================================
enrollForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const mssv = document.getElementById('reg-mssv').value;
    const name = document.getElementById('reg-name').value;
    const file = document.getElementById('reg-image').files[0];

    const formData = new FormData();
    formData.append('mssv', mssv);
    formData.append('name', name);
    formData.append('image', file);

    enrollStatus.style.color = "blue";
    enrollStatus.textContent = "Đang gửi dữ liệu...";

    try {
        const response = await fetch('/api/add_student', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            enrollStatus.style.color = "green";
            enrollStatus.textContent = `Đăng ký thành công MSSV: ${mssv}`;
            enrollForm.reset();
        } else {
            enrollStatus.style.color = "red";
            enrollStatus.textContent = "Lỗi đăng ký từ server!";
        }
    } catch (error) {
        enrollStatus.style.color = "red";
        enrollStatus.textContent = "Không kết nối được với API.";
    }
});

// ==========================================
// B. GIÁM SÁT (MONITORING)
// ==========================================
btnStart.addEventListener('click', async () => {
    const mssv = inputMonMssv.value.trim();
    if (!mssv) {
        alert('Vui lòng nhập MSSV trước khi giám sát!');
        return;
    }

    // 1. Mở Webcam
    try {
        if (!stream) {
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            video.srcObject = stream;
        }
    } catch (err) {
        logConsole('Không thể truy cập webcam!', 'danger');
        return;
    }

    // 2. Chuyển đổi trạng thái UI
    btnStart.disabled = true;
    btnStop.disabled = false;
    inputMonMssv.disabled = true;
    logConsole(`Bắt đầu giám sát MSSV: ${mssv}`, 'ok');

    // 3. Set interval capture 2s/lần (~0.5 FPS)
    monitorInterval = setInterval(() => captureAndSend(mssv), 2000);
});

btnStop.addEventListener('click', () => {
    // Tắt interval
    clearInterval(monitorInterval);
    
    // Reset UI
    btnStart.disabled = false;
    btnStop.disabled = true;
    inputMonMssv.disabled = false;
    logConsole('Đã dừng giám sát.', 'warning');
});

// Hàm xử lý capture & gọi API
async function captureAndSend(mssv) {
    if (!video.videoWidth) return; // Đợi video load xong

    // Set canvas kích thước bằng video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // a. Vẽ frame lên canvas
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // b. Convert sang Base64 dạng JPEG chất lượng 70% để giảm tải băng thông
    const base64Frame = canvas.toDataURL('image/jpeg', 0.7);

    // c. Gửi qua API
    try {
        const response = await fetch('/api/process_frame', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mssv: mssv, frame: base64Frame })
        });

        const data = await response.json();
        
        // d. Hiển thị log dựa theo kết quả server (Ví dụ server trả về status và message)
        // Giả sử: data.status có thể là 'ok', 'warning', 'danger'
        const statusType = data.status ? data.status.toLowerCase() : 'ok';
        logConsole(data.message || 'Frame nhận thành công.', statusType);

    } catch (error) {
        logConsole('Lỗi gửi frame! Server timeout hoặc down.', 'danger');
    }
}

// ==========================================
// C. CONSOLE LOG RENDERING
// ==========================================
function logConsole(message, type = 'ok') {
    const timeStr = new Date().toLocaleTimeString('vi-VN');
    
    const div = document.createElement('div');
    div.className = 'log-entry';
    div.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-${type}">${message}</span>`;
    
    consoleLog.appendChild(div);

    // Auto-scroll xuống cuối
    consoleWrapper.scrollTop = consoleWrapper.scrollHeight;
}