let streamRef = null;

function startRecognition(subject, onResult) {
  const container = document.getElementById('videoContainer');
  container.innerHTML = '';
  
  const video = document.createElement('video');
  video.autoplay = true;
  video.playsInline = true;
  video.style.width = '100%';
  video.style.height = '100%';
  container.appendChild(video);

  // Request camera with proper constraints
  const constraints = {
    video: {
      width: { ideal: 640 },
      height: { ideal: 480 },
      facingMode: 'user'
    }
  };

  navigator.mediaDevices.getUserMedia(constraints)
    .then(stream => {
      streamRef = stream;
      video.srcObject = stream;
      
      const canvas = document.createElement('canvas');
      canvas.width = 640;
      canvas.height = 480;
      const ctx = canvas.getContext('2d');
      
      let running = true;
      let recognitionInProgress = false;
      
      async function loop() {
        if (!running) return;
        
        try {
          // Draw video frame to canvas
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
          
          // Only send one request at a time
          if (!recognitionInProgress) {
            recognitionInProgress = true;
            
            const res = await fetch('/api/recognize', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ frame: dataUrl, subject: subject })
            });
            
            const j = await res.json();
            recognitionInProgress = false;

            // New response format: { ok: true, results: [ { marked: true|false, username, dist, ... }, ... ] }
            if (j && Array.isArray(j.results)) {
              // If any face was marked true, stop and return that result
              const marked = j.results.find(r => r.marked === true);
              if (marked) {
                running = false;
                streamRef.getTracks().forEach(t => t.stop());
                if (onResult) onResult(marked);
                return;
              }

              // If any face was already marked in DB, show a popup notification
              const alreadyMarked = j.results.find(r => r.reason === 'already_marked_db');
              if (alreadyMarked) {
                try {
                  // Show a modal that requires the teacher to click OK to proceed to next
                  await showAlreadyMarkedModal(alreadyMarked.username || alreadyMarked.name, subject);
                } catch (e) {
                  console.warn('Already-marked modal failed:', e);
                }
                // continue recognition for other faces after OK
              }

              // If any low-confidence matches were returned, log and optionally show UI
              const low = j.results.find(r => r.reason === 'low_confidence' || r.reason === 'accept_fallback');
              if (low) {
                console.warn('Low-confidence match:', low);
                // show a confirmation modal to the teacher/admin
                showConfirmation(low.username || low.name, low.dist, subject, async (confirmed) => {
                  if (confirmed) {
                    try {
                      const headers = { 'Content-Type': 'application/json' };
                      if (window && window.CSRF_TOKEN) headers['X-CSRFToken'] = window.CSRF_TOKEN;
                      const res = await fetch('/api/confirm_mark', {
                        method: 'POST',
                        headers: headers,
                        body: JSON.stringify({ username: low.username || low.name, subject })
                      });
                      const body = await res.json();
                      if (body && body.marked) {
                        running = false;
                        streamRef.getTracks().forEach(t => t.stop());
                        if (onResult) onResult(body);
                        return;
                      } else {
                        console.warn('Confirm mark failed or already marked', body);
                      }
                    } catch (err) {
                      console.error('Confirm mark request failed', err);
                    }
                  } else {
                    // teacher rejected, continue recognition
                    console.log('Manual rejection; continuing recognition');
                  }
                });
              }
            } else {
              // fallback for older format
              if (j.marked) {
                running = false;
                streamRef.getTracks().forEach(t => t.stop());
                if (onResult) onResult(j);
                return;
              }
            }
          }
        } catch (e) {
          console.error('Recognition error:', e);
          recognitionInProgress = false;
        }
        
        // run more frequently for active recognition
        setTimeout(loop, 400);
      }
      
      loop();
    })
    .catch(error => {
      console.error('Camera permission error:', error);
      
      let errorMsg = '❌ Camera Access Denied';
      let errorDetail = '';
      
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        errorMsg = '❌ Camera Permission Denied';
        errorDetail = 'Please allow camera access in your browser settings.';
      } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
        errorMsg = '❌ No Camera Found';
        errorDetail = 'Please connect a camera device.';
      } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
        errorMsg = '❌ Camera in Use';
        errorDetail = 'Another application is using the camera.';
      }
      
      const log = document.getElementById('log');
      if (log) {
        log.innerHTML = `<div style="color: #721c24;">${errorMsg}<br><small>${errorDetail}</small></div>`;
      }
      
      alert(`${errorMsg}\n\n${errorDetail}\n\nTo fix this:\n1. Check browser permissions\n2. Go to browser settings\n3. Allow camera access for this site\n4. Refresh the page`);
    });
}

// Create and show a simple confirmation modal. Calls callback(true) if accepted, callback(false) if rejected.
function showConfirmation(username, dist, subject, callback) {
  // Avoid duplicate modals
  if (document.getElementById('recog-confirm-modal')) return;

  const overlay = document.createElement('div');
  overlay.id = 'recog-confirm-modal';
  Object.assign(overlay.style, {
    position: 'fixed', left: 0, top: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
  });

  const box = document.createElement('div');
  Object.assign(box.style, { background: '#fff', padding: '18px', borderRadius: '8px', width: '320px', textAlign: 'center' });
  box.innerHTML = `<h3 style="margin:0 0 8px;">Confirm Attendance</h3>
                   <p style="margin:0 0 10px;">Possible match: <strong>${username}</strong></p>
                   <p style="margin:0 0 12px; font-size:12px; color:#555;">Distance: ${dist ? dist.toFixed(3) : 'N/A'}</p>`;

  const btnAccept = document.createElement('button');
  btnAccept.textContent = 'Confirm';
  Object.assign(btnAccept.style, { marginRight: '8px', padding: '8px 12px' });
  const btnReject = document.createElement('button');
  btnReject.textContent = 'Reject';
  Object.assign(btnReject.style, { padding: '8px 12px' });

  btnAccept.addEventListener('click', () => { document.body.removeChild(overlay); callback(true); });
  btnReject.addEventListener('click', () => { document.body.removeChild(overlay); callback(false); });

  box.appendChild(btnAccept);
  box.appendChild(btnReject);
  overlay.appendChild(box);
  document.body.appendChild(overlay);
}

// Modal for already-marked notification that requires the teacher to click OK to continue
function showAlreadyMarkedModal(username, subject) {
  return new Promise((resolve) => {
    // Avoid duplicate modals
    if (document.getElementById('recog-already-modal')) return resolve();

    const overlay = document.createElement('div');
    overlay.id = 'recog-already-modal';
    Object.assign(overlay.style, {
      position: 'fixed', left: 0, top: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
    });

    const box = document.createElement('div');
    Object.assign(box.style, { background: '#fff', padding: '18px', borderRadius: '8px', width: '360px', textAlign: 'center' });
    box.innerHTML = `<h3 style="margin:0 0 8px;">Already Marked</h3>
                     <p style="margin:0 0 10px;">User <strong>${username}</strong> is already marked present for <strong>${subject}</strong> today.</p>
                     <p style="margin:0 0 12px; font-size:13px; color:#555;">Click <strong>OK</strong> to continue to the next student.</p>`;

    const btnOk = document.createElement('button');
    btnOk.textContent = 'OK';
    Object.assign(btnOk.style, { padding: '8px 14px' });
    btnOk.addEventListener('click', () => { document.body.removeChild(overlay); resolve(); });

    box.appendChild(btnOk);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
  });
}
