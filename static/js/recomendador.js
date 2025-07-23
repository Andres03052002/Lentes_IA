/* recomendador.js MEJORADO CON TODAS LAS MEJORAS (3D, normalización, filtro, UX mejorada) */

const htmlEl = document.documentElement;
document.getElementById('toggleDark')?.addEventListener('click', () => {
  htmlEl.classList.toggle('dark');
  document.getElementById('sunmoon').textContent = htmlEl.classList.contains('dark') ? '☀️' : '🌙';
});

const video         = document.getElementById('video');
const overlay       = document.getElementById('overlay');
const ctxOv         = overlay.getContext('2d');
const rostroInfo    = document.getElementById('rostroInfo');
const btnRecomendar = document.getElementById('btnRecomendar');
const gridGafas     = document.querySelector('#gridGafas .swiper-wrapper');
const gridGafasMobile = document.getElementById('gridGafasMobile');
const spinner       = document.getElementById('spinner');
const genero        = document.getElementById('genero');
const actividad     = document.getElementById('actividad');
let faceType        = null;
let lastUserId      = null;
let swiperInstance  = null;
let stableCounter   = 0;
const STABILITY_THRESHOLD = 10;
const MAX_FACE_ANGLE = 15;

function calcFaceType(landmarks, w, h) {
  const dist = (a, b) => Math.hypot((landmarks[a].x - landmarks[b].x), (landmarks[a].y - landmarks[b].y), (landmarks[a].z - landmarks[b].z));
  const interocular = dist(33, 263) + 1e-6;
  const norm = (a, b) => dist(a, b) / interocular;

  const lengthNorm     = norm(10, 152);
  const cheekWidth     = (norm(93, 323) + norm(323, 93)) / 2;
  const foreheadWidth  = (norm(10, 127) + norm(10, 356)) / 2;
  const mandibulaWidth = norm(234, 454);
  const aspectRatio    = lengthNorm / cheekWidth;

  if (aspectRatio > 1.65 && foreheadWidth < cheekWidth) return "Alargado";
  if (Math.abs(cheekWidth - mandibulaWidth) < 0.05 && Math.abs(cheekWidth - foreheadWidth) < 0.05) return "Cuadrado";
  if (aspectRatio < 1.1 && cheekWidth > foreheadWidth && cheekWidth > mandibulaWidth) return "Redondo";
  if (foreheadWidth > mandibulaWidth && foreheadWidth > cheekWidth) return "Corazón";
  if (cheekWidth > foreheadWidth && cheekWidth > mandibulaWidth) return "Diamante";
  if (mandibulaWidth > foreheadWidth && aspectRatio > 1.2) return "Triangular";
  return "Ovalado";
}

function getFaceRotation(lm) {
  const noseTip = lm[1];
  const leftEye = lm[33];
  const rightEye = lm[263];
  const dx = rightEye.x - leftEye.x;
  const dy = rightEye.y - leftEye.y;
  const angle = Math.atan2(dy, dx) * (180 / Math.PI);
  return Math.abs(angle);
}

const faceMesh = new FaceMesh({ locateFile: (f) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${f}` });
faceMesh.setOptions({ selfieMode: true, maxNumFaces: 1, refineLandmarks: true, minDetectionConfidence: 0.7, minTrackingConfidence: 0.7 });

faceMesh.onResults((res) => {
  if (!res.multiFaceLandmarks.length) {
    stableCounter = 0;
    rostroInfo.textContent = "📡 Analizando rostro…";
    btnRecomendar.disabled = true;
    return;
  }

  const lm = res.multiFaceLandmarks[0];
  const w = video.videoWidth, h = video.videoHeight;
  const rotation = getFaceRotation(lm);

  if (rotation > MAX_FACE_ANGLE) {
    stableCounter = 0;
    rostroInfo.textContent = "📡 Por favor mire al frente";
    btnRecomendar.disabled = true;
    return;
  }

  const detectedType = calcFaceType(lm, w, h);
  if (detectedType === faceType) {
    stableCounter++;
  } else {
    stableCounter = 0;
    faceType = detectedType;
  }

  overlay.width = w;
  overlay.height = h;
  ctxOv.clearRect(0, 0, w, h);

  const color = faceColors[faceType] || "#10b981";
  ctxOv.fillStyle = color;
  ctxOv.strokeStyle = color;
  ctxOv.lineWidth = 3;

  lm.forEach(p => ctxOv.fillRect(p.x * w, p.y * h, 2, 2));
  ctxOv.strokeRect(0, 0, w, h);

  if (stableCounter >= STABILITY_THRESHOLD) {
    rostroInfo.textContent = `✔️ Forma detectada: ${faceType}`;
    btnRecomendar.disabled = false;
  } else {
    rostroInfo.textContent = "📡 Analizando rostro…";
    btnRecomendar.disabled = true;
  }
});

(async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    video.srcObject = stream;
    await video.play();
    const loop = async () => {
      if (video.readyState >= 2) await faceMesh.send({ image: video });
      requestAnimationFrame(loop);
    };
    loop();
  } catch (err) {
    console.error("❌ Error al acceder a la cámara:", err);
  }
})();

const faceColors = {
  "Alargado": "#facc15",
  "Cuadrado": "#ef4444",
  "Redondo": "#3b82f6",
  "Corazón": "#8b5cf6",
  "Diamante": "#f97316",
  "Triangular": "#a855f7",
  "Ovalado": "#22c55e"
};

btnRecomendar.onclick = () => {
  if (!faceType) return console.error("⚠️ Espera a que se detecte tu rostro");
  if (!genero.value || !actividad.value) return console.error("⚠️ Selecciona tu género y actividad");

  spinner.classList.remove('hidden');

  fetch("/api/recomendar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      genero: genero.value,
      actividad: actividad.value,
      tipo_rostro: faceType
    })
  })
    .then(r => {
      if (!r.ok) {
        throw new Error(`Error ${r.status}: ${r.statusText}`);
      }
      return r.json();
    })
    .then(({ id_usuario, recomendaciones }) => {
      lastUserId = id_usuario;
      gridGafas.innerHTML = "";
      gridGafasMobile.innerHTML = "";

      // Proteger contra recomendaciones undefined o null
      if (!recomendaciones || !Array.isArray(recomendaciones)) {
        console.error("❌ No se recibieron recomendaciones válidas:", recomendaciones);
        gridGafas.innerHTML = "<div class='text-center text-red-500'>No se pudieron cargar las recomendaciones</div>";
        gridGafasMobile.innerHTML = "<div class='text-center text-red-500'>No se pudieron cargar las recomendaciones</div>";
        return;
      }

      recomendaciones.forEach(g => {
        const cardHTML = `
        <div class="swiper-slide bg-white dark:bg-gray-800 rounded-xl shadow hover:shadow-lg transition duration-300">
          <img src="${g.img}" alt="${g.nombre}" class="w-full h-40 object-cover rounded-t-xl">
          <div class="p-3 text-center">
            <h3 class="font-semibold">${g.nombre}</h3>
            <p class="text-blue-600 dark:text-blue-300 text-sm">Afinidad: ${g.afinidad}%</p>
            <p class="text-gray-500 dark:text-gray-400 text-xs">Precio: $${g.precio}</p>
            <div class="flex justify-center gap-2 mt-2">
              <button class="probar-btn bg-blue-600 hover:bg-blue-700 text-white text-sm py-1 px-3 rounded" data-id="${g.id_lente}" data-modelo="${g.modelo}" data-afinidad="${g.afinidad}">Probar</button>
              <button class="comprar-btn bg-green-600 hover:bg-green-700 text-white text-sm py-1 px-3 rounded" data-id="${g.id_lente}" data-nombre="${g.nombre}" data-afinidad="${g.afinidad}">Comprar</button>
            </div>
            <div class="flex justify-center gap-2 mt-2">
              <button class="feedback-btn text-sm px-2 py-1 bg-gray-200 dark:bg-gray-700 rounded transition-transform" data-id="${g.id_lente}" data-like="1">Me gusta</button>
              <button class="feedback-btn text-sm px-2 py-1 bg-gray-200 dark:bg-gray-700 rounded transition-transform" data-id="${g.id_lente}" data-like="0">No me gusta</button>
            </div>
          </div>
        </div>`;
        gridGafas.insertAdjacentHTML('beforeend', cardHTML);
        const mobileCard = document.createElement("div");
        mobileCard.innerHTML = cardHTML.replace('swiper-slide ', '');
        gridGafasMobile.appendChild(mobileCard.firstElementChild);
      });

      if (swiperInstance) swiperInstance.destroy(true, true);
      swiperInstance = new Swiper('.swiper', {
        slidesPerView: 2,
        spaceBetween: 20,
        navigation: { nextEl: '.swiper-button-next', prevEl: '.swiper-button-prev' },
        loop: false
      });
    })
    .catch(error => {
      console.error("❌ Error al obtener recomendaciones:", error);
      gridGafas.innerHTML = "<div class='text-center text-red-500'>Error al cargar recomendaciones</div>";
      gridGafasMobile.innerHTML = "<div class='text-center text-red-500'>Error al cargar recomendaciones</div>";
    })
    .finally(() => {
      spinner.classList.add('hidden');
    });
};

gridGafasMobile.addEventListener("click", handleCardClicks);
gridGafas.addEventListener("click", handleCardClicks);

function handleCardClicks(e) {
  if (e.target.classList.contains("probar-btn")) {
    const modelo = e.target.dataset.modelo;
    const idLente = e.target.dataset.id;
    const afinidad = e.target.dataset.afinidad;
    fetchFeedback("probar", idLente, afinidad, () => lanzarJeelizTryon(modelo));
  } else if (e.target.classList.contains("comprar-btn")) {
    const idLente = e.target.dataset.id;
    const nombre = e.target.dataset.nombre;
    const afinidad = e.target.dataset.afinidad;
    fetchFeedback("comprar", idLente, afinidad, () => {
      const mensaje = `Hola, estoy interesado en comprar el modelo ${nombre}`;
      window.open(`https://wa.me/593997906611?text=${encodeURIComponent(mensaje)}`, "_blank");
    });
  } else if (e.target.classList.contains("feedback-btn")) {
    const like = e.target.dataset.like === "1";
    const idLente = e.target.dataset.id;
    fetchFeedback("feedback", idLente, 0, null, like);

    const parent = e.target.parentElement;
    parent.querySelectorAll('.feedback-btn').forEach(btn => {
      btn.classList.remove('bg-blue-500', 'text-white', 'bg-red-500', 'text-white', 'pulse');
    });
    if (like) {
      e.target.classList.add('bg-blue-500', 'text-white', 'pulse');
    } else {
      e.target.classList.add('bg-red-500', 'text-white', 'pulse');
    }
  }
}

function fetchFeedback(accion, idLente, afinidad, callback, like = null) {
  if (!lastUserId) return console.error("❌ No se detectó usuario");
  fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_usuario: lastUserId, id_lente: idLente, accion, afinidad, like })
  }).then(() => {
    if (callback) callback();
  });
}

function lanzarJeelizTryon(modelo) {
  const modal = document.getElementById("tryonModal");
  modal.classList.remove("hidden");
  document.getElementById("cerrarTryon").onclick = () => modal.classList.add("hidden");
  if (window.JEELIZVTOWIDGET) {
    if (window.__jeelizIniciado) {
      JEELIZVTOWIDGET.load(modelo);
    } else {
      JEELIZVTOWIDGET.start({
        sku: modelo,
        isShadow: true,
        searchImageMask: "https://appstatic.jeeliz.com/jeewidget/images/target512.jpg",
        searchImageColor: 0xeeeeee,
        callbackReady: () => window.__jeelizIniciado = true,
        onError: (e) => console.error("❌ Jeeliz error:", e)
      });
    }
  }
}
