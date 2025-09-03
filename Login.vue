<!-- src/components/Login.vue -->
<template>
  <div class="login-page">
    <!-- 背景视频 -->
    <video class="bg-video" :src="currentBg" autoplay muted playsinline loop></video>

    <!-- ===== 账号模式：左右双面板 ===== -->
    <div v-if="mode==='account'" class="grid">
      <!-- 学生登录（左） -->
      <section class="panel">
        <h2 class="panel-title neon">学生登录</h2>

        <div class="inner">
          <form class="form" @submit.prevent="loginStudent">
            <input v-model="sUser" placeholder="用户名" required />
            <input v-model="sPass" type="password" placeholder="密码" required />
            <button class="cta" type="submit">登 录</button>
          </form>

          <div class="sep">
            <span class="line"></span><span class="or">或</span><span class="line"></span>
          </div>

          <button class="cta" @click="startFace()">人脸识别登录</button>
        </div>

        <p v-if="errorMsgStu" class="error">{{ errorMsgStu }}</p>
      </section>

      <!-- 中间留白，避免挡住视频中心 -->
      <section class="center-safe" aria-hidden="true"></section>

      <!-- 教师登录（右） -->
      <section class="panel">
        <h2 class="panel-title neon">教师登录</h2>

        <div class="inner">
          <form class="form" @submit.prevent="loginTeacher">
            <input v-model="tUser" placeholder="用户名" required />
            <input v-model="tPass" type="password" placeholder="密码" required />
            <button class="cta" type="submit">登 录</button>
          </form>

          <div class="sep">
            <span class="line"></span><span class="or">或</span><span class="line"></span>
          </div>

          <button class="cta" @click="startFace()">人脸识别登录</button>
        </div>

        <p v-if="errorMsgTea" class="error">{{ errorMsgTea }}</p>
      </section>
    </div>

    <!-- ===== 人脸识别模式 ===== -->
    <div
      v-if="mode==='face'"
      class="camera-frame"
      :class="{ hidden: !personVisible && cameraOk && algoOk && !recognizedOk }"
    >
      <!-- 状态纵向一列（每项一行，宽度随文字） -->
      <div class="cam-toolbar">
        <ul class="status-list">
          <li class="status-item" :class="(cameraOk||recognizedOk) ? 'ok' : 'idle'">
            <span class="dot"></span><b>摄像头</b>：{{ (cameraOk||recognizedOk) ? '就绪' : '未就绪' }}
          </li>
          <li class="status-item" :class="(algoOk||recognizedOk) ? 'ok' : 'idle'">
            <span class="dot"></span><b>分割算法</b>：{{ (algoOk||recognizedOk) ? '就绪' : '未就绪' }}
          </li>
          <li class="status-item" :class="(personVisible||recognizedOk) ? 'ok' : 'idle'">
            <span class="dot"></span><b>人像</b>：{{ (personVisible||recognizedOk) ? '已检测' : '未检测' }}
          </li>
          <li class="status-item strong" :class="recognizedOk ? 'ok' : 'idle'">
            <span class="dot"></span><b>识别状态</b>：{{ recognizedOk ? '识别成功' : '识别中' }}
          </li>
        </ul>
      </div>

      <!-- 右下角炫酷返回按钮 -->
      <button class="back-fab neon-fab" @click="switchMode('account')" aria-label="返回账号登录">
        返回账号登录
      </button>

      <!-- 视频输入（隐藏） -->
      <video ref="cameraVideo" class="hidden-video" autoplay muted playsinline></video>
      <!-- 抠像结果（仅人物） -->
      <canvas ref="segCanvas" class="seg-canvas"></canvas>

      <p v-if="errorMsgFace" class="error face-err">{{ errorMsgFace }}</p>
    </div>

    <!-- 识别成功后的头像与信息 -->
    <transition name="fade">
      <img
        v-if="photoVisible"
        :src="photoUrl"
        class="info-photo photo-pop"
        alt="photo"
        loading="eager"
        decoding="sync"
        @error="onPhotoError"
      />
    </transition>

    <transition name="fade">
      <div v-if="infoVisible" class="info-box fx">
        <div
          v-for="(line,i) in infoLines"
          :key="i"
          class="info-line"
          :style="{animationDelay: (i*0.28)+'s'}"
        >
          <span class="line-glow">{{ line }}</span>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, onBeforeUnmount, nextTick, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import creds from '../data/credentials.js';

/* 背景视频（登录/人脸） */
const loginBg = new URL('../assets/videos/login_bg.mp4', import.meta.url).href;
const faceBg  = new URL('../assets/videos/login_face.mp4', import.meta.url).href;

const router       = useRouter();
const mode         = ref('account');
const currentBg    = ref(loginBg);

/* 学生/教师账号 */
const sUser = ref(''); const sPass = ref(''); const errorMsgStu = ref('');
const tUser = ref(''); const tPass = ref(''); const errorMsgTea = ref('');

/* 人脸识别/分割 */
const cameraVideo = ref(null);
const segCanvas   = ref(null);
let stream = null, retryTimer = null, showTimer = null, redirectTimer = null, faceTimeoutTimer = null;
let faceStart = 0;
const errorMsgFace = ref('');
const personVisible = ref(false);
const cameraOk = ref(false);
const algoOk   = ref(false);
const recognizedOk = ref(false);

/* 成功信息 + 行级动画 */
const photoUrl     = ref('');
const photoVisible = ref(false);
const infoHtml     = ref('');
const infoVisible  = ref(false);
const infoLines    = ref([]);
const currentRole  = ref('student'); // 用于图片出错时回退默认头像

/* —— 人像框（CSS 变量） —— */
const camLeft  = ref(getCssVar('--cam-left','20.5%'));
const camTop   = ref(getCssVar('--cam-top','24.6%'));
const camWidth = ref(getCssVar('--cam-width','21%'));
const camHeight= ref(getCssVar('--cam-height','50%'));
function applyCamVars(){
  const r = document.documentElement;
  r.style.setProperty('--cam-left',  camLeft.value);
  r.style.setProperty('--cam-top',   camTop.value);
  r.style.setProperty('--cam-width', camWidth.value);
  r.style.setProperty('--cam-height',camHeight.value);
}
function getCssVar(name, fallback){
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/* 动态加载 CDN 脚本（双源回退） */
async function loadScriptOnce(src){
  return new Promise((resolve,reject)=>{
    if (document.querySelector(`script[data-src="${src}"]`)) return resolve();
    const s = document.createElement('script');
    s.async = true; s.src = src; s.setAttribute('data-src', src);
    s.onload = ()=>resolve(); s.onerror = ()=>reject(new Error('script load failed: '+src));
    document.head.appendChild(s);
  });
}
async function ensureMediapipe(){
  const tryList = [
    'https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils@0.3/camera_utils.js',
    'https://cdn.jsdelivr.net/npm/@mediapipe/selfie_segmentation@0.1/selfie_segmentation.js',
    'https://unpkg.com/@mediapipe/camera_utils@0.3/camera_utils.js',
    'https://unpkg.com/@mediapipe/selfie_segmentation@0.1/selfie_segmentation.js'
  ];
  try{ await loadScriptOnce(tryList[0]); }catch{}
  try{ await loadScriptOnce(tryList[1]); }catch{}
  if(!window.Camera || !window.SelfieSegmentation){
    try{ await loadScriptOnce(tryList[2]); }catch{}
    try{ await loadScriptOnce(tryList[3]); }catch{}
  }
  if(window.Camera && window.SelfieSegmentation){ algoOk.value = true; }
  else throw new Error('mediapipe not available');
}

/* 清理上次分析缓存 */
async function clearPreviousState(){
  const KEYS = [
    'metacog_last_file','metacog_chart_cache','metacog_analyze_result',
    'metacog_shap_cache','metacog_student_detail','metacog_teacher_filters'
  ];
  KEYS.forEach(k => localStorage.removeItem(k));
  sessionStorage.removeItem('metacog_upload_name');
  sessionStorage.removeItem('metacog_upload_time');
  try { await axios.post('/api/reset_analysis'); }
  catch(_){ try { await axios.post('/api/clear_last_upload'); } catch(__){} }
}

/* 登录：学生/教师 */
async function loginStudent(){
  errorMsgStu.value = '';
  const ok = (creds['student']||[]).some(u => u.username===sUser.value && u.password===sPass.value);
  if(ok){ await clearPreviousState(); router.push('/student'); }
  else{ errorMsgStu.value = '用户名或密码错误'; }
}
async function loginTeacher(){
  errorMsgTea.value = '';
  const ok = (creds['teacher']||[]).some(u => u.username===tUser.value && u.password===tPass.value);
  if(ok){ await clearPreviousState(); router.push('/teacher'); }
  else{ errorMsgTea.value = '用户名或密码错误'; }
}

/* ====== 头像加载 & 中文文件名支持 ====== */
function normalizeRole(role){
  const r = String(role||'').trim().toLowerCase();
  if(['student','students','stu','学生'].includes(r)) return 'student';
  if(['teacher','teachers','tea','教师','老师'].includes(r)) return 'teacher';
  return r || 'student';
}
/* 只编码“最后一个段（文件名）”，保留目录结构 */
function encodeLastSeg(p){
  if(!p) return '';
  if(/^https?:\/\//i.test(p)) return p; // 绝对 URL 不动
  // 保留查询串
  const [base, query] = String(p).split('?');
  const i = base.lastIndexOf('/');
  const dir = i>=0 ? base.slice(0,i+1) : '';
  const file = i>=0 ? base.slice(i+1) : base;
  const encoded = encodeURIComponent(file);
  return dir + encoded + (query ? ('?' + query) : '');
}
/* 仅编码普通字符串为文件名（不含路径） */
function encodeSeg(name){
  return encodeURIComponent(String(name??'').trim());
}
/* 构造候选头像 URL（包含原始 & 仅编码文件名两种） */
function buildFaceCandidates(role, rec, fallbackUser){
  const base = `/faces/${role}/`;
  const names = [
    rec?.photo, rec?.avatar,
    rec?.username, rec?.name, rec?.id, rec?.studentId, rec?.teacherId, rec?.number,
    fallbackUser
  ].filter(Boolean);

  const exts = ['jpg','jpeg','png','webp'];
  const urls = [];

  for (const n of names){
    if (typeof n === 'string' && (n.startsWith('http://') || n.startsWith('https://'))) {
      urls.push(n);
      continue;
    }
    if (typeof n === 'string' && n.includes('/')) {
      // 已带路径：原样 + 仅编码文件名版本
      urls.push(n);
      urls.push(encodeLastSeg(n));
      continue;
    }
    if (n){
      const fname = encodeSeg(n); // 文件名编码，支持中文
      for (const ext of exts){
        urls.push(base + fname + '.' + ext);
      }
    }
  }
  // 去重
  return Array.from(new Set(urls));
}
function probeImage(url){
  return new Promise(resolve=>{
    const img = new Image();
    img.onload = ()=>resolve(true);
    img.onerror = ()=>resolve(false);
    img.src = url;
  });
}
async function pickFirstExisting(urls){
  for (const u of urls){ if(await probeImage(u)) return u; }
  return null;
}
function defaultAvatar(role){
  return role==='teacher'? '/faces/default-teacher.png' : '/faces/default-student.png';
}
function onPhotoError(e){
  const fallback = defaultAvatar(currentRole.value);
  if (photoUrl.value !== fallback) photoUrl.value = fallback;
  console.warn('photo load error', e?.target?.src);
}

/* —— 健壮查找人物信息 —— */
function findRecord(role, username){
  const roleKey = normalizeRole(role);
  const keys = roleKey==='student'
    ? ['student','students','stu','学生']
    : ['teacher','teachers','tea','教师','老师'];
  // 汇总多个可能 key
  const list = keys.reduce((acc,k)=>{
    const arr = creds?.[k];
    if (Array.isArray(arr)) acc.push(...arr);
    return acc;
  }, []);
  const norm = v => String(v ?? '').trim().toLowerCase();
  const key = norm(username);

  let rec = list.find(u => norm(u.username) === key);
  if(!rec) rec = list.find(u => norm(u.name) === key);
  if(!rec) rec = list.find(u =>
    norm(u.id)===key || norm(u.studentId)===key || norm(u.teacherId)===key || norm(u.number)===key
  );
  if(!rec){
    const strip = s => norm(s).replace(/\s+/g,'');
    rec = list.find(u => strip(u.username)===strip(username) || strip(u.name)===strip(username));
  }
  if(!rec){
    console.warn('[face-login] 未在 credentials.js 找到匹配项：', {role, username});
  }
  return rec || null;
}

/* 切换模式 */
async function switchMode(m){
  mode.value = m;
  resetInfo();
  clearTimeout(faceTimeoutTimer);
  recognizedOk.value = false;

  if(m==='face'){
    faceStart = Date.now();
    currentBg.value = faceBg;

    try{
      checkCameraEnvOrThrow();
      await ensureMediapipe();
      await openCamera();
      await nextTick();
      await startSegmentation();      // 前端抠像
      retryTimer = setTimeout(captureAndSend, 900); // 后端识别
      errorMsgFace.value = '';
    }catch(e){
      console.error(e);
      errorMsgFace.value = humanizeCameraError(e);
    }

    faceTimeoutTimer = setTimeout(()=>{
      if(!infoVisible.value){ switchMode('account'); errorMsgFace.value='识别超时，请重试'; }
    }, 14000);
  }else{
    currentBg.value = loginBg;
    closeCamera();
    stopSegmentation();
  }
}
function startFace(){ switchMode('face'); }

/* 环境检查 */
function checkCameraEnvOrThrow(){
  if(!navigator.mediaDevices?.getUserMedia) throw new Error('此设备/浏览器不支持摄像头');
  const isHttps = location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  if(!isHttps) throw new Error('需要在 HTTPS 或 localhost 下访问页面');
}
function humanizeCameraError(e){
  const msg = String(e?.message||e||'失败');
  if(msg.includes('HTTPS')||msg.includes('https')) return '需要在 HTTPS 或 localhost 下访问页面';
  if(msg.includes('NotAllowedError')) return '已被浏览器拒绝摄像头权限，请在地址栏右侧开启权限';
  if(msg.includes('NotFoundError')) return '未找到可用摄像头设备';
  if(msg.includes('mediapipe')) return '分割算法加载失败，可能被网络或安全策略拦截';
  return '无法访问摄像头或算法加载失败';
}

/* 摄像头 */
async function openCamera(){
  if(stream) return;
  try{
    stream = await navigator.mediaDevices.getUserMedia({
      video:{ facingMode:'user', width:{ideal:1280}, height:{ideal:720} }, audio:false
    });
    cameraOk.value = true;
  }catch(e){
    cameraOk.value = false;
    throw e;
  }
  if (cameraVideo.value){
    cameraVideo.value.srcObject = stream;
    try{ await cameraVideo.value.play(); }catch(_){}}
}
function closeCamera(){
  if(stream){ stream.getTracks().forEach(t=>t.stop()); stream=null; }
  clearTimeout(retryTimer);
  if(!recognizedOk.value) cameraOk.value = false;
}

/* —— 人像分割 —— */
let mpCamera = null, selfieSegmentation = null;
let maskCanvas = null, maskCtx = null;
let frameCount = 0;
const FEATHER_PX = 1.25;     // 羽化半径（越大边缘越柔和）
const SOFT_FRAMES = 6;       // 每 N 帧做一次占比检测，减负

async function startSegmentation(){
  if(!window.SelfieSegmentation || !window.Camera) throw new Error('mediapipe not available');

  const videoEl = cameraVideo.value;
  const canvasEl = segCanvas.value;
  if(!videoEl || !canvasEl) return;

  const setSize = ()=>{
    const w = videoEl.videoWidth || 640;
    const h = videoEl.videoHeight || 480;
    canvasEl.width = w; canvasEl.height = h;
    maskCanvas = document.createElement('canvas');
    maskCanvas.width = w; maskCanvas.height = h;
    maskCtx = maskCanvas.getContext('2d');
  };
  if(videoEl.readyState >= 2){ setSize(); } else { videoEl.onloadedmetadata = setSize; }

  const SSClass = window.SelfieSegmentation?.SelfieSegmentation || window.SelfieSegmentation;
  selfieSegmentation = new SSClass({
    locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/selfie_segmentation@0.1/${file}`
  });
  selfieSegmentation.setOptions({ modelSelection: 1, selfieMode: true });
  selfieSegmentation.onResults(onResults);

  mpCamera = new window.Camera(videoEl, {
    onFrame: async () => { await selfieSegmentation.send({ image: videoEl }); },
    width: 640, height: 480
  });
  mpCamera.start();
  algoOk.value = true;
}
function stopSegmentation(){
  if (mpCamera && mpCamera.stop) mpCamera.stop();
  mpCamera = null; selfieSegmentation = null;
  if(!recognizedOk.value){ personVisible.value = false; }
  maskCanvas = null; maskCtx = null;
}

/* 清晰抠图：先画视频，再用“羽化的 mask”做 destination-in 裁剪 */
function onResults(results){
  const canvasEl = segCanvas.value;
  if(!canvasEl) return;
  const ctx = canvasEl.getContext('2d');

  // 离屏 mask（便于做 blur）
  if(maskCtx){
    maskCtx.clearRect(0,0,maskCanvas.width,maskCanvas.height);
    maskCtx.drawImage(results.segmentationMask, 0, 0, maskCanvas.width, maskCanvas.height);
  }

  // 1) 画原始视频帧
  ctx.save();
  ctx.clearRect(0,0,canvasEl.width,canvasEl.height);
  ctx.filter = 'none';
  ctx.globalCompositeOperation = 'source-over';
  ctx.drawImage(results.image, 0, 0, canvasEl.width, canvasEl.height);

  // 2) 用“轻微羽化”的 mask 做 destination-in（边缘更干净）
  ctx.globalCompositeOperation = 'destination-in';
  ctx.filter = `blur(${FEATHER_PX}px)`;
  ctx.drawImage(results.segmentationMask, 0, 0, canvasEl.width, canvasEl.height);
  ctx.restore();

  // 3) 每隔若干帧粗略判断是否有人像（提高稳定性）
  frameCount = (frameCount+1)%SOFT_FRAMES;
  if(frameCount===0 && maskCtx){
    try{
      const data = maskCtx.getImageData(0,0,maskCanvas.width,maskCanvas.height).data;
      let cnt=0, white=0;
      for(let i=0;i<data.length;i+=4*8){ cnt++; if(data[i] > 210) white++; }
      personVisible.value = (white / Math.max(1,cnt)) > 0.02;
    }catch(_){}}
}

/* 抓拍 → 后端识别 */
async function captureAndSend(){
  if(!cameraVideo.value) return;
  const v = cameraVideo.value;
  if(!v.videoWidth || !v.videoHeight){
    retryTimer = setTimeout(captureAndSend, 500);
    return;
  }
  const c=document.createElement('canvas');
  c.width=v.videoWidth; c.height=v.videoHeight;
  c.getContext('2d').drawImage(v,0,0);
  const imgB64=c.toDataURL('image/jpeg').split(',')[1];
  try{
    const {data}=await axios.post('/api/face_login',{image:imgB64});
    if(data?.success) await handleSuccess(data.username,data.role); // await 很重要：等挑选头像完成
    else retryTimer=setTimeout(captureAndSend,900);
  }catch{
    retryTimer=setTimeout(captureAndSend,900);
  }
}

/* 成功后流程（挑选可用头像 + 动画行文本） */
async function handleSuccess(user,role){
  recognizedOk.value = true;
  cameraOk.value = true; algoOk.value = true; personVisible.value = true;

  clearTimeout(retryTimer);
  clearTimeout(faceTimeoutTimer);
  closeCamera();
  stopSegmentation();

  const r = normalizeRole(role);
  currentRole.value = r;

  const rec = findRecord(r, user);

  // 头像多候选，优先 credentials 指定，再到 /faces/{role}/{中文名}.{ext}（仅编码文件名）
  const candidates = buildFaceCandidates(r, rec || {}, user);
  const chosen = await pickFirstExisting(candidates);
  photoUrl.value = chosen || defaultAvatar(r);

  // 文本信息填充（容错字段）
  const name    = rec?.name    || rec?.username || user;
  const gender  = rec?.gender  || '未知';
  const grade   = rec?.grade   || rec?.class || '未知';
  const subject = rec?.subject || rec?.course || '未知';

  infoLines.value = (
    r==='student'
      ? [`姓名：${name}`, `性别：${gender}`, `年级：${grade}`, `职业：学生`]
      : [`姓名：${name}`, `性别：${gender}`, `职业：教师`, `学科：${subject}`]
  );

  const wait=Math.max(0,7000-(Date.now()-faceStart)); // 至少 7 秒演出
  showTimer=setTimeout(()=>{
    photoVisible.value=true;
    setTimeout(()=>{ infoVisible.value=true; }, 360);
    clearPreviousState().finally(()=>{
      redirectTimer=setTimeout(()=>router.push(r==='student'?'/student':'/teacher'),5000);
    });
  },wait);
}

/* 生命周期与清理 */
onMounted(()=>{
  // 从真正的 :root 读取相机位置变量，避免默认值覆盖自定义
  camLeft.value   = getCssVar('--cam-left',  camLeft.value);
  camTop.value    = getCssVar('--cam-top',   camTop.value);
  camWidth.value  = getCssVar('--cam-width', camWidth.value);
  camHeight.value = getCssVar('--cam-height',camHeight.value);
  applyCamVars();
});
onUnmounted(()=>{});
function resetInfo(){
  photoVisible.value=false; infoVisible.value=false;
  infoLines.value=[]; infoHtml.value='';
  photoUrl.value='';
  clearTimeout(showTimer); clearTimeout(redirectTimer);
}
onBeforeUnmount(()=>{ closeCamera(); stopSegmentation(); resetInfo(); clearTimeout(faceTimeoutTimer); });
</script>

<style scoped>
*,*::before,*::after{ box-sizing:border-box; }

:root{
  --glass-strong: rgba(10,16,40,.72);
  --text: #eaf3ff;
  --neon: #2bd9ff;
  --neon2:#8f7bff;

  /* 人像框位置与大小（默认值，最终会被全局 :root 覆盖） */
  --cam-left: 20.5%;
  --cam-top: 24.6%;
  --cam-width: 21%;
  --cam-height: 50%;
}

.login-page{position:relative;width:100%;height:100vh;overflow:hidden;background:#000;}
.bg-video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;pointer-events:none;user-select:none;}

/* 三列网格 */
.grid{
  position:absolute; inset:0;
  display:grid; grid-template-columns: 30% 40% 30%;
  align-items:center; justify-items:center;
  padding: min(3.2vw,48px);
  z-index:2;
  pointer-events:none;
}
.center-safe{height:100%;}

/* 面板 */
.panel{
  pointer-events:auto;
  color:var(--text);
  background:linear-gradient(180deg, var(--glass-strong), rgba(14,20,48,.48));
  border:1px solid rgba(68,136,255,.35);
  border-radius:18px;
  box-shadow:
    0 0 0 1px rgba(43,217,255,.18) inset,
    0 18px 40px rgba(0,0,0,.35),
    0 0 24px rgba(43,217,255,.22);
  backdrop-filter: blur(8px) saturate(130%);
  position:relative; overflow:hidden;
  padding:14px 0 12px;
  width:min(520px, 96%);
}
.panel-title{
  margin:2px 14px 8px;
  text-align:center;
  font-size:22px; letter-spacing:.12em; font-weight:800;
}
.neon{
  background: linear-gradient(90deg, #66e0ff 0%, #8f7bff 40%, #4df3a3 80%, #66e0ff 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  text-shadow: 0 0 12px rgba(43,217,255,.45);
  background-size: 200% 100%;
  animation: shine 6s linear infinite;
}
@keyframes shine{ 0%{background-position:0% 0;} 100%{background-position:200% 0;} }

.inner{ padding: 0 14px 8px; }
.form{ display:flex; flex-direction:column; gap:12px; }
.form input{
  width:100%;
  height:42px; padding:0 12px; border-radius:12px;
  background:#0d1434; color:#eaf3ff;
  border:1px solid rgba(108,138,255,.38); outline:none;
}
.form input::placeholder{ color:#8aa3ff; }
.cta{
  width:100%;
  height:44px; border-radius:12px; cursor:pointer;
  border:1px solid #49dbff;
  background: linear-gradient(90deg, rgba(29,162,253,.9), rgba(30,220,255,.96));
  color:#001627; font-weight:900; letter-spacing:.1em;
  box-shadow: 0 10px 26px rgba(43,217,255,.35);
  transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
}
.cta:hover{ transform: translateY(-1px); box-shadow: 0 14px 30px rgba(43,217,255,.45); filter: brightness(1.06); }
.sep{ display:flex; align-items:center; gap:8px; margin:12px 0 10px; color:#a9b9ff; }
.sep .line{ flex:1; height:1px; background:linear-gradient(90deg, transparent, rgba(120,160,255,.6), transparent); }
.sep .or{ font-size:12px; opacity:.95; text-shadow:0 0 6px rgba(43,217,255,.35); }
.error{ color:#ff8a8a; margin:6px 14px 0; font-size:12px; text-shadow:0 0 6px rgba(255,0,0,.25); }

/* ===== 人脸识别容器 ===== */
.camera-frame{
  position:absolute;
  left: var(--cam-left); top: var(--cam-top);
  width: var(--cam-width); height: var(--cam-height);
  display:flex; flex-direction:column; gap:8px;
  background:linear-gradient(180deg, rgba(12,18,40,.5), rgba(12,18,40,.2));
  border-radius:16px; overflow:hidden; z-index:2;
  border:1px solid rgba(73,219,255,.55);
  box-shadow:0 0 0 1px rgba(43,217,255,.25) inset, 0 0 28px rgba(43,217,255,.25);
  padding:8px;
  transition: opacity .18s ease;
}
.camera-frame.hidden{ opacity:0; }

/* 状态栏：纵向一列，每个状态“随文字宽度” */
.cam-toolbar{ width:100%; }
.status-list{
  list-style:none; margin:0; padding:0;
  display:flex; flex-direction:column; gap:6px;
  align-items:flex-start;
}
.status-item{
  display:inline-flex;
  align-items:center; gap:8px;
  width:auto;
  max-width:100%;
  font-size:12px; padding:6px 10px;
  border-radius:10px;
  border:1px solid rgba(73,219,255,.35);
  background:rgba(10,16,36,.6); color:#9feaff;
  white-space:nowrap;
}
.status-item .dot{
  width:8px;height:8px;border-radius:50%;
  background:#ffd073; box-shadow:0 0 8px rgba(255,208,115,.6);
}
.status-item.ok .dot{ background:#24e6a1; box-shadow:0 0 8px rgba(36,230,161,.7); }
.status-item.idle{ color:#ffd073; border-color:rgba(255,208,115,.45); }
.status-item.ok{ color:#bfffe8; border-color:rgba(36,230,161,.55); }
.status-item.strong{ font-weight:700; }

/* 右下角炫酷返回按钮 */
.back-fab{
  position:absolute; right:10px; bottom:10px; z-index:3;
  height:34px; padding:0 14px; border-radius:999px; cursor:pointer;
  border:none; color:#001627; font-weight:800; letter-spacing:.04em;
}
.neon-fab{
  background:
    radial-gradient(120% 120% at 10% 10%, rgba(255,255,255,.16), transparent 60%),
    linear-gradient(90deg, rgba(29,162,253,.98), rgba(30,220,255,.98));
  box-shadow:
    0 0 0 1px rgba(73,219,255,.8) inset,
    0 10px 26px rgba(43,217,255,.35),
    0 0 24px rgba(43,217,255,.45);
  transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
}
.neon-fab:hover{ transform:translateY(-1px); box-shadow:0 14px 34px rgba(43,217,255,.55),0 0 34px rgba(43,217,255,.55); filter:brightness(1.06); }

/* 画布 */
.hidden-video{ display:none; }
.seg-canvas{
  flex:1;
  width:100%; height:100%;
  object-fit:cover;
  image-rendering:auto;
  border-radius:10px;
}

/* 识别成功动画区（支持等比缩放） */
.info-photo{
  position:absolute;
  top:48%; right:45%;
  width: clamp(56px, calc(8% * var(--success-scale)), 22vw);
  height: auto;
  aspect-ratio:1/1;
  object-fit:contain;
  border-radius:12px; z-index:3;
  box-shadow:0 10px 26px rgba(0,0,0,.35), 0 0 32px rgba(43,217,255,.35);
  transform-origin: top right;
}
.photo-pop{ transform-origin: 50% 50%; animation: popIn .66s cubic-bezier(.2, .9, .2, 1.2) both; }
@keyframes popIn{ 0%{ transform: scale(.2); opacity:0; filter: blur(8px); } 60%{ transform: scale(1.05); opacity:1; filter: blur(0); } 100%{ transform: scale(1); } }

.info-box{
  position:absolute;
  top:48%; right:35%; z-index:3;
  color:#e8f8ff;
  font-size: clamp(14px, calc(20px * var(--success-scale)), 28px);
  line-height: 1.5;
  text-shadow:0 0 6px rgba(0,224,255,.5);
  pointer-events:none;
}
.info-box.fx .info-line{ opacity:0; transform: translateY(10px); animation: riseIn .48s ease forwards; }
@keyframes riseIn{ to{ opacity:1; transform: translateY(0); } }
.info-line .line-glow{
  background: linear-gradient(90deg, #8be8ff, #a99aff, #5ff3b1, #8be8ff);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  background-size: 200% 100%;
  animation: shine 5s linear infinite;
  text-shadow: 0 0 10px rgba(43,217,255,.35), 0 0 18px rgba(123,125,255,.25);
}

/* 渐隐 */
.fade-enter-active,.fade-leave-active{ transition:opacity .6s; }
.fade-enter-from,.fade-leave-to{ opacity:0; }

/* 移动端 */
@media (max-width: 1080px){
  .grid{ grid-template-columns: 100%; grid-auto-rows:auto; gap:18px; align-items:end; }
  .panel{ justify-self:center; width:min(560px,96%); }
}
</style>

<!-- ★★★ 全局 :root 变量（不带 scoped，最终生效） -->
<style>
:root{
  /* 识别框位置与大小（百分比） */
  --cam-left: 19.5%;
  --cam-top: 24.6%;
  --cam-width: 18%;
  --cam-height: 51%;

  /* ★ 等比缩放倍数（1=原始，1.25=放大25%） */
  --success-scale: 1.25;
}
</style>
