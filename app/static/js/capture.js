// Student registration / re-capture: grabs webcam frames in the browser and
// POSTs them (base64 JPEG) to the server, which computes face encodings.
// Doing capture client-side means registration works from any device with a
// camera — not just the machine physically wired to the classroom webcam.
(function () {
  const app = document.getElementById('capture-app');
  if (!app) return;

  const TARGET = parseInt(app.dataset.targetImages, 10) || 12;
  const ENDPOINT = app.dataset.endpoint;
  const IS_REGISTER = app.dataset.mode === 'register';
  const CAPTURE_INTERVAL_MS = 450; // slight pose change between shots

  const video = document.getElementById('cam-preview');
  const thumbs = document.getElementById('thumbs');
  const progress = document.getElementById('capture-progress');
  const alertBox = document.getElementById('capture-alert');
  const btnCapture = document.getElementById('btn-capture');
  const btnSubmit = document.getElementById('btn-submit');
  const submitSpinner = document.getElementById('submit-spinner');

  const images = [];

  function showAlert(message) {
    alertBox.textContent = message;
    alertBox.classList.remove('d-none');
  }

  function hideAlert() { alertBox.classList.add('d-none'); }

  // ------------------------------------------------------------- camera init
  async function initCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      video.srcObject = stream;
      btnCapture.disabled = false;
    } catch (err) {
      showAlert('Webcam access denied or unavailable: ' + err.message);
    }
  }

  // ---------------------------------------------------------------- capture
  function grabFrame() {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.85);
  }

  function addThumb(dataUrl) {
    const img = document.createElement('img');
    img.src = dataUrl;
    thumbs.appendChild(img);
  }

  btnCapture.addEventListener('click', () => {
    hideAlert();
    images.length = 0;
    thumbs.innerHTML = '';
    btnCapture.disabled = true;
    btnSubmit.disabled = true;

    const timer = setInterval(() => {
      if (!video.videoWidth) return; // stream not ready yet
      const frame = grabFrame();
      images.push(frame);
      addThumb(frame);
      progress.style.width = `${(images.length / TARGET) * 100}%`;

      if (images.length >= TARGET) {
        clearInterval(timer);
        btnCapture.disabled = false;
        btnCapture.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i> Retake photos';
        btnSubmit.disabled = false;
      }
    }, CAPTURE_INTERVAL_MS);
  });

  // ----------------------------------------------------------------- submit
  btnSubmit.addEventListener('click', async () => {
    hideAlert();

    const payload = { images };
    if (IS_REGISTER) {
      payload.full_name = document.getElementById('f-full-name').value.trim();
      payload.roll_number = document.getElementById('f-roll').value.trim();
      payload.department = document.getElementById('f-dept').value.trim();
      payload.year = document.getElementById('f-year').value;
      if (!payload.full_name || !payload.roll_number || !payload.department) {
        showAlert('Fill in all student details before saving.');
        return;
      }
    }

    btnSubmit.disabled = true;
    submitSpinner.classList.remove('d-none');
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await res.json();
      if (body.ok) {
        window.location.href = body.redirect;
      } else {
        showAlert(body.error || 'Registration failed.');
        btnSubmit.disabled = false;
      }
    } catch (err) {
      showAlert('Could not reach the server: ' + err.message);
      btnSubmit.disabled = false;
    } finally {
      submitSpinner.classList.add('d-none');
    }
  });

  initCamera();
})();
