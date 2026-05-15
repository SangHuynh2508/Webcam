// ==========================================
// IMPORTS — MediaPipe Vision (client-side face tracking)
// ==========================================
import { FaceDetector, FilesetResolver } from
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18";

// --- DOM Elements ---
const enrollForm = document.getElementById('enrollForm');
const enrollStatus = document.getElementById('enroll-status');

const video = document.getElementById('webcam');
const canvas = document.getElementById('hidden-canvas');
const ctx = canvas.getContext('2d');
const overlayCanvas = document.getElementById('overlay-canvas');
const overlayCtx = overlayCanvas.getContext('2d');
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const inputMonMssv = document.getElementById('mon-mssv');
const consoleLog = document.getElementById('console-log');
const consoleWrapper = document.getElementById('console-wrapper');

let stream = null;
let monitorInterval = null;

// --- Client-side face tracking state ---
let faceDetector = null;
let clientTrackingRAF = null;  // requestAnimationFrame ID
let lastServerIdentity = null; // Latest identity result from server

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
    btnStart.disabled = true;
    btnStop.disabled = false;
    inputMonMssv.disabled = true;
    logConsole(`Bắt đầu giám sát MSSV: ${mssv}`, 'ok');

    // 4. Start real-time client-side face tracking loop
    startClientTracking();

    // 5. Set interval gửi server 2s/lần cho AI pipeline nặng
    monitorInterval = setInterval(() => captureAndSend(mssv), 2000);
});

btnStop.addEventListener('click', () => {
    clearInterval(monitorInterval);
    stopClientTracking();

    btnStart.disabled = false;
    btnStop.disabled = true;
    inputMonMssv.disabled = false;
    lastServerIdentity = null;

    // Clear overlay
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

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
        logConsole('Lỗi gửi frame! Server timeout hoặc down.', 'danger');
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