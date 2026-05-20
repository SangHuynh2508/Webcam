// ==========================================
// IMPORTS — MediaPipe Vision (client-side face tracking)
// ==========================================
import { FaceDetector, FilesetResolver } from
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18";

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
let rooms = [
    { id: 1, name: "Thi giữa kỳ môn AI", teacher: "Admin" },
    { id: 2, name: "Kiểm tra lập trình Web", teacher: "Admin" }
];
let violationPolling = null;

// --- Client-side face tracking state ---
let faceDetector = null;
let clientTrackingRAF = null;  // requestAnimationFrame ID
let lastServerIdentity = null; // Latest identity result from server
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
    event.target.classList.add('active');
};

loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const mssv = document.getElementById('login-mssv').value;
    const role = document.getElementById('login-role').value;

    // Giả lập Login
    currentUser = { mssv: mssv, name: "Thí sinh " + mssv, role: role };
    
    userInfoDiv.innerHTML = `
        <span>${currentUser.name} (${role})</span>
        <button onclick="logout()" class="btn-sm">Đăng xuất</button>
    `;

    if (role === 'teacher') {
        showView('view-teacher');
        renderTeacherDashboard();
        startViolationPolling();
    } else {
        showView('view-student');
        renderStudentDashboard();
    }
});

window.logout = () => {
    location.reload();
};

window.joinRoom = (roomName) => {
    if (!currentUser) return;
    document.getElementById('current-room-title').textContent = roomName;
    document.getElementById('current-user-display').textContent = `MSSV: ${currentUser.mssv}`;
    showView('view-monitor');
};

document.getElementById('createRoomForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const nameInput = document.getElementById('room-name-input');
    const name = nameInput.value;
    
    const newRoom = {
        id: Date.now(),
        name: name,
        teacher: currentUser.name
    };
    
    rooms.push(newRoom);
    nameInput.value = '';
    renderTeacherDashboard();
    alert(`Đã tạo bài thi: ${name}`);
});

function renderTeacherDashboard() {
    const list = document.getElementById('teacher-room-list');
    if (!list) return;
    list.innerHTML = rooms.map(room => `
        <div class="room-item-small">
            <span><strong>${room.name}</strong></span>
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
            <p>Giảng viên: ${room.teacher}</p>
            <button class="btn btn-primary" onclick="joinRoom('${room.name}')">Vào thi ngay</button>
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

btnStop.addEventListener('click', () => {
    isMonitoring = false;
    clearInterval(monitorInterval);
    stopClientTracking();

    btnStart.disabled = false;
    btnStop.disabled = true;
    lastServerIdentity = null;

    // Clear overlay
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    
    showView('view-student'); // Quay lại dashboard

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

                // MediaPipe trả pixel coords trên video gốc, cần scale sang display size
                const scaleX = displayW / video.videoWidth;
                const scaleY = displayH / video.videoHeight;

                const x = bb.originX * scaleX;
                const y = bb.originY * scaleY;
                const w = bb.width * scaleX;
                const h = bb.height * scaleY;

                // Chọn màu dựa theo kết quả server gần nhất
                let color = '#facc15'; // Vàng mặc định (chưa có kết quả)
                let label = 'Đang xác minh...';

                if (lastServerIdentity) {
                    if (lastServerIdentity.status === 'Match') {
                        color = '#22c55e'; // Xanh lá
                        label = `${lastServerIdentity.name} (${(lastServerIdentity.similarity * 100).toFixed(1)}%)`;
                    } else if (lastServerIdentity.status === 'Unknown') {
                        color = '#ef4444'; // Đỏ
                        label = `Sai người (${(lastServerIdentity.similarity * 100).toFixed(1)}%)`;
                    } else if (lastServerIdentity.status === 'Error') {
                        color = '#ef4444';
                        label = 'Chưa đăng ký';
                    } else if (lastServerIdentity.status === 'No Face') {
                        color = '#facc15';
                        label = 'Không thấy mặt (server)';
                    }
                }

                // Vẽ bbox
                overlayCtx.strokeStyle = color;
                overlayCtx.lineWidth = 3;
                overlayCtx.strokeRect(x, y, w, h);

                // Vẽ label nền
                overlayCtx.font = 'bold 14px Inter, sans-serif';
                const textW = overlayCtx.measureText(label).width;
                overlayCtx.fillStyle = color;
                overlayCtx.fillRect(x, y - 22, textW + 12, 22);

                // Vẽ text
                overlayCtx.fillStyle = '#000';
                overlayCtx.fillText(label, x + 6, y - 6);
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
        
        // NẾU NGƯỜI DÙNG ĐÃ ẤN STOP TRONG LÚC ĐANG CHỜ API TRẢ VỀ, BỎ QUA KẾT QUẢ NÀY
        if (!isMonitoring) return;

        // Nếu KHÔNG có client-side tracker → fallback vẽ bbox từ server
        if (!faceDetector) {
            drawFaceBboxFallback(data.identity);
        }

        // Hiển thị log
        if (data.alerts && data.alerts.length > 0) {
            data.alerts.forEach(alertText => {
                let type = 'ok';
                if (alertText.includes('🚨')) type = 'danger';
                if (alertText.includes('⚠️')) type = 'warning';
                if (alertText.includes('❌')) type = 'danger';
                if (alertText.includes('✅')) type = 'ok';
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
    const x = bbox.x1 * displayW;
    const y = bbox.y1 * displayH;
    const w = (bbox.x2 - bbox.x1) * displayW;
    const h = (bbox.y2 - bbox.y1) * displayH;

    let color = '#facc15';
    if (identity.status === 'Match') color = '#22c55e';
    if (identity.status === 'Unknown') color = '#ef4444';
    if (identity.status === 'Error') color = '#ef4444';

    overlayCtx.strokeStyle = color;
    overlayCtx.lineWidth = 3;
    overlayCtx.strokeRect(x, y, w, h);

    const label = `${identity.name} (${(identity.similarity * 100).toFixed(1)}%)`;
    overlayCtx.font = 'bold 14px Inter, sans-serif';
    const textW = overlayCtx.measureText(label).width;
    overlayCtx.fillStyle = color;
    overlayCtx.fillRect(x, y - 22, textW + 12, 22);

    overlayCtx.fillStyle = '#000';
    overlayCtx.fillText(label, x + 6, y - 6);
}

// ==========================================
// F. CONSOLE LOG RENDERING
// ==========================================
function logConsole(message, type = 'ok') {
    const timeStr = new Date().toLocaleTimeString('vi-VN');
    
    const div = document.createElement('div');
    div.className = 'log-entry';
    div.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-${type}">${message}</span>`;
    
    consoleLog.appendChild(div);
    consoleWrapper.scrollTop = consoleWrapper.scrollHeight;
}