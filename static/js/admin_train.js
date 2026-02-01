async function captureAndTrain(username, count = 6) {
  try {
    // Request camera with proper constraints
    const constraints = {
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        facingMode: 'user'
      }
    };

    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    
    // Create hidden video element
    const video = document.createElement('video');
    video.style.display = 'none';
    video.autoplay = true;
    video.playsInline = true;
    document.body.appendChild(video);
    
    video.srcObject = stream;
    
    // Wait for video to start playing
    await new Promise(resolve => {
      video.onloadedmetadata = () => {
        video.play();
        resolve();
      };
    });
    
    await new Promise(r => setTimeout(r, 500));
    
    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 480;
    const ctx = canvas.getContext('2d');
    
    const frames = [];
    
    for (let i = 0; i < count; i++) {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      frames.push(canvas.toDataURL('image/jpeg', 0.85));
      
      // Delay between captures
      await new Promise(r => setTimeout(r, 400));
    }
    
    // Stop all tracks
    stream.getTracks().forEach(t => t.stop());
    document.body.removeChild(video);
    
    // Send frames to server
    const res = await fetch('/api/train', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username, frames: frames })
    });
    
    const result = await res.json();
    return result;
  } catch (error) {
    console.error('Training error:', error);
    
    let errorMsg = 'Camera Error';
    let errorDetail = '';
    
    if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
      errorMsg = 'Camera Permission Denied';
      errorDetail = 'Please allow camera access and try again.';
    } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
      errorMsg = 'No Camera Found';
      errorDetail = 'Please connect a camera device.';
    } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
      errorMsg = 'Camera in Use';
      errorDetail = 'Another application is using the camera.';
    } else if (error.name === 'TypeError') {
      errorMsg = 'Browser Error';
      errorDetail = 'Your browser may not support camera access.';
    }
    
    return {
      ok: false,
      error: `${errorMsg}: ${errorDetail}`
    };
  }
}
