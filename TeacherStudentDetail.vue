<!-- src/components/TeacherStudentDetail.vue -->
<template>
  <div class="stage" :style="stageVars">
    <!-- 背景 -->
    <img
      class="bg"
      src="/bg/BG.jpg"
      srcset="/bg/BG.jpg 1x, /bg/BG@2x.jpg 2x"
      sizes="100vw"
      alt="背景"
      loading="eager"
      decoding="sync"
      fetchpriority="high"
      draggable="false"
    />

    <!-- 中央裁剪窗口视频（教师端直接处于 analysis 态） -->
    <video
      v-if="logoOK"
      ref="videoEl"
      class="window-frame window-video"
      :src="logo"
      autoplay
      loop
      muted
      playsinline
      @canplay="onVideoCanPlay"
    ></video>

    <!-- 顶部 HUD -->
    <header class="topbar">
      <div class="left-controls">
        <button class="hud-btn" @click="goHome">首页</button>
        <button class="hud-btn" @click="goBack">返回</button>
        <span class="hud-datetime">{{ dateTimeFull }}</span>
      </div>
      <div class="right-controls"></div>
    </header>

    <!-- 能力输出框：上方显示学生姓名，下方显示 高/中/低 -->
    <transition name="ability-pop">
      <div v-if="abilityVisible" class="ability-badge" :class="abilityClass">
        <div class="stu-name">{{ studentName }}</div>
        <div class="ability-level">{{ abilityText }}</div>
      </div>
    </transition>

    <!-- 四图 -->
    <div id="radar" class="chart box-left-top"></div>
    <div id="emo"   class="chart box-left-bottom"></div>
    <div id="line"  class="chart box-right-top"></div>
    <div id="cog"   class="chart box-right-bottom"></div>

    <!-- 智能对话（逐字打字效果；共用历史，不自动播欢迎语） -->
    <div class="chat-module bare">
      <div class="chat-window bare" ref="chatWinEl">
        <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-msg', msg.sender]">
          <span>{{ msg.text }}</span>
        </div>
      </div>
      <div class="chat-input bare">
        <input v-model="userInput" @keyup.enter="sendMessage" placeholder="输入你的问题..." />
        <button @click="sendMessage">发送</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import axios from 'axios';
import logo from '../assets/techlogo.mp4';

/* === API 实例 === */
const api = axios.create({
  baseURL: import.meta.env?.VITE_API_BASE || '',
  timeout: 30000
});

/* ===== 统一中文映射 ===== */
const LABEL_MAP = {
  'CEM':'明确评价方式','CLT':'明确学习任务','VC':'查看课程','RA':'资源访问',
  'DI':'讨论互动','TC':'任务完成','SH':'寻求帮助','PM':'过程监控','LR':'学习反思','LE':'学习评价',
  'Affect':'情感体验','PosEmo':'积极情绪','CogMech':'认知能力','Insight':'反思能力'
};
const SEQ_ZH = [
  '明确评价方式→明确评价方式','明确学习任务→查看课程','明确学习任务→任务完成','明确学习任务→学习反思',
  '查看课程→明确学习任务','查看课程→查看课程','资源访问→明确评价方式','资源访问→资源访问',
  '讨论互动→讨论互动','讨论互动→学习反思','任务完成→任务完成','任务完成→过程监控',
  '过程监控→查看课程','过程监控→任务完成','过程监控→过程监控','学习反思→学习反思'
];
const toCN = (name)=>{
  if (!name) return '';
  if (name.includes('→')){ const [a,b]=name.split('→'); return `${LABEL_MAP[a]||a}→${LABEL_MAP[b]||b}`; }
  return LABEL_MAP[name] || name;
};

/* ===== 路由与时钟 ===== */
const router = useRouter();
const route  = useRoute();
const dateTimeFull = ref('');
let timerClock;

function pad(n){ return n<10 ? '0'+n : ''+n; }
function fmt(now){
  const y=now.getFullYear(), m=pad(now.getMonth()+1), d=pad(now.getDate());
  const hh=pad(now.getHours()), mm=pad(now.getMinutes()), ss=pad(now.getSeconds());
  const wk=now.toLocaleDateString('zh-CN',{ weekday:'长'==='长' ? 'long' : 'long' }).replace('周','星期');
  return `${y}-${m}-${d} ${hh}:${mm}:${ss} ${wk}`;
}
function tick(){ dateTimeFull.value = fmt(new Date()); }
function goHome(){ router.push('/'); }
function goBack(){ router.back(); }

/* ===== 能力炫酷字（视频出现后显示） ===== */
const logoOK = true;
const videoEl = ref(null);
const abilityText = ref('');
const abilityVisible = ref(false);
let abilityTimer = null;
const abilityClass = computed(()=>{
  if (abilityText.value === '高') return 'lvl-high';
  if (abilityText.value === '中') return 'lvl-mid';
  if (abilityText.value === '低') return 'lvl-low';
  return '';
});
function onVideoCanPlay(){
  clearTimeout(abilityTimer);
  abilityTimer = setTimeout(()=>{ abilityVisible.value = true; }, 300);
}

/* ===== 读取 studentData（教师端从 sessionStorage 注入） ===== */
const studentData = ref(null);
function safeJSON(str){ try{ return JSON.parse(str); }catch{ return null; } }

(function loadStudent(){
  const saved = sessionStorage.getItem('studentData');
  if (!saved) {
    alert('未检测到学生数据，将返回教师页');
    router.push('/teacher');
  } else {
    const parsed = safeJSON(saved);
    if(!parsed){ alert('学生数据解析失败'); router.push('/teacher'); return; }
    studentData.value = parsed;
  }
})();

/* ===== 推断学生姓名 ===== */
function pickNameFromAny(any){
  const NAME_KEYS = [
    'name','studentname','student_name','stu_name','displayname','nickname',
    '姓名','学生姓名','名字','称呼'
  ];
  const isNonEmptyStr = v => typeof v === 'string' && v.trim() !== '';

  const scanObj = (obj) => {
    if (!obj || typeof obj !== 'object') return '';
    for (const k of Object.keys(obj)){
      const nk = k.toLowerCase().replace(/_/g,'');
      if (NAME_KEYS.includes(nk) && isNonEmptyStr(obj[k])) return String(obj[k]).trim();
    }
    const nests = ['student','meta','basic','profile','info','data','record','row'];
    for (const n of nests){
      if (obj[n]){
        const v = pickNameFromAny(obj[n]);
        if (v) return v;
      }
    }
    for (const k of Object.keys(obj)){
      const val = obj[k];
      if (val && typeof val === 'object'){
        const v = pickNameFromAny(val);
        if (v) return v;
      }
    }
    return '';
  };

  if (Array.isArray(any)){
    for (const item of any){
      const v = pickNameFromAny(item);
      if (v) return v;
    }
    return '';
  }
  if (typeof any === 'object') return scanObj(any);
  return '';
}
function pickIdFromAny(any){
  const ID_KEYS = ['id','sid','studentid','student_id','studentno','student_no','学号','编号','idcard','uid'];
  const scanObj = (obj) => {
    if (!obj || typeof obj !== 'object') return '';
    for (const k of Object.keys(obj)){
      const nk = k.toLowerCase().replace(/_/g,'');
      if (ID_KEYS.includes(nk) && obj[k] != null && String(obj[k]).trim() !== '') return String(obj[k]).trim();
    }
    const nests = ['student','meta','basic','profile','info','data','record','row'];
    for (const n of nests){
      if (obj[n]){
        const v = pickIdFromAny(obj[n]);
        if (v) return v;
      }
    }
    for (const k of Object.keys(obj)){
      const val = obj[k];
      if (val && typeof val === 'object'){
        const v = pickIdFromAny(val);
        if (v) return v;
      }
    }
    return '';
  };
  if (Array.isArray(any)){
    for (const item of any){
      const v = pickIdFromAny(item);
      if (v) return v;
    }
    return '';
  }
  if (typeof any === 'object') return scanObj(any);
  return '';
}
function lookupNameById(id){
  if (!id) return '';
  const banks = [sessionStorage, localStorage];
  const listKeys = ['roster','classRoster','students','studentList','stuList','tableData','class_list','list','records','rows','data'];
  for (const bank of banks){
    for (let i=0;i<bank.length;i++){
      const key = bank.key(i), val = key && bank.getItem(key);
      const parsed = safeJSON(val);
      if (!parsed) continue;
      const searchArr = (arr)=>{
        for (const row of arr){
          if (row && typeof row==='object'){
            const rid = pickIdFromAny(row);
            if (rid && String(rid) == String(id)){
              const nm = pickNameFromAny(row);
              if (nm) return nm;
            }
          }
        } return '';
      };
      if (Array.isArray(parsed)){
        const nm = searchArr(parsed); if (nm) return nm;
      }else if (typeof parsed === 'object'){
        for (const zk of listKeys){
          if (parsed[zk] && Array.isArray(parsed[zk])){
            const nm = searchArr(parsed[zk]); if (nm) return nm;
          }
        }
      }
    }
  }
  return '';
}
function deriveName(){
  const routeCandidates = [route.query.name, route.params?.name, route.query.studentName, route.params?.studentName, route.query.sname]
    .filter(v => typeof v === 'string' && v.trim());
  if (routeCandidates.length) return String(routeCandidates[0]).trim();

  const simpleKeys = ['studentName','selectedStudentName','currentStudentName','name','姓名'];
  for (const k of simpleKeys){
    const s1 = sessionStorage.getItem(k);
    if (typeof s1 === 'string' && s1.trim()) return s1.trim();
    const s2 = localStorage.getItem(k);
    if (typeof s2 === 'string' && s2.trim()) return s2.trim();
  }

  const fromObj = pickNameFromAny(studentData.value); if (fromObj) return fromObj;
  const idFromData = pickIdFromAny(studentData.value);
  const idFromRoute = [route.query.id, route.params?.id, route.query.sid, route.params?.sid]
                        .find(v => v != null && String(v).trim() !== '');
  const id = String(idFromData || idFromRoute || '').trim();
  if (id){ const nm = lookupNameById(id); if (nm) return nm; }

  return '未命名学生';
}
const studentName = ref('未命名学生');

/* ===== 能力框位置（可通过路由参数调整） ===== */
const abilityTopPct  = ref( isFinite(+route.query.abilityTop)  ? +route.query.abilityTop  : 54 );
const abilityLeftPct = ref( isFinite(+route.query.abilityLeft) ? +route.query.abilityLeft : 50 );
const stageVars = computed(()=>({ '--ability-top' : `${abilityTopPct.value}%`, '--ability-left': `${abilityLeftPct.value}%` }));

/* ===== ECharts 守护与公共 ===== */
let radar, line, emo, cog, ro;
const COLOR_ME = '#19e4ff';
const COLOR_ME_AREA = 'rgba(25,228,255,0.14)';
const COLOR_ME_SHADOW = 'rgba(25,228,255,0.65)';
const COLOR_GROUP = '#ff5a5a';
const COLOR_GROUP_AREA = 'rgba(255,90,90,0.12)';
const COLOR_GROUP_SHADOW = 'rgba(255,90,90,0.55)';
const format3 = (v)=> (typeof v==='number'? Number(v).toFixed(3): v);
const dot = (c)=> `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};margin-right:6px;vertical-align:1px;"></span>`;
const ensureEChartsReady = () => new Promise((resolve)=>{
  if (window.echarts) return resolve();
  const t = setInterval(()=>{ if (window.echarts){ clearInterval(t); resolve(); } }, 30);
  setTimeout(()=>{ clearInterval(t); resolve(); }, 1500);
});

function tipTitle(t){ return `<div style="margin-bottom:4px;">${t}</div>`; }
function tipLineMe(v){ return `${dot(COLOR_ME)}我：${format3(v)}`; }
function tipLineGrp(v){ return `${dot(COLOR_GROUP)}高群体：${format3(v)}`; }
function tipTwoLines(title, me, grp){ return tipTitle(title) + tipLineMe(me) + '<br/>' + tipLineGrp(grp); }

function hudAxis(ec){
  return {
    axisLine:{ lineStyle:{ color:'rgba(120,220,255,0.65)', width:1.2 } },
    axisTick:{ show:false },
    axisLabel:{ color:'#cfeeff', fontSize:12, fontWeight:600, fontFamily:'Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui',
      formatter:(val)=> format3(val) },
    splitLine:{ lineStyle:{ color:'rgba(0,180,255,0.18)', width:1 } }
  };
}
function hudTooltip(){
  return {
    trigger:'axis',
    backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10,
    textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
    axisPointer:{ type:'line', lineStyle:{ color:'#00eaff', width:1, type:'dashed' }, z:99 },
    extraCssText:'backdrop-filter: blur(4px);'
  };
}
function neonLine(ec){
  return {
    width:2.6, shadowBlur:14, shadowColor:'rgba(0,238,255,0.65)',
    color:new ec.graphic.LinearGradient(0,0,1,0,[{offset:0,color:'#00f5ff'},{offset:0.5,color:'#18c8ff'},{offset:1,color:'#2affd5'}])
  };
}
function neonBar(ec){
  return {
    borderRadius:6, shadowBlur:12, shadowColor:'rgba(0,238,255,0.35)',
    color:new ec.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'#22f3ff'},{offset:0.6,color:'#11b8ff'},{offset:1,color:'#0a6cff'}])
  };
}
function disposeAll(){
  const ec = window.echarts;
  [radar,line,emo,cog].forEach(ins => { if(ins) ec.dispose(ins); });
  radar = line = emo = cog = null;
}
function buildRadarPointSeries(name, values, color){
  const n = values.length, list = [];
  for(let i=0;i<n;i++){
    const vec = new Array(n).fill(null); vec[i] = values[i];
    list.push({
      name: `${name}-p${i}`,
      type:'radar',
      data:[{ value: vec, name }],
      lineStyle:{ opacity:0 }, areaStyle:{ opacity:0 },
      symbol:'circle', symbolSize:6, itemStyle:{ color }, z:20
    });
  }
  return list;
}

/* 动画参数 */
const ENTER_MS = 2400;
const UPDATE_MS = 1200;
const DELAY_STEP = 80;
const delayByIndex = (i)=> i*DELAY_STEP;

/* 统一 init */
function initChartsBase(){
  const ec = window.echarts; if (!ec) return;
  const DPR = Math.min(window.devicePixelRatio || 1, 2.5);
  const make = (id)=>{
    const el = document.getElementById(id);
    if (!el) return null;
    const old = ec.getInstanceByDom ? ec.getInstanceByDom(el) : null;
    if (old) ec.dispose(old);
    return ec.init(el, null, { backgroundColor:'transparent', renderer:'canvas', devicePixelRatio:DPR });
  };
  disposeAll();
  radar = make('radar'); line = make('line'); emo = make('emo'); cog = make('cog');

  window.addEventListener('resize', resizeAll, { passive:true });
  if (ro) ro.disconnect(); ro = new ResizeObserver(resizeAll);
  const host = document.querySelector('.stage'); if (host && ro) ro.observe(host);
}
function resizeAll(){ if(radar) radar.resize(); if(line) line.resize(); if(emo) emo.resize(); if(cog) cog.resize(); }

/* 零帧→真帧 */
function nextFrame(cb){ requestAnimationFrame(()=>{ requestAnimationFrame(cb); }); }
function primeAnalysisZeroThenAnimate(d){ renderAnalysisZero(d); nextFrame(()=>{ renderAnalysisFromData(d); }); }

/* 群体均值（固定对照） */
const avgAll = [
  0.286956522,0.304576271,0.537219731,0.250119522,
  0.338461538,0.547222222,0.423972603,0.307874016,
  0.303333333,0.31713615 ,0.479646018,0.324444444,
  0.478816794,0.518902439,0.294871795,0.254929577,
  0.340875912,0.226470588,0.536029412,0.351485149,
  0.458108108,0.336956522,0.195      ,0.205172414,
  0.458718399,0.411533105,0.721529773,0.759010105
];
const avgFreq = avgAll.slice(0,8);
const avgSeq  = avgAll.slice(8,24);
const avgEmo  = avgAll.slice(24,26);
const avgCog  = avgAll.slice(26,28);

/* 分析态：零帧（我/群体=0） */
function renderAnalysisZero(d){
  if (!radar || !line || !emo || !cog) return;
  const ec = window.echarts;
  const myFreq = d.behavior_freq.map(()=>0);
  const mySeq  = d.behavior_seq.map(()=>0);
  const myEmo  = d.emotion.map(()=>0);
  const myCog  = d.cognition.map(()=>0);
  const indicators = d.behavior_freq.map(i=>({ name: toCN(i[0]), max:1 }));

  radar.setOption({
    animation:false,
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{ trigger:'item', triggerOn:'none' },
    radar:{ indicator:indicators,
      axisName:{ color:'#cfeeff', fontFamily:'Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui', fontWeight:700 },
      splitArea:{ show:true, areaStyle:{ color:['rgba(0,180,255,0.05)','rgba(0,180,255,0.02)'] } },
      splitLine:{ lineStyle:{ color:'rgba(0,210,255,0.25)' } },
      axisLine:{ lineStyle:{ color:'rgba(0,210,255,0.25)' } } },
    series:[
      { name:'我', type:'radar', data:[{ value: myFreq, name:'我' }],
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_ME_SHADOW, color:COLOR_ME },
        itemStyle:{ color:COLOR_ME }, areaStyle:{ color:COLOR_ME_AREA } },
      { name:'高群体', type:'radar', data:[{ value: avgFreq.map(()=>0), name:'高群体' }],
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_GROUP_SHADOW, color:COLOR_GROUP },
        itemStyle:{ color:COLOR_GROUP }, areaStyle:{ color:COLOR_GROUP_AREA } }
    ]
    .concat(buildRadarPointSeries('我', myFreq, COLOR_ME))
    .concat(buildRadarPointSeries('高群体', avgFreq.map(()=>0), COLOR_GROUP))
  }, { notMerge:true });

  const xcats = d.behavior_seq.map((_,i)=>i+1);
  line.setOption({
    animation:false,
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:hudTooltip(),
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: xcats, ...hudAxis(ec) },
    yAxis:{ type:'value', ...hudAxis(ec) },
    series:[
      { name:'我', type:'line', data: mySeq, smooth:true, showAllSymbol:true,
        symbol:'circle', symbolSize:6, lineStyle:neonLine(ec), itemStyle:{ color:COLOR_ME },
        areaStyle:{ color:'rgba(25,228,255,0.08)' } },
      { name:'高群体', type:'line', data: avgSeq.map(()=>0), smooth:true, showAllSymbol:true,
        symbol:'circle', symbolSize:6,
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_GROUP_SHADOW, color:COLOR_GROUP },
        itemStyle:{ color:COLOR_GROUP }, areaStyle:{ color:'rgba(255,90,90,0.08)' } }
    ]
  }, { notMerge:true });

  emo.setOption({
    animation:false,
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{ trigger:'axis', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 }, confine:true },
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: d.emotion.map(i=> toCN(i[0])), ...hudAxis(ec) },
    yAxis:{ type:'value', ...hudAxis(ec) },
    series:[
      { name:'我', type:'bar', data: myEmo,
        itemStyle:neonBar(ec), barWidth:'42%' },
      { name:'高群体', type:'bar', data: avgEmo.map(()=>0),
        itemStyle:{ color: COLOR_GROUP, shadowBlur:12, shadowColor: COLOR_GROUP_SHADOW, opacity:.9 }, barWidth:'42%' }
    ]
  }, { notMerge:true });

  cog.setOption({
    animation:false,
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{ trigger:'axis', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 } },
    grid:{ left:60, right:20, top:30, bottom:24, containLabel:true },
    yAxis:{ type:'category', data: d.cognition.map(i=> toCN(i[0])),
      axisLabel: hudAxis(ec).axisLabel, axisLine: hudAxis(ec).axisLine, splitLine:{ show:false } },
    xAxis:{ type:'value', ...hudAxis(ec) },
    series:[
      { name:'我', type:'bar', data: myCog,
        itemStyle:neonBar(ec), barWidth:'42%' },
      { name:'高群体', type:'bar', data: avgCog.map(()=>0),
        itemStyle:{ color: COLOR_GROUP, shadowBlur:12, shadowColor: COLOR_GROUP_SHADOW, opacity:.9 }, barWidth:'42%' }
    ]
  }, { notMerge:true });
}

/* 分析态：真帧（慢速动画） */
function renderAnalysisFromData(d){
  if (!radar || !line || !emo || !cog) return;
  const ec = window.echarts;
  const myFreq = d.behavior_freq.map(v=>Number(v[1])||0);
  const mySeq  = d.behavior_seq.map(v=>Number(v[1])||0);
  const myEmo  = d.emotion.map(v=>Number(v[1])||0);
  const myCog  = d.cognition.map(v=>Number(v[1])||0);

  const indicators = d.behavior_freq.map(i=>({ name: toCN(i[0]), max:1 }));
  const xcats = d.behavior_seq.map((_,i)=>i+1);
  const emoCats = d.emotion.map(i=> toCN(i[0]));
  const cogCats = d.cognition.map(i=> toCN(i[0]));

  const mapLevel = ['低','中','高'];
  abilityText.value = mapLevel[Number(d.ability)] || '未知';
  clearTimeout(abilityTimer);
  abilityTimer = setTimeout(()=>{ abilityVisible.value = true; }, 1200);

  radar.setOption({
    animation:true, animationDuration:ENTER_MS, animationEasing:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      trigger:'item', triggerOn:'mousemove|click',
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter:(p)=>{
        const m=/^(我|高群体)-p(\d+)$/.exec(p.seriesName); if(!m) return '';
        const i=+m[2]; const name = indicators[i].name;
        return tipTwoLines(name, myFreq[i], avgFreq[i]);
      }
    },
    radar:{
      indicator:indicators,
      axisName:{ color:'#cfeeff', fontFamily:'Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui', fontWeight:700 },
      splitArea:{ show:true, areaStyle:{ color:['rgba(0,180,255,0.05)','rgba(0,180,255,0.02)'] } },
      splitLine:{ lineStyle:{ color:'rgba(0,210,255,0.25)' } },
      axisLine:{ lineStyle:{ color:'rgba(0,210,255,0.25)' } }
    },
    series:[
      { name:'我', type:'radar', data:[{ value: myFreq, name:'我' }],
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_ME_SHADOW, color:COLOR_ME },
        itemStyle:{ color:COLOR_ME }, areaStyle:{ color:COLOR_ME_AREA },
        universalTransition:true, animationDelay: delayByIndex
      },
      { name:'高群体', type:'radar', data:[{ value: avgFreq, name:'高群体' }],
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_GROUP_SHADOW, color:COLOR_GROUP },
        itemStyle:{ color:COLOR_GROUP }, areaStyle:{ color:COLOR_GROUP_AREA },
        universalTransition:true, animationDelay: delayByIndex
      }
    ]
    .concat(buildRadarPointSeries('我', myFreq, COLOR_ME))
    .concat(buildRadarPointSeries('高群体', avgFreq, COLOR_GROUP))
  }, { notMerge:true });

  line.setOption({
    animation:true, animationDuration:ENTER_MS, animationDurationUpdate:UPDATE_MS,
    animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      ...hudTooltip(),
      formatter:(ps)=>{ const idx = (ps && ps[0]) ? ps[0].dataIndex : 0;
        return tipTwoLines(SEQ_ZH[idx], mySeq[idx], avgSeq[idx]); },
      axisPointer:{ type:'line', snap:true, lineStyle:{ color:'#00eaff', width:1, type:'dashed' }, z:99 }
    },
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: xcats, ...hudAxis(ec) },
    yAxis:{ type:'value', ...hudAxis(ec) },
    series:[
      { name:'我', type:'line', data: mySeq, smooth:true, showAllSymbol:true,
        symbol:'circle', symbolSize:6, lineStyle:neonLine(ec), itemStyle:{ color:COLOR_ME },
        areaStyle:{ color:'rgba(25,228,255,0.08)' },
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex
      },
      { name:'高群体', type:'line', data: avgSeq, smooth:true, showAllSymbol:true,
        symbol:'circle', symbolSize:6,
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_GROUP_SHADOW, color:COLOR_GROUP },
        itemStyle:{ color:COLOR_GROUP }, areaStyle:{ color:'rgba(255,90,90,0.08)' },
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex
      }
    ]
  }, { notMerge:true });

  emo.setOption({
    animation:true, animationDuration:ENTER_MS, animationDurationUpdate:UPDATE_MS,
    animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      trigger:'axis', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter:(ps)=>{ const idx = (ps && ps[0]) ? ps[0].dataIndex : 0;
        return tipTwoLines(emoCats[idx], myEmo[idx], avgEmo[idx]); }
    },
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: emoCats, ...hudAxis(ec) },
    yAxis:{ type:'value', ...hudAxis(ec) },
    series:[
      { name:'我', type:'bar', data: myEmo,
        itemStyle:neonBar(ec), barWidth:'42%',
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex },
      { name:'高群体', type:'bar', data: avgEmo,
        itemStyle:{ color: COLOR_GROUP, shadowBlur:12, shadowColor: COLOR_GROUP_SHADOW, opacity:.9 }, barWidth:'42%',
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex }
    ]
  }, { notMerge:true });

  cog.setOption({
    animation:true, animationDuration:ENTER_MS, animationDurationUpdate:UPDATE_MS,
    animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      trigger:'axis', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter:(ps)=>{ const idx = (ps && ps[0]) ? ps[0].dataIndex : 0;
        return tipTwoLines(cogCats[idx], myCog[idx], avgCog[idx]); }
    },
    grid:{ left:60, right:20, top:30, bottom:24, containLabel:true },
    yAxis:{ type:'category', data: cogCats,
      axisLabel: hudAxis(ec).axisLabel, axisLine: hudAxis(ec).axisLine, splitLine:{ show:false } },
    xAxis:{ type:'value', ...hudAxis(ec) },
    series:[
      { name:'我', type:'bar', data: myCog,
        itemStyle:neonBar(ec), barWidth:'42%',
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex },
      { name:'高群体', type:'bar', data: avgCog,
        itemStyle:{ color: COLOR_GROUP, shadowBlur:12, shadowColor: COLOR_GROUP_SHADOW, opacity:.9 }, barWidth:'42%',
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex }
    ]
  }, { notMerge:true });

  // 分析完成后，输出简短总结
  postAnalysisSummary(d);
}

/* —— 对话（共用历史；携带 studentData 上下文） —— */
const CHAT_KEY = 'globalChatHistory';
const messages = ref([]);
const userInput = ref('');
const chatWinEl = ref(null);
function loadChat(){ try{ messages.value = JSON.parse(sessionStorage.getItem(CHAT_KEY) || '[]'); }catch{ messages.value = []; } }
function saveChat(){ try{ sessionStorage.setItem(CHAT_KEY, JSON.stringify(messages.value)); }catch{} }
function scrollToBottom(){ nextTick(()=>{ const el = chatWinEl.value; if (!el) return; el.scrollTop = el.scrollHeight; }); }
function pushUserImmediate(text){ messages.value.push({ sender:'user', text }); saveChat(); scrollToBottom(); }
function typeBot(text){
  const msg = { sender:'bot', text:'' };
  messages.value.push(msg); saveChat(); scrollToBottom();
  const chars = Array.from(text);
  let i=0;
  const base = chars.length>500?6:(chars.length>200?10:18);
  (function step(){
    if(i<chars.length){
      const chunk = (chars.length>400)?2:1;
      msg.text += chars.slice(i,i+chunk).join(''); i+=chunk; saveChat(); scrollToBottom();
      setTimeout(step, base + Math.floor(Math.random()*7));
    }else{ saveChat(); }
  })();
}
function postAnalysisSummary(d){
  const mapLevel = ['低','中','高'];
  const level = mapLevel[Number(d.ability)] || '未知';
  typeBot(`分析完成：${studentName.value} 的元认知能力为【${level}】。已生成行为频次、行为序列、情感、认知四类对比图表供查看。`);
}
async function sendMessage(){
  const text = userInput.value ? userInput.value.trim() : '';
  if(!text) return;
  pushUserImmediate(text);
  userInput.value = '';
  try{
    const res = await api.post('/api/chat', { message: text, scene: 'teacher', context: studentData.value || {} });
    const reply = (res?.data && res.data.reply) ? res.data.reply : '（大模型无响应）';
    typeBot(reply);
  }catch(err){
    typeBot('对话出错：无法连接智能体接口，请检查后端 /api/chat。');
  }
}

/* 生命周期 */
onMounted(async ()=>{
  tick(); timerClock = setInterval(tick, 1000);

  // 统一推断学生姓名
  studentName.value = deriveName();

  await nextTick();
  await ensureEChartsReady();
  initChartsBase();

  loadChat(); // 不自动播欢迎语，复用教师页历史

  if (studentData.value) {
    primeAnalysisZeroThenAnimate(studentData.value);
  } else {
    [radar, line, emo, cog].forEach(ins=>{
      if(!ins) return;
      ins.setOption({ graphic:[{ type:'text', left:'center', top:'middle', style:{ text:'未检测到数据', fill:'#a8d9ff', font:'700 12px Rajdhani, system-ui' } }] });
    });
  }

  clearTimeout(abilityTimer);
  abilityTimer = setTimeout(()=>{ abilityVisible.value = true; }, 1200);
});

onBeforeUnmount(()=>{
  clearInterval(timerClock);
  clearTimeout(abilityTimer);
  disposeAll(); if (ro) ro.disconnect();
});
</script>

<style scoped>
/* ===== 全局参数（保持原位置与尺寸） ===== */
.stage{
  --hud-top: 1.0%;
  --fx: 50%; --fy: 50%;
  --box-left: 37%; --box-top: 9%; --box-width: 26%; --box-height: 57%;

  --ability-top: 54%;
  --ability-left: 50%;
  --ability-translate-x: -50%;

  --chat-left: 50%;
  --chat-top: 70%;
  --chat-w: 25%;
  --chat-h: 25%;
  --chat-translate-x: -50%;

  position:relative; width:100vw; margin:0 auto; aspect-ratio:16/9; overflow:hidden;
  color:#eaf8ff; background:#000;
  font-family: Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui, -apple-system, "PingFang SC", "Microsoft YaHei";
}
.bg{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; object-position:center; z-index:0; pointer-events:none; }

/* 中间窗口（视频） */
.window-frame{
  position:absolute; inset:0; width:100%; height:97%; z-index:1;
  clip-path: inset(
    var(--box-top)
    calc(100% - var(--box-left) - var(--box-width))
    calc(100% - var(--box-top) - var(--box-height))
    var(--box-left)
  );
  pointer-events:none;
}
.window-video{ object-fit:cover; object-position: var(--fx) var(--fy); pointer-events:none; }

/* 顶部 HUD */
.topbar{ position:absolute; top:var(--hud-top); left:2%; right:2%; z-index:10; display:flex; justify-content:space-between; align-items:center; font-size:14px; pointer-events:auto; }
.left-controls{ display:flex; align-items:center; gap:10px; }
.right-controls{ display:flex; align-items:center; gap:12px; }
.hud-datetime{ margin-left:6px; color:#cfeeff; font-weight:700; text-shadow:0 0 8px rgba(0,190,255,.6); letter-spacing:.2px; white-space:nowrap; }
.hud-btn{
  padding:6px 14px; color:#00eaff; background:rgba(10,22,36,.35);
  border:1px solid rgba(0,234,255,.65); border-radius:10px; cursor:pointer; font-weight:700; font-size:13px; letter-spacing:.3px;
  transition:.22s; box-shadow:0 0 10px rgba(0,238,255,.15) inset, 0 0 0 1px rgba(0,238,255,.12); backdrop-filter: blur(2px);
}
.hud-btn:hover{ background:rgba(0,234,255,.12); box-shadow:0 0 14px rgba(0,238,255,.35), 0 0 0 1px rgba(0,238,255,.45) inset; transform:translateY(-1px); }
.hud-btn:active{ transform:translateY(0); box-shadow:0 0 10px rgba(0,238,255,.25), 0 0 0 1px rgba(0,238,255,.35) inset; }
.hud-btn:disabled{ opacity:.55; cursor:not-allowed; }

/* 能力输出框（含学生姓名 + 高/中/低） */
.ability-badge{
  position:absolute;
  top: 52.5%;
  left: var(--ability-left);
  transform: translateX(var(--ability-translate-x));
  z-index:3;
  font-weight:900;
  letter-spacing:.6px;
  user-select:none;
  text-align:center;
}
.stu-name{
  font-size:18px;
  color:#cfeeff;
  opacity:.95;
  margin-bottom:4px;
  text-shadow:0 0 12px rgba(0,210,255,.35);
}
.ability-level{
  font-size:36px;
  text-shadow:0 0 14px rgba(0,220,255,.35), 0 0 26px rgba(0,120,255,.18);
}
.ability-badge.lvl-high .ability-level{ color:#2affd5; text-shadow:0 0 16px rgba(42,255,213,.45), 0 0 28px rgba(0,180,160,.25); }
.ability-badge.lvl-mid  .ability-level{ color:#ffd257; text-shadow:0 0 16px rgba(255,210,87,.45), 0 0 28px rgba(180,120,0,.25); }
.ability-badge.lvl-low  .ability-level{ color:#ff5a5a; text-shadow:0 0 16px rgba(255,90,90,.45), 0 0 28px rgba(180,0,0,.25); }

/* 能力字入场动画 */
.ability-pop-enter-from { opacity:0; transform: translateX(var(--ability-translate-x)) translateY(-8px) scale(.96); }
.ability-pop-enter-to   { opacity:1; transform: translateX(var(--ability-translate-x)) translateY(0)    scale(1); }
.ability-pop-enter-active{ transition: opacity .7s ease, transform .7s cubic-bezier(.2,.8,.2,1); }

/* 图表区域 */
.chart{ position:absolute; z-index:2; background:transparent!important; border-radius:14px; isolation:isolate; }
.box-left-top{     left:3.5%;  top:14%;   width:30%; height:37%; }
.box-left-bottom{  left:3.5%;  top:58.5%; width:30%; height:37%; }
.box-right-top{    left:66.6%; top:14%;   width:30%; height:37%; }
.box-right-bottom{ left:66.6%; top:58.5%; width:30%; height:37%; }

/* 对话：透明，位置/尺寸可调（字体统一 12px） */
.chat-module{
  position:absolute; left: var(--chat-left); top: var(--chat-top); transform: translateX(var(--chat-translate-x));
  width: var(--chat-w); height: var(--chat-h); display:flex; flex-direction:column; z-index:3;
}
.chat-module.bare{ background:transparent; border:none; box-shadow:none; backdrop-filter:none; }
.chat-window{ flex:1; overflow-y:auto; padding:10px; scrollbar-width:thin; font-size:12px; line-height:1.6; }
.chat-window.bare{ background:transparent; }
.chat-msg{ margin-bottom:8px; }
.chat-msg.user{ text-align:right; color:#a7f0ff; text-shadow:0 0 10px rgba(20,220,255,.25); }
.chat-msg.bot{  text-align:left;  color:#eaf8ff; text-shadow:0 0 10px rgba(255,255,255,.15); }
.chat-input{ display:flex; }
.chat-input.bare{ border:none; background:transparent; }
.chat-input input{
  flex:1; padding:8px; background:rgba(8,14,28,.35); color:#eaf8ff;
  border:1px solid rgba(0,234,255,.25); border-radius:10px 0 0 10px; outline:none; font-size:12px;
}
.chat-input button{
  padding:8px 12px; color:#001a22; background:linear-gradient(90deg,#35f5ff,#22c8ff);
  border:none; border-radius:0 10px 10px 0; cursor:pointer; font-weight:800; letter-spacing:.3px; font-size:12px;
}

/* ===== 科技风滚动条 ===== */
:deep(.stage), :deep(.stage *){ scrollbar-width: thin; scrollbar-color: rgba(0,234,255,.5) rgba(10,18,36,.18); }
:deep(.stage::-webkit-scrollbar), :deep(.stage *::-webkit-scrollbar){ width:8px; height:8px; }
:deep(.stage::-webkit-scrollbar-track), :deep(.stage *::-webkit-scrollbar-track){
  background:linear-gradient(180deg, rgba(0,35,69,.25), rgba(0,0,0,.15));
  border-radius:10px;
}
:deep(.stage::-webkit-scrollbar-thumb), :deep(.stage *::-webkit-scrollbar-thumb){
  background:linear-gradient(180deg, rgba(0,234,255,.8), rgba(0,156,255,.7));
  border-radius:10px;
  box-shadow:0 0 10px rgba(0,238,255,.35);
  border:1px solid rgba(0,234,255,.35);
}
:deep(.stage::-webkit-scrollbar-thumb:hover), :deep(.stage *::-webkit-scrollbar-thumb:hover){
  background:linear-gradient(180deg, rgba(0,255,255,.95), rgba(0,176,255,.85));
}
</style>
