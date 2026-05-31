// ==========================================
// IMPORTS — MediaPipe Vision (client-side face tracking)
// ==========================================
import { FaceDetector, FilesetResolver } from
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18/vision_bundle.mjs";

// --- DOM Elements ---
const enrollForm = document.getElementById('enrollForm');
const enrollStatus = document.getElementById('enroll-status');

const canvas = document.getElementById('hidden-canvas');
const ctx = canvas.getContext('2d');
const overlayCanvas = document.getElementById('overlay-canvas');
const overlayCtx = overlayCanvas.getContext('2d');
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const consoleLog = document.getElementById('console-log');
const consoleWrapper = document.getElementById('console-wrapper');

const video = document.getElementById('webcam');
const loginForm = document.getElementById('loginForm');
const userInfoDiv = document.getElementById('user-info');

let stream = null;
let monitorInterval = null;
let currentUser = null; // { mssv: string, name: string, role: string }
let rooms = [];
let currentRoomCode = null;
let violationPolling = null;

// --- Client-side face tracking state ---
let faceDetector = null;
let clientTrackingRAF = null;  // requestAnimationFrame ID
let lastServerIdentity = null; // Latest identity result from server
let lastServerHeadPose = null;  // Latest head pose result from server
let isMonitoring = false;      // Flag để chặn các request đang delay khi bấm Stop

// ==========================================
// XỬ LÝ GIAO DIỆN & PHÂN QUYỀN
// ==========================================
function showView(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
    document.getElementById(viewId).classList.remove('hidden');
}

window.switchAuthTab = (tab) => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

    const loginFormEl = document.getElementById('loginForm');
    const registerFormEl = document.getElementById('registerForm');
    const tabLogin = document.getElementById('tab-login');
    const tabRegister = document.getElementById('tab-register');

    if (tab === 'login') {
        tabLogin.classList.add('active');
        loginFormEl.classList.remove('hidden');
        registerFormEl.classList.add('hidden');
    } else {
        tabRegister.classList.add('active');
        loginFormEl.classList.add('hidden');
        registerFormEl.classList.remove('hidden');
    }
};

window.toggleRegMssvField = () => {
    const role = document.getElementById('register-role').value;
    const mssvGroup = document.getElementById('reg-mssv-group');
    const mssvInput = document.getElementById('register-mssv');
    if (role === 'student') {
        mssvGroup.classList.remove('hidden');
        mssvInput.setAttribute('required', 'true');
    } else {
        mssvGroup.classList.add('hidden');
        mssvInput.removeAttribute('required');
    }
};

loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorDiv = document.getElementById('login-error');

    errorDiv.classList.add('hidden');
    errorDiv.textContent = '';

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username, password })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Đăng nhập thất bại');
        }

        const data = await response.json();
        const token = data.access_token;
        const user = data.user;

        localStorage.setItem('token', token);

        currentUser = {
            username: user.username,
            mssv: user.mssv || user.username,
            name: user.full_name,
            role: user.role
        };

        userInfoDiv.innerHTML = `
            <span>${currentUser.name} (${currentUser.role})</span>
            <button onclick="logout()" class="btn-sm">Đăng xuất</button>
        `;

        if (currentUser.role === 'teacher' || currentUser.role === 'admin') {
            showView('view-teacher');
            loadTeacherRooms();
            startViolationPolling();
        } else {
            showView('view-student');
            loadStudentRooms();
        }
    } catch (err) {
        errorDiv.textContent = err.message;
        errorDiv.classList.remove('hidden');
    }
});

const registerForm = document.getElementById('registerForm');
registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fullName = document.getElementById('register-fullname').value.trim();
    const username = document.getElementById('register-username').value.trim();
    const password = document.getElementById('register-password').value;
    const role = document.getElementById('register-role').value;
    const mssv = document.getElementById('register-mssv').value.trim();
    const messageDiv = document.getElementById('register-message');

    messageDiv.classList.add('hidden');
    messageDiv.textContent = '';
    messageDiv.className = 'error-message hidden';

    try {
        const payload = {
            username,
            password,
            role,
            full_name: fullName
        };
        if (role === 'student') {
            payload.mssv = mssv;
        }

        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Đăng ký thất bại');
        }

        messageDiv.textContent = 'Đăng ký thành công! Hãy chuyển sang Đăng nhập.';
        messageDiv.className = 'error-message success-msg';
        registerForm.reset();
        window.toggleRegMssvField(); // Reset fields visibility
    } catch (err) {
        messageDiv.textContent = err.message;
        messageDiv.className = 'error-message';
    }
});

window.logout = () => {
    localStorage.removeItem('token');
    location.reload();
};

async function loadTeacherRooms() {
    const token = localStorage.getItem('token');
    if (!token) return;
    try {
        const response = await fetch('/api/rooms/teacher-rooms', {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (response.ok) {
            const data = await response.json();
            rooms = data.map(r => ({
                id: r.id,
                name: r.title,
                room_code: r.room_code,
                teacher: "Giảng viên"
            }));
        }
    } catch (err) {
        console.error("Lỗi tải phòng thi giảng viên:", err);
    }
    renderTeacherDashboard();
}

async function loadStudentRooms() {
    const token = localStorage.getItem('token');
    if (!token) return;
    try {
        const response = await fetch('/api/rooms/student-rooms', {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (response.ok) {
            const data = await response.json();
            rooms = data.map(r => ({
                id: r.id,
                name: r.title,
                room_code: r.room_code,
                teacher: "Giảng viên"
            }));
        }
    } catch (err) {
        console.error("Lỗi tải phòng thi sinh viên:", err);
    }
    renderStudentDashboard();
}

window.joinRoom = async (roomCode, roomTitle) => {
    if (!currentUser) return;
    const token = localStorage.getItem('token');
    if (!token) {
        alert("Vui lòng đăng nhập lại!");
        return;
    }

    try {
        const response = await fetch('/api/exam/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ room_code: roomCode })
        });

        if (response.ok) {
            const result = await response.json();
            currentRoomCode = roomCode;
            document.getElementById('current-room-title').textContent = roomTitle;
            document.getElementById('current-user-display').textContent = `MSSV: ${currentUser.mssv}`;
            showView('view-monitor');
            btnStop.disabled = false; // Bật nút Thoát phòng ngay khi vào phòng
            logConsole(`Đã tạo phiên thi thật trong DB (Mã: ${roomCode}). Hãy bật camera để bắt đầu.`, 'ok');
        } else {
            const err = await response.json();
            alert(`Lỗi vào phòng thi: ${err.detail || 'Bạn chưa được ghi danh trong phòng thi này.'}`);
        }
    } catch (e) {
        console.error("Lỗi kết nối khi bắt đầu thi:", e);
        alert("Không thể kết nối với server để bắt đầu phiên thi.");
    }
};

document.getElementById('createRoomForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById('room-name-input');
    const name = nameInput.value.trim();
    if (!name) return;

    const token = localStorage.getItem('token');
    if (!token) {
        alert("Vui lòng đăng nhập lại!");
        return;
    }

    // Generate a unique room code
    const roomCode = 'ROOM_' + Math.random().toString(36).substring(2, 8).toUpperCase();

    try {
        const response = await fetch('/api/rooms/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                room_code: roomCode,
                title: name,
                description: 'Phòng thi trực tuyến tự động tạo'
            })
        });

        if (response.ok) {
            nameInput.value = '';
            alert(`Đã tạo phòng thi: ${name} (Mã: ${roomCode})`);
            loadTeacherRooms();
        } else {
            const err = await response.json();
            alert(`Lỗi tạo phòng thi: ${err.detail || 'Không xác định'}`);
        }
    } catch (err) {
        console.error("Lỗi kết nối:", err);
        alert("Không thể kết nối với API tạo phòng thi.");
    }
});

function renderTeacherDashboard() {
    const list = document.getElementById('teacher-room-list');
    if (!list) return;
    list.innerHTML = rooms.map(room => `
        <div class="room-item-small">
            <span><strong>${room.name}</strong> (${room.room_code})</span>
            <span class="status-badge">Đang mở</span>
        </div>
    `).join('');
}

function renderStudentDashboard() {
    const list = document.getElementById('room-list');
    if (!list) return;
    list.innerHTML = rooms.map(room => `
        <div class="room-item">
            <h4>${room.name}</h4>
            <p>Mã phòng: <strong>${room.room_code}</strong></p>
            <button class="btn btn-primary" onclick="joinRoom('${room.room_code}', '${room.name}')">Vào thi ngay</button>
        </div>
    `).join('');
}

// --- GIÁM SÁT VI PHẠM (Dành cho Giảng viên) ---
function startViolationPolling() {
    if (violationPolling) clearInterval(violationPolling);
    refreshViolations();
    // Tự động cập nhật mỗi 5 giây
    violationPolling = setInterval(refreshViolations, 5000);
}

window.refreshViolations = async () => {
    try {
        const response = await fetch('/api/logs?limit=20');
        const result = await response.json();

        if (result.status === 'ok') {
            renderViolationLogs(result.data);
        }
    } catch (err) {
        console.error("Không thể tải log vi phạm:", err);
    }
};

function renderViolationLogs(logs) {
    const container = document.getElementById('teacher-violation-log');
    if (!container) return;

    if (!logs || logs.length === 0) {
        container.innerHTML = '<div class="log-entry">Chưa có dữ liệu giám sát nào.</div>';
        return;
    }

    container.innerHTML = logs.map(log => {
        const hasAlert = log.alerts && log.alerts.length > 0;
        const isCritical = log.alerts.includes('🚨') || log.alerts.includes('Unknown');
        const rowClass = isCritical ? 'log-danger' : (hasAlert ? 'log-warning' : 'log-ok');

        return `
            <div class="log-entry">
                <span class="log-time">[${log.timestamp.split(' ')[1]}]</span>
                <strong>MSSV: ${log.mssv}</strong> - 
                <span class="${rowClass}">${log.alerts || 'Bình thường'}</span>
            </div>
        `;
    }).join('');
}

// ==========================================
// 0. INIT MediaPipe Face Detector (client-side, lightweight)
// ==========================================
async function initFaceDetector() {
    try {
        const vision = await FilesetResolver.forVisionTasks(
            "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18/wasm"
        );
        faceDetector = await FaceDetector.createFromOptions(vision, {
            baseOptions: {
                modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
                delegate: "GPU",
            },
            runningMode: "VIDEO",
            minDetectionConfidence: 0.5,
        });
        logConsole("[System] Client-side face tracking loaded (real-time)", 'ok');
    } catch (e) {
        console.warn("MediaPipe Face Detector init failed, falling back to server-only:", e);
        logConsole("[System] Face tracking fallback: server-only (2s delay)", 'warning');
    }
}

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
    formData.append('photo', file);

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
            const errData = await response.json();
            enrollStatus.style.color = "red";
            enrollStatus.textContent = `Lỗi: ${errData.message || 'Không xác định'}`;
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
    if (!currentUser) {
        alert('Lỗi: Không tìm thấy thông tin thí sinh!');
        return;
    }
    const mssv = currentUser.mssv;

    // 1. Mở Webcam
    try {
        if (!stream) {
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            video.srcObject = stream;
            await video.play();
        }
    } catch (err) {
        logConsole('Không thể truy cập webcam!', 'danger');
        return;
    }

    // 2. Init client-side face tracking (nếu chưa)
    if (!faceDetector) {
        await initFaceDetector();
    }

    // 3. Chuyển đổi trạng thái UI
    isMonitoring = true;
    btnStart.disabled = true;
    btnStop.disabled = false;
    logConsole(`Bắt đầu giám sát MSSV: ${mssv}`, 'ok');

    // 4. Start real-time client-side face tracking loop
    startClientTracking();

    // 5. Set interval gửi server 2s/lần cho AI pipeline nặng
    monitorInterval = setInterval(() => captureAndSend(mssv), 2000);
});

btnStop.addEventListener('click', async () => {
    isMonitoring = false;
    clearInterval(monitorInterval);
    stopClientTracking();

    // Giải phóng tài nguyên camera nếu đang mở
    if (stream) {
        try {
            stream.getTracks().forEach(track => track.stop());
        } catch (e) {
            console.error("Lỗi giải phóng camera:", e);
        }
        stream = null;
    }
    if (video) {
        video.srcObject = null;
    }

    const token = localStorage.getItem('token');
    if (token) {
        try {
            await fetch('/api/exam/submit', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
        } catch (e) {
            console.error("Lỗi khi gửi kết thúc phiên thi:", e);
        }
    }

    currentRoomCode = null;
    btnStart.disabled = false;
    btnStop.disabled = true;
    lastServerIdentity = null;
    lastServerHeadPose = null;

    // Clear overlay
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    showView('view-student'); // Quay lại dashboard
    loadStudentRooms();       // Tải lại danh sách phòng

    logConsole('Đã dừng giám sát.', 'warning');
});

// ==========================================
// C. CLIENT-SIDE REAL-TIME FACE TRACKING (~30fps)
// ==========================================
function startClientTracking() {
    if (!faceDetector) return;

    function trackLoop() {
        if (!video.videoWidth || video.paused) {
            clientTrackingRAF = requestAnimationFrame(trackLoop);
            return;
        }

        // Sync overlay canvas size
        const displayW = video.clientWidth;
        const displayH = video.clientHeight;
        overlayCanvas.width = displayW;
        overlayCanvas.height = displayH;
        overlayCanvas.style.position = 'absolute';
        overlayCanvas.style.top = '0';
        overlayCanvas.style.left = '0';
        overlayCanvas.style.pointerEvents = 'none';

        overlayCtx.clearRect(0, 0, displayW, displayH);

        try {
            // MediaPipe detect trên video element trực tiếp
            const now = performance.now();
            const detections = faceDetector.detectForVideo(video, now);

            if (detections.detections.length > 0) {
                const face = detections.detections[0];
                const bb = face.boundingBox;

                // MediaPipe trả pixel coords trên video gốc, scale theo object-fit: cover
                const scale = Math.max(displayW / video.videoWidth, displayH / video.videoHeight);
                const scaledW = video.videoWidth * scale;
                const scaledH = video.videoHeight * scale;
                const offsetX = (scaledW - displayW) / 2;
                const offsetY = (scaledH - displayH) / 2;

                const x = bb.originX * scale - offsetX;
                const y = bb.originY * scale - offsetY;
                const w = bb.width * scale;
                const h = bb.height * scale;

                // Chọn màu dựa theo kết quả server gần nhất
                let primaryColor = '#facc15';
                let borderColor = 'rgba(250, 204, 21, 0.4)';
                let fillBgColor = 'rgba(250, 204, 21, 0.08)';
                let label = 'Đang xác minh...';

                if (lastServerIdentity) {
                    if (lastServerIdentity.status === 'Match') {
                        primaryColor = '#22c55e';
                        borderColor = 'rgba(34, 197, 94, 0.4)';
                        fillBgColor = 'rgba(34, 197, 94, 0.12)';
                        label = `${lastServerIdentity.name} (${(lastServerIdentity.similarity * 100).toFixed(1)}%)`;
                    } else if (lastServerIdentity.status === 'Unknown') {
                        primaryColor = '#ef4444';
                        borderColor = 'rgba(239, 68, 68, 0.4)';
                        fillBgColor = 'rgba(239, 68, 68, 0.12)';
                        label = `Sai người (${(lastServerIdentity.similarity * 100).toFixed(1)}%)`;
                    } else if (lastServerIdentity.status === 'Error') {
                        primaryColor = '#ef4444';
                        borderColor = 'rgba(239, 68, 68, 0.4)';
                        fillBgColor = 'rgba(239, 68, 68, 0.12)';
                        label = 'Chưa đăng ký';
                    } else if (lastServerIdentity.status === 'No Face') {
                        primaryColor = '#facc15';
                        borderColor = 'rgba(250, 204, 21, 0.4)';
                        fillBgColor = 'rgba(250, 204, 21, 0.08)';
                        label = 'Không thấy mặt (server)';
                    }
                }

                // 1. Vẽ nền trong suốt
                overlayCtx.fillStyle = fillBgColor;
                overlayCtx.fillRect(x, y, w, h);

                // 2. Vẽ viền mỏng
                overlayCtx.strokeStyle = borderColor;
                overlayCtx.lineWidth = 1.5;
                overlayCtx.strokeRect(x, y, w, h);

                // 3. Vẽ 4 góc màu đậm hơn
                const cornerLen = Math.min(20, w * 0.2, h * 0.2);
                overlayCtx.strokeStyle = primaryColor;
                overlayCtx.lineWidth = 4;
                overlayCtx.lineCap = 'round';
                overlayCtx.lineJoin = 'round';

                // Top-Left
                overlayCtx.beginPath();
                overlayCtx.moveTo(x + cornerLen, y);
                overlayCtx.lineTo(x, y);
                overlayCtx.lineTo(x, y + cornerLen);
                overlayCtx.stroke();

                // Top-Right
                overlayCtx.beginPath();
                overlayCtx.moveTo(x + w - cornerLen, y);
                overlayCtx.lineTo(x + w, y);
                overlayCtx.lineTo(x + w, y + cornerLen);
                overlayCtx.stroke();

                // Bottom-Left
                overlayCtx.beginPath();
                overlayCtx.moveTo(x, y + h - cornerLen);
                overlayCtx.lineTo(x, y + h);
                overlayCtx.lineTo(x + cornerLen, y + h);
                overlayCtx.stroke();

                // Bottom-Right
                overlayCtx.beginPath();
                overlayCtx.moveTo(x + w - cornerLen, y + h);
                overlayCtx.lineTo(x + w, y + h);
                overlayCtx.lineTo(x + w, y + h - cornerLen);
                overlayCtx.stroke();

                // Vẽ label nền
                overlayCtx.font = 'bold 14px Inter, sans-serif';
                const textW = overlayCtx.measureText(label).width;
                overlayCtx.fillStyle = primaryColor;
                overlayCtx.fillRect(x, y - 22, textW + 12, 22);

                // Vẽ text
                overlayCtx.fillStyle = '#ffffff';
                overlayCtx.fillText(label, x + 6, y - 6);

                // Vẽ Head Pose info (Yaw/Pitch/Roll) bên dưới bbox
                if (lastServerHeadPose) {
                    const hp = lastServerHeadPose;
                    const poseColor = hp.alert ? '#f59e0b' : '#22c55e';
                    const poseText = `Y:${hp.yaw.toFixed(1)}° P:${hp.pitch.toFixed(1)}° R:${hp.roll.toFixed(1)}°`;

                    overlayCtx.font = 'bold 12px JetBrains Mono, monospace';
                    const poseTextW = overlayCtx.measureText(poseText).width;
                    overlayCtx.fillStyle = poseColor;
                    overlayCtx.globalAlpha = 0.85;
                    overlayCtx.fillRect(x, y + h + 2, poseTextW + 12, 20);
                    overlayCtx.globalAlpha = 1.0;
                    overlayCtx.fillStyle = '#000';
                    overlayCtx.fillText(poseText, x + 6, y + h + 16);
                }
            }
        } catch (e) {
            // Silently ignore detection errors to keep loop running
        }

        clientTrackingRAF = requestAnimationFrame(trackLoop);
    }

    clientTrackingRAF = requestAnimationFrame(trackLoop);
}

function stopClientTracking() {
    if (clientTrackingRAF) {
        cancelAnimationFrame(clientTrackingRAF);
        clientTrackingRAF = null;
    }
}

// ==========================================
// D. SERVER-SIDE AI PIPELINE (2s interval)
// ==========================================
async function captureAndSend(mssv) {
    if (!video.videoWidth) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const base64Frame = canvas.toDataURL('image/jpeg', 0.7);

    try {
        const response = await fetch('/api/process_frame', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mssv: mssv, frame: base64Frame })
        });

        const data = await response.json();

        // Cập nhật identity result cho client-side tracking sử dụng
        lastServerIdentity = data.identity;
        lastServerHeadPose = data.head_pose || null;

        // Tổng số vi phạm tích lũy trong phiên hiện tại
        const totalViolations = data.violation_count || 0;

        // NẾU NGƯỜI DÙNG ĐÃ ẤN STOP TRONG LÚC ĐANG CHỜ API TRẢ VỀ, BỎ QUA KẾT QUẢ NÀY
        if (!isMonitoring) return;

        // Nếu KHÔNG có client-side tracker → fallback vẽ bbox từ server
        if (!faceDetector) {
            drawFaceBboxFallback(data.identity);
        }

        // Hiển thị log
        if (data.alerts && data.alerts.length > 0) {
            data.alerts.forEach(alertText => {
                // Phân loại màu theo nội dung alert
                let type = 'ok';
                if (alertText.includes('🚨')) type = 'danger';
                if (alertText.includes('⚠️')) type = 'warning';
                if (alertText.includes('❌')) type = 'danger';
                if (alertText.includes('✅')) type = 'ok';

                // Thông báo vi phạm tích lũy → dùng màu theo cấp độ
                if (alertText.startsWith('HỆ THỐNG:') && alertText.includes('vi phạm')) {
                    type = getViolationColorType(totalViolations);
                }

                logConsole(alertText, type);
            });
        } else {
            logConsole('Frame nhận thành công nhưng không có kết quả AI.', 'warning');
        }

    } catch (error) {
        if (isMonitoring) {
            logConsole('Lỗi gửi frame! Server timeout hoặc down.', 'danger');
        }
    }
}

// ==========================================
// E. FALLBACK: Server-only bbox rendering (khi MediaPipe JS fail)
// ==========================================
function drawFaceBboxFallback(identity) {
    const displayW = video.clientWidth;
    const displayH = video.clientHeight;
    overlayCanvas.width = displayW;
    overlayCanvas.height = displayH;
    overlayCanvas.style.position = 'absolute';
    overlayCanvas.style.top = '0';
    overlayCanvas.style.left = '0';
    overlayCanvas.style.pointerEvents = 'none';

    overlayCtx.clearRect(0, 0, displayW, displayH);

    if (!identity || !identity.face_bbox) return;

    const bbox = identity.face_bbox;
    const scale = Math.max(displayW / video.videoWidth, displayH / video.videoHeight);
    const scaledW = video.videoWidth * scale;
    const scaledH = video.videoHeight * scale;
    const offsetX = (scaledW - displayW) / 2;
    const offsetY = (scaledH - displayH) / 2;

    const x = bbox.x1 * scaledW - offsetX;
    const y = bbox.y1 * scaledH - offsetY;
    const w = (bbox.x2 - bbox.x1) * scaledW;
    const h = (bbox.y2 - bbox.y1) * scaledH;

    let primaryColor = '#facc15';
    let borderColor = 'rgba(250, 204, 21, 0.4)';
    let fillBgColor = 'rgba(250, 204, 21, 0.08)';
    let label = 'Đang xác minh...';

    if (identity) {
        if (identity.status === 'Match') {
            primaryColor = '#22c55e';
            borderColor = 'rgba(34, 197, 94, 0.4)';
            fillBgColor = 'rgba(34, 197, 94, 0.12)';
            label = `${identity.name} (${(identity.similarity * 100).toFixed(1)}%)`;
        } else if (identity.status === 'Unknown') {
            primaryColor = '#ef4444';
            borderColor = 'rgba(239, 68, 68, 0.4)';
            fillBgColor = 'rgba(239, 68, 68, 0.12)';
            label = `Sai người (${(identity.similarity * 100).toFixed(1)}%)`;
        } else if (identity.status === 'Error') {
            primaryColor = '#ef4444';
            borderColor = 'rgba(239, 68, 68, 0.4)';
            fillBgColor = 'rgba(239, 68, 68, 0.12)';
            label = 'Chưa đăng ký';
        }
    }

    // 1. Vẽ nền trong suốt
    overlayCtx.fillStyle = fillBgColor;
    overlayCtx.fillRect(x, y, w, h);

    // 2. Vẽ viền mỏng
    overlayCtx.strokeStyle = borderColor;
    overlayCtx.lineWidth = 1.5;
    overlayCtx.strokeRect(x, y, w, h);

    // 3. Vẽ 4 góc màu đậm hơn
    const cornerLen = Math.min(20, w * 0.2, h * 0.2);
    overlayCtx.strokeStyle = primaryColor;
    overlayCtx.lineWidth = 4;
    overlayCtx.lineCap = 'round';
    overlayCtx.lineJoin = 'round';

    // Top-Left
    overlayCtx.beginPath();
    overlayCtx.moveTo(x + cornerLen, y);
    overlayCtx.lineTo(x, y);
    overlayCtx.lineTo(x, y + cornerLen);
    overlayCtx.stroke();

    // Top-Right
    overlayCtx.beginPath();
    overlayCtx.moveTo(x + w - cornerLen, y);
    overlayCtx.lineTo(x + w, y);
    overlayCtx.lineTo(x + w, y + cornerLen);
    overlayCtx.stroke();

    // Bottom-Left
    overlayCtx.beginPath();
    overlayCtx.moveTo(x, y + h - cornerLen);
    overlayCtx.lineTo(x, y + h);
    overlayCtx.lineTo(x + cornerLen, y + h);
    overlayCtx.stroke();

    // Bottom-Right
    overlayCtx.beginPath();
    overlayCtx.moveTo(x + w - cornerLen, y + h);
    overlayCtx.lineTo(x + w, y + h);
    overlayCtx.lineTo(x + w, y + h - cornerLen);
    overlayCtx.stroke();

    overlayCtx.font = 'bold 14px Inter, sans-serif';
    const textW = overlayCtx.measureText(label).width;
    overlayCtx.fillStyle = primaryColor;
    overlayCtx.fillRect(x, y - 22, textW + 12, 22);

    overlayCtx.fillStyle = '#ffffff';
    overlayCtx.fillText(label, x + 6, y - 6);
}

// ==========================================
// F. CONSOLE LOG RENDERING
// ==========================================

/**
 * Map số vi phạm tích lũy → CSS class màu cấp độ.
 *   1-3  → violation-low    (trắng mặc định)
 *   4-6  → violation-medium (vàng cảnh báo)
 *   7-9  → violation-high   (cam đậm)
 *   10+  → violation-critical (đỏ + pulse)
 */
function getViolationColorType(count) {
    if (count >= 10) return 'violation-critical';
    if (count >= 7)  return 'violation-high';
    if (count >= 4)  return 'violation-medium';
    return 'violation-low';
}

function logConsole(message, type = 'ok') {

    const timeStr = new Date().toLocaleTimeString('vi-VN');

    const div = document.createElement('div');
    div.className = 'log-entry';
    div.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-${type}">${message}</span>`;

    consoleLog.appendChild(div);
    consoleWrapper.scrollTop = consoleWrapper.scrollHeight;
}

// ==========================================
// G. PERSISTED SESSION CHECK (ON STARTUP)
// ==========================================
async function checkPersistedSession() {
    const token = localStorage.getItem('token');
    if (!token) return;

    const viewAuth = document.getElementById('view-auth');
    const authCard = document.querySelector('.auth-card');

    // Create and append loading indicator
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'auth-loading';
    loadingDiv.style.cssText = "padding: 3rem; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 1rem; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: var(--border-radius); max-width: 420px; margin: 4rem auto; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.04);";
    loadingDiv.innerHTML = `
        <div class="spinner" style="width: 40px; height: 40px; border: 4px solid var(--border-color); border-top-color: var(--primary-color); border-radius: 50%; animation: spin 1s linear infinite;"></div>
        <p style="font-weight: 600; color: var(--text-muted); margin: 0;">Đang xác thực phiên đăng nhập...</p>
    `;

    if (authCard) authCard.style.display = 'none';
    if (viewAuth) viewAuth.appendChild(loadingDiv);

    try {
        const response = await fetch('/api/auth/me', {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Session expired');
        }

        const user = await response.json();
        currentUser = {
            username: user.username,
            mssv: user.mssv || user.username,
            name: user.full_name,
            role: user.role
        };

        userInfoDiv.innerHTML = `
            <span>${currentUser.name} (${currentUser.role})</span>
            <button onclick="logout()" class="btn-sm">Đăng xuất</button>
        `;

        if (currentUser.role === 'teacher' || currentUser.role === 'admin') {
            showView('view-teacher');
            loadTeacherRooms();
            startViolationPolling();
        } else {
            showView('view-student');
            loadStudentRooms();
        }
    } catch (err) {
        console.warn("Session validation failed:", err);
        localStorage.removeItem('token');
        if (loadingDiv) loadingDiv.remove();
        if (authCard) authCard.style.display = '';
    }
}

// Run persisted session check on startup
checkPersistedSession();

// Gắn nút "Làm mới danh sách" vi phạm cho giảng viên (thay vì onclick inline không hoạt động với ES module)
document.getElementById('btn-refresh-violations')?.addEventListener('click', () => {
    refreshViolations();
});