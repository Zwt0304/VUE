<template>
  <div class="stage">
    <img class="bg" src="/bg/BG.jpg" srcset="/bg/BG.jpg 1x, /bg/BG@2x.jpg 2x" sizes="100vw" alt="背景" loading="eager" decoding="sync" fetchpriority="high" draggable="false" />

    <!-- 上传态：科技蓝 CTA；分析态：视频（同一裁剪窗口） -->
    <button
      v-if="mode==='upload'"
      class="window-frame window-cta"
      @click="startAnalysisFromCTA"
      :disabled="!hasData"
      title="请先在右上角选择并上传Excel数据">
      <span class="pulse"></span>
      <span class="pulse delay"></span>
      <span class="cta-text">开始分析</span>
      <small class="cta-sub">{{ hasData ? '数据就绪 · 点击进入分析' : '未加载数据 · 先选择文件' }}</small>
    </button>

    <video
      v-if="logoOK && mode==='analysis'"
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
      <div class="right-controls">
        <template v-if="mode==='upload'">
          <label class="hud-btn file-btn" title="选择 Excel（.xls/.xlsx）">
            选择文件
            <input type="file" accept=".xls,.xlsx" @change="handleFile" hidden />
          </label>
          <button class="hud-btn" :disabled="!hasData" @click="resetData">重置数据</button>
        </template>
      </div>
    </header>

    <!-- 能力炫酷字：仅视频出现后再显示 + 入场动画 -->
    <transition name="ability-pop">
      <div
        v-if="mode==='analysis' && abilityVisible"
        class="ability-badge"
        :class="abilityClass">
        {{ abilityText }}
      </div>
    </transition>

    <!-- 四图 -->
    <div id="radar" class="chart box-left-top"></div>
    <div id="emo"   class="chart box-left-bottom"></div>
    <div id="line"  class="chart box-right-top"></div>
    <div id="cog"   class="chart box-right-bottom"></div>

    <!-- 智能对话：初始即呈现、无边框无背景（学生页独立，不与教师页共享） -->
    <div class="chat-module bare">
      <div class="chat-window bare">
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
import axios from 'axios';
import { useRouter } from 'vue-router';
import logo from '../assets/techlogo.mp4';
import * as echarts from 'echarts'; // 显式引入，防止 window.echarts 未定义
if (!window.echarts) window.echarts = echarts;

const router = useRouter();
const logoOK = true;
const mode = ref('upload'); // 'upload' | 'analysis'
const hasData = ref(false);
const studentData = ref(null);

/* ===== 名称映射（全中文） ===== */
const NAME_MAP = {
  CEM:'明确评价方式', CLT:'明确学习任务', VC:'查看课程', RA:'资源访问', DI:'讨论互动',
  TC:'任务完成', SH:'寻求帮助', PM:'过程监控', LR:'学习反思', LE:'学习评价',
  Affect:'情感体验', PosEmo:'积极情绪', CogMech:'认知能力', Insight:'反思能力'
};
const SEQ_KEYS = [
  'CEM→CEM','CLT→VC','CLT→TC','CLT→LR',
  'VC→CLT','VC→VC','RA→CEM','RA→RA',
  'DI→DI','DI→LR','TC→TC','TC→PM',
  'PM→VC','PM→TC','PM→PM','LR→LR'
];
const SEQ_CN = SEQ_KEYS.map(k => k.split('→').map(p => NAME_MAP[p] || p).join('→'));

/* ===== 能力炫酷字（仅视频出现后显示） ===== */
const abilityText = ref('');
const abilityClass = computed(() => {
  if (abilityText.value === '高') return 'lvl-high';
  if (abilityText.value === '中') return 'lvl-mid';
  if (abilityText.value === '低') return 'lvl-low';
  return '';
});
const abilityVisible = ref(false);
const videoEl = ref(null);
let abilityTimer = null;

/* ===== 时钟 ===== */
const dateTimeFull = ref('');
let timer;
function pad(n){ return n<10 ? '0'+n : ''+n; }
function fmt(now){
  const y=now.getFullYear(), m=pad(now.getMonth()+1), d=pad(now.getDate());
  const hh=pad(now.getHours()), mm=pad(now.getMinutes()), ss=pad(now.getSeconds());
  const wk=now.toLocaleDateString('zh-CN',{ weekday:'long' }).replace('周','星期');
  return `${y}-${m}-${d} ${hh}:${mm}:${ss} ${wk}`;
}
function tick(){ dateTimeFull.value = fmt(new Date()); }

/* ===== 导航/重置 ===== */
function goHome(){ router.push('/'); }
async function goBack(){
  clearTimeout(abilityTimer);
  abilityVisible.value = false;
  if (mode.value === 'analysis') {
    mode.value = 'upload';
    await nextTick();
    initChartsBase();
    if (studentData.value) primeUploadZeroThenAnimate(studentData.value, true);
    else renderUploadPlaceholders();
  } else router.back();
}
async function resetData(){
  sessionStorage.removeItem('studentData');
  studentData.value = null;
  hasData.value = false;
  clearTimeout(abilityTimer);
  abilityVisible.value = false;
  await nextTick();
  initChartsBase();
  renderUploadPlaceholders();
}

/* ===== ECharts 公共 ===== */
let radar, line, emo, cog, ro;
const COLOR_ME = '#19e4ff';
const COLOR_ME_AREA = 'rgba(25,228,255,0.14)';
const COLOR_ME_SHADOW = 'rgba(25,228,255,0.65)';
const COLOR_GROUP = '#ff5a5a';
const COLOR_GROUP_AREA = 'rgba(255,90,90,0.12)';
const COLOR_GROUP_SHADOW = 'rgba(255,90,90,0.55)';
const format3 = v => (typeof v === 'number' ? Number(v).toFixed(3) : v);

const dot = c => `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};margin-right:6px;vertical-align:1px;"></span>`;
const tipTitle = t => `<div style="margin-bottom:4px;">${t}</div>`;
const tipLineMe = v => `${dot(COLOR_ME)}我：${format3(v)}`;
const tipLineGrp = v => `${dot(COLOR_GROUP)}高群体：${format3(v)}`;
const tipTwoLines = (title, me, grp) => tipTitle(title) + tipLineMe(me) + '<br/>' + tipLineGrp(grp);

/* —— 统一：图表字号 12px + 数值坐标三位小数 —— */
function hudAxis(ec){
  return {
    axisLine:{ lineStyle:{ color:'rgba(120,220,255,0.65)', width:1.2 } },
    axisTick:{ show:false },
    axisLabel:{ color:'#cfeeff', fontSize:12, fontWeight:600, fontFamily:'Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui' },
    splitLine:{ lineStyle:{ color:'rgba(0,180,255,0.18)', width:1 } }
  };
}
function valueAxisFmt(base){
  const b = hudAxis().axisLabel;
  return { ...b, formatter: v => (typeof v === 'number' ? Number(v).toFixed(3) : v) };
}
function hudTooltip(){
  return {
    trigger:'axis',
    backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10,
    textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
    axisPointer:{ type:'line', lineStyle:{ color:'#00eaff', width:1, type:'dashed' }, z:99 },
    extraCssText:'backdrop-filter: blur(4px);',
    confine:true
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
  if (!ec) return;
  [radar,line,emo,cog].forEach(ins => { if(ins) ec.dispose(ins); });
  radar = line = emo = cog = null;
}

/* —— 单维点位系列（允许悬停；不做淡化）—— */
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

/* ===== 慢速动画参数 ===== */
const ENTER_MS = 2400;
const UPDATE_MS = 1200;
const DELAY_STEP = 80;
const delayByIndex = i => i*DELAY_STEP;

/* ===== 统一 init ===== */
function initChartsBase(){
  const ec = window.echarts;
  if (!ec) return; // 防护
  const DPR = Math.min(window.devicePixelRatio || 1, 2.5);
  const make = (id)=>{
    const el = document.getElementById(id);
    if (!el) return null; // 防护：DOM 未就绪
    const old = ec.getInstanceByDom(el); if (old) ec.dispose(old);
    return ec.init(el, null, { backgroundColor:'transparent', renderer:'canvas', devicePixelRatio:DPR });
  };
  disposeAll();
  radar = make('radar'); line = make('line'); emo = make('emo'); cog = make('cog');

  window.addEventListener('resize', resizeAll, { passive:true });
  if (ro) ro.disconnect(); ro = new ResizeObserver(resizeAll);
  const host = document.querySelector('.stage');
  if (host) ro.observe(host);
}
function resizeAll(){ [radar,line,emo,cog].forEach(ins=>ins && ins.resize()); }

/* ===== 入场动画策略：先零帧，再真帧 ===== */
function nextFrame(cb){ requestAnimationFrame(()=>{ requestAnimationFrame(cb); }); }
function primeUploadZeroThenAnimate(d, isBack){ renderUploadZero(d); nextFrame(()=>{ renderUploadFromData(d, isBack); }); }
function primeAnalysisZeroThenAnimate(d){ renderAnalysisZero(d); nextFrame(()=>{ renderAnalysisFromData(d); }); }

/* ===== 数据名中文化辅助 ===== */
function toCN(name){
  if (NAME_MAP[name]) return NAME_MAP[name];
  // 形如 "CEM→CEM"
  if (name && name.includes('→')) {
    return name.split('→').map(n => NAME_MAP[n] || n).join('→');
  }
  return name;
}
function arrNamesCN(pairs){ return pairs.map(it => [toCN(it[0]), it[1]]); }

/* ===== 上传态：零帧（仅“我”都是0） ===== */
function renderUploadZero(d){
  const ec = window.echarts; if (!ec || !radar) return;
  const freqCN = arrNamesCN(d.behavior_freq || []);
  const emoCN  = arrNamesCN(d.emotion || []);
  const cogCN  = arrNamesCN(d.cognition || []);

  const IND = freqCN.map(i => ({ name:i[0], max:1 }));
  const zeros = n => Array(n).fill(0);

  radar.setOption({
    animation:false, legend:{ show:false }, tooltip:{ trigger:'item', triggerOn:'none' },
    radar:{
      indicator: IND,
      axisName:{ color:'#cfeeff', fontFamily:'Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui', fontWeight:700 },
      splitArea:{ show:true, areaStyle:{ color:['rgba(0,180,255,0.05)','rgba(0,180,255,0.02)'] } },
      splitLine:{ lineStyle:{ color:'rgba(0,210,255,0.25)' } },
      axisLine:{ lineStyle:{ color:'rgba(0,210,255,0.25)' } }
    },
    series:[
      { name:'我', type:'radar', data:[{ value: zeros(IND.length), name:'我' }],
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_ME_SHADOW, color:COLOR_ME },
        itemStyle:{ color:COLOR_ME }, areaStyle:{ color:COLOR_ME_AREA } },
      ].concat(buildRadarPointSeries('我', zeros(IND.length), COLOR_ME))
  }, { notMerge:true });

  const seqLen = (d.behavior_seq || []).length;
  const xcats = Array.from({length:seqLen}, (_,i)=>i+1);
  line.setOption({
    animation:false, tooltip:hudTooltip(),
    grid:{ left:40, right:20, top:16, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: xcats, ...hudAxis(ec) },
    yAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[{ type:'line', data:Array(seqLen).fill(0), smooth:true,
      lineStyle:neonLine(ec), symbol:'circle', symbolSize:6,
      itemStyle:{ color:'#21ffe3', shadowBlur:10, shadowColor:'rgba(0,255,214,0.8)' },
      areaStyle:{ color:'rgba(0,238,255,0.08)' } }]
  }, { notMerge:true });

  emo.setOption({
    animation:false, tooltip:hudTooltip(),
    grid:{ left:40, right:20, top:16, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: emoCN.map(x=>x[0]), ...hudAxis(ec) },
    yAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[{ type:'bar', data: emoCN.map(()=>0), itemStyle:neonBar(ec), barWidth:'42%' }]
  }, { notMerge:true });

  cog.setOption({
    animation:false, tooltip:{ trigger:'axis', ...hudTooltip() },
    grid:{ left:56, right:20, top:16, bottom:24, containLabel:true },
    yAxis:{ type:'category', data: cogCN.map(x=>x[0]),
      axisLabel: hudAxis(ec).axisLabel, axisLine: hudAxis(ec).axisLine, splitLine:{ show:false } },
    xAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[{ type:'bar', data: cogCN.map(()=>0), itemStyle:neonBar(ec), barWidth:'42%' }]
  }, { notMerge:true });
}

/* ===== 上传态：真帧（仅“我”，慢速动画） ===== */
function renderUploadFromData(d, back){
  const ec = window.echarts; if (!ec || !radar) return;
  const freqCN = arrNamesCN(d.behavior_freq || []);
  const emoCN  = arrNamesCN(d.emotion || []);
  const cogCN  = arrNamesCN(d.cognition || []);
  const IND = freqCN.map(i => ({ name:i[0], max:1 }));
  const myFreq = freqCN.map(v=>v[1]);
  const mySeq  = (d.behavior_seq || []).map(v=>v[1]);
  const myEmo  = emoCN.map(v=>v[1]);
  const myCog  = cogCN.map(v=>v[1]);
  const dur = back ? UPDATE_MS : ENTER_MS;

  radar.setOption({
    animation:true, animationDuration:dur, animationEasing:'cubicOut',
    legend:{ show:false },
    tooltip:{
      trigger:'item', triggerOn:'mousemove|click',
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter: p => {
        const m=/^(我)-p(\d+)$/.exec(p.seriesName); if(!m) return '';
        const i=+m[2]; return tipTitle(IND[i].name) + tipLineMe(myFreq[i]);
      }
    },
    radar:{
      indicator:IND,
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
      }
    ].concat(buildRadarPointSeries('我', myFreq, COLOR_ME))
  }, { notMerge:true });

  const xcats = (d.behavior_seq || []).map((_,i)=>i+1);
  line.setOption({
    animation:true, animationDuration:dur, animationDurationUpdate:UPDATE_MS, animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    tooltip:{
      ...hudTooltip(),
      formatter: ps => {
        const idx = (ps && ps[0]) ? ps[0].dataIndex : 0;
        return tipTitle(SEQ_CN[idx] || `序列 ${idx+1}`) + tipLineMe(mySeq[idx]);
      }
    },
    grid:{ left:40, right:20, top:16, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: xcats, ...hudAxis(ec) },
    yAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[{
      name:'我', type:'line', data: mySeq, smooth:true, showAllSymbol:true,
      symbol:'circle', symbolSize:6, lineStyle:neonLine(ec), itemStyle:{ color:COLOR_ME },
      areaStyle:{ color:'rgba(0,238,255,0.08)' },
      universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex
    }]
  }, { notMerge:true });

  emo.setOption({
    animation:true, animationDuration:dur, animationDurationUpdate:UPDATE_MS, animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    tooltip:hudTooltip(),
    grid:{ left:40, right:20, top:16, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: emoCN.map(x=>x[0]), ...hudAxis(ec) },
    yAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[{
      name:'我', type:'bar', data: myEmo, itemStyle:neonBar(ec), barWidth:'42%',
      universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex
    }]
  }, { notMerge:true });

  cog.setOption({
    animation:true, animationDuration:dur, animationDurationUpdate:UPDATE_MS, animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    tooltip:{ trigger:'axis', ...hudTooltip() },
    grid:{ left:56, right:20, top:16, bottom:24, containLabel:true },
    yAxis:{ type:'category', data: cogCN.map(x=>x[0]),
      axisLabel: hudAxis(ec).axisLabel, axisLine: hudAxis(ec).axisLine, splitLine:{ show:false } },
    xAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[{
      name:'我', type:'bar', data: myCog, itemStyle:neonBar(ec), barWidth:'42%',
      universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex
    }]
  }, { notMerge:true });
}

/* ====== 分析态：零帧（我/群体都为0） ====== */
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

function renderAnalysisZero(d){
  const ec = window.echarts; if (!ec || !radar) return;
  const freqCN = arrNamesCN(d.behavior_freq || []);
  const emoCN  = arrNamesCN(d.emotion || []);
  const cogCN  = arrNamesCN(d.cognition || []);
  const indicators = freqCN.map(i=>({ name:i[0], max:1 }));

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
      { name:'我', type:'radar', data:[{ value: freqCN.map(()=>0), name:'我' }],
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_ME_SHADOW, color:COLOR_ME },
        itemStyle:{ color:COLOR_ME }, areaStyle:{ color:COLOR_ME_AREA } },
      { name:'高群体', type:'radar', data:[{ value: avgFreq.map(()=>0), name:'高群体' }],
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_GROUP_SHADOW, color:COLOR_GROUP },
        itemStyle:{ color:COLOR_GROUP }, areaStyle:{ color:COLOR_GROUP_AREA } }
    ]
    .concat(buildRadarPointSeries('我', freqCN.map(()=>0), COLOR_ME))
    .concat(buildRadarPointSeries('高群体', avgFreq.map(()=>0), COLOR_GROUP))
  }, { notMerge:true });

  const xcats = (d.behavior_seq || []).map((_,i)=>i+1);
  line.setOption({
    animation:false,
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:hudTooltip(),
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: xcats, ...hudAxis(ec) },
    yAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[
      { name:'我', type:'line', data: xcats.map(()=>0), smooth:true, showAllSymbol:true,
        symbol:'circle', symbolSize:6, lineStyle:neonLine(ec), itemStyle:{ color:COLOR_ME },
        areaStyle:{ color:'rgba(25,228,255,0.08)' } },
      { name:'高群体', type:'line', data: avgSeq.map(()=>0), smooth:true, showAllSymbol:true,
        symbol:'circle', symbolSize:6,
        lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_GROUP_SHADOW, color:COLOR_GROUP },
        itemStyle:{ color:COLOR_GROUP }, areaStyle:{ color:'rgba(255,90,90,0.08)' } }
    ]
  }, { notMerge:true });

  const emoCats = emoCN.map(i=>i[0]);
  emo.setOption({
    animation:false,
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      trigger:'axis', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter: ps => {
        const idx=(ps&&ps[0])?ps[0].dataIndex:0;
        return tipTitle(emoCats[idx]) + tipLineMe(0) + '<br/>' + tipLineGrp(0);
      }
    },
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: emoCats, ...hudAxis(ec) },
    yAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[
      { name:'我', type:'bar', data: emoCats.map(()=>0), itemStyle:neonBar(ec), barWidth:'42%' },
      { name:'高群体', type:'bar', data: avgEmo.map(()=>0), itemStyle:{ color: COLOR_GROUP, shadowBlur:12, shadowColor: COLOR_GROUP_SHADOW, opacity:.9 }, barWidth:'42%' }
    ]
  }, { notMerge:true });

  const cogCats = cogCN.map(i=>i[0]);
  cog.setOption({
    animation:false,
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      trigger:'axis', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter: ps => {
        const idx=(ps&&ps[0])?ps[0].dataIndex:0;
        return tipTitle(cogCats[idx]) + tipLineMe(0) + '<br/>' + tipLineGrp(0);
      }
    },
    grid:{ left:60, right:20, top:30, bottom:24, containLabel:true },
    yAxis:{ type:'category', data: cogCats,
      axisLabel: hudAxis(ec).axisLabel, axisLine: hudAxis(ec).axisLine, splitLine:{ show:false } },
    xAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[
      { name:'我', type:'bar', data: cogCats.map(()=>0), itemStyle:neonBar(ec), barWidth:'42%' },
      { name:'高群体', type:'bar', data: avgCog.map(()=>0), itemStyle:{ color: COLOR_GROUP, shadowBlur:12, shadowColor: COLOR_GROUP_SHADOW, opacity:.9 }, barWidth:'42%' }
    ]
  }, { notMerge:true });
}

/* ====== 分析态：真帧（慢速动画） ====== */
function renderAnalysisFromData(d){
  const ec = window.echarts; if (!ec || !radar) return;
  const freqCN = arrNamesCN(d.behavior_freq || []);
  const emoCN  = arrNamesCN(d.emotion || []);
  const cogCN  = arrNamesCN(d.cognition || []);
  const myFreq = freqCN.map(v=>v[1]);
  const mySeq  = (d.behavior_seq || []).map(v=>v[1]);
  const myEmo  = emoCN.map(v=>v[1]);
  const myCog  = cogCN.map(v=>v[1]);
  const indicators = freqCN.map(i=>({ name:i[0], max:1 }));
  abilityText.value = ['低','中','高'][Number(d.ability)] || '未知';

  radar.setOption({
    animation:true, animationDuration:ENTER_MS, animationEasing:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      trigger:'item', triggerOn:'mousemove|click',
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter:p=>{
        const m=/^(我|高群体)-p(\d+)$/.exec(p.seriesName); if(!m) return '';
        const i=+m[2]; const name=indicators[i].name;
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

  const xcats = (d.behavior_seq || []).map((_,i)=>i+1);
  line.setOption({
    animation:true, animationDuration:ENTER_MS, animationDurationUpdate:UPDATE_MS, animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      ...hudTooltip(),
      formatter: ps => { const idx=(ps&&ps[0])?ps[0].dataIndex:0;
        return tipTwoLines(SEQ_CN[idx] || `序列 ${idx+1}`, mySeq[idx], avgSeq[idx]); }
    },
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: xcats, ...hudAxis(ec) },
    yAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
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

  const emoCats = emoCN.map(i=>i[0]);
  emo.setOption({
    animation:true, animationDuration:ENTER_MS, animationDurationUpdate:UPDATE_MS, animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      trigger:'axis', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter: ps => { const idx=(ps&&ps[0])?ps[0].dataIndex:0;
        return tipTwoLines(emoCats[idx], myEmo[idx], avgEmo[idx]); }
    },
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: emoCats, ...hudAxis(ec) },
    yAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[
      { name:'我', type:'bar', data: myEmo,
        itemStyle:neonBar(ec), barWidth:'42%',
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex },
      { name:'高群体', type:'bar', data: avgEmo,
        itemStyle:{ color: COLOR_GROUP, shadowBlur:12, shadowColor: COLOR_GROUP_SHADOW, opacity:.9 }, barWidth:'42%',
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex }
    ]
  }, { notMerge:true });

  const cogCats = cogCN.map(i=>i[0]);
  cog.setOption({
    animation:true, animationDuration:ENTER_MS, animationDurationUpdate:UPDATE_MS, animationEasing:'cubicOut', animationEasingUpdate:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:12 }, data:['我','高群体'] },
    tooltip:{
      trigger:'axis', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:12, fontWeight:600 },
      formatter: ps => { const idx=(ps&&ps[0])?ps[0].dataIndex:0;
        return tipTwoLines(cogCats[idx], myCog[idx], avgCog[idx]); }
    },
    grid:{ left:60, right:20, top:30, bottom:24, containLabel:true },
    yAxis:{ type:'category', data: cogCats,
      axisLabel: hudAxis(ec).axisLabel, axisLine: hudAxis(ec).axisLine, splitLine:{ show:false } },
    xAxis:{ type:'value', axisLabel: valueAxisFmt().formatter, ...hudAxis(ec) },
    series:[
      { name:'我', type:'bar', data: myCog,
        itemStyle:neonBar(ec), barWidth:'42%',
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex },
      { name:'高群体', type:'bar', data: avgCog,
        itemStyle:{ color: COLOR_GROUP, shadowBlur:12, shadowColor: COLOR_GROUP_SHADOW, opacity:.9 }, barWidth:'42%',
        universalTransition:true, animationDelay: delayByIndex, animationDelayUpdate: delayByIndex }
    ]
  }, { notMerge:true });
}

/* ===== 上传 ===== */
async function handleFile(e){
  const file = e.target.files && e.target.files[0]; if(!file) return;
  const fd = new FormData(); fd.append('file', file);
  try{
    const res = await axios.post('/api/analyze', fd);
    if(res.data.error){ alert(res.data.error); return; }
    if(res.data.role !== 'student'){ alert('请上传单个学生数据'); return; }
    sessionStorage.setItem('studentData', JSON.stringify(res.data));
    studentData.value = res.data; hasData.value = true;

    await nextTick();
    initChartsBase();
    primeUploadZeroThenAnimate(res.data, false);
  }catch(err){
    alert((err && err.response && err.response.data && err.response.data.error) || err.message || '上传失败');
  }
}

/* ===== 进入分析（CTA） ===== */
async function startAnalysisFromCTA(){
  if (!hasData.value || !studentData.value) { alert('请先在右上角“选择文件”上传学生数据'); return; }
  clearTimeout(abilityTimer);
  abilityVisible.value = false; // 视频出现后再显示
  mode.value = 'analysis';
  await nextTick();
  initChartsBase();
  primeAnalysisZeroThenAnimate(studentData.value);

  // 兜底显示能力字
  abilityTimer = setTimeout(()=>{ abilityVisible.value = true; }, 1200);

  // 本地提示
  setTimeout(()=>{ typePush('分析完成 ✅ 已生成四个图表；如需解读或个性化建议，请直接提问。', 'bot'); }, ENTER_MS + 500);
}
function onVideoCanPlay(){
  clearTimeout(abilityTimer);
  abilityTimer = setTimeout(()=>{ abilityVisible.value = true; }, 300);
}

/* ===== 对话（含逐字打字效果；学生页独立） ===== */
const messages = ref([]);
const userInput = ref('');
const TYPING_INTERVAL = 16;
const TYPING_CHARS_PER_TICK = 2;
function typePush(text, sender='bot'){
  const msg = { sender, text:'' };
  messages.value.push(msg);
  let i = 0;
  (function step(){
    if(i < text.length){
      msg.text += text.slice(i, i + TYPING_CHARS_PER_TICK);
      i += TYPING_CHARS_PER_TICK;
      setTimeout(step, TYPING_INTERVAL);
    }else{
      msg.text = text;
    }
  })();
}

async function sendMessage(){
  const text = (userInput.value || '').trim(); if(!text) return;
  messages.value.push({ sender:'user', text });
  userInput.value='';
  try{
    const ctx = studentData.value ? {
      role:'student', ability: studentData.value.ability,
      behavior_freq: studentData.value.behavior_freq, behavior_seq: studentData.value.behavior_seq,
      emotion: studentData.value.emotion, cognition: studentData.value.cognition
    } : null;
    const res = await axios.post('/api/chat', { message: text, scene:'student', context: ctx });
    const reply = (res && res.data && res.data.reply) ? res.data.reply : '未收到回复';
    typePush(reply + ' 🙂', 'bot');
  }catch{
    typePush('对话出错，请稍后再试 🙏', 'bot');
  }
}

/* ===== 占位（未上传数据时） ===== */
function renderUploadPlaceholders(){
  const placeholder = '等待上传数据…';
  [radar, line, emo, cog].forEach(ins=>{
    if(!ins) return;
    ins.clear();
    ins.setOption({ graphic:[{ type:'text', left:'center', top:'middle', style:{ text: placeholder, fill:'#a8d9ff', font:'700 12px Rajdhani, system-ui' } }] });
  });
}

/* ===== 生命周期 ===== */
onMounted(()=>{
  tick(); timer = setInterval(tick, 1000);
  initChartsBase();
  const saved = sessionStorage.getItem('studentData');
  if(saved){
    try{
      studentData.value = JSON.parse(saved); hasData.value = true;
      primeUploadZeroThenAnimate(studentData.value, false);
    }catch{ hasData.value=false; renderUploadPlaceholders(); }
  }else{
    renderUploadPlaceholders();
  }
  // 统一的欢迎语（学生页也加表情）
  typePush('你好，我是智能分析助手 🤖✨  已就绪，问我任何问题都可以～', 'bot');
});
onBeforeUnmount(()=>{
  clearInterval(timer);
  clearTimeout(abilityTimer);
  disposeAll(); if (ro) ro.disconnect();
});
</script>

<style scoped>
/* ===== 全局参数（不改你的布局） ===== */
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

/* 中间窗口（视频/CTA共用） */
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

/* 科技蓝 CTA（不改尺寸，仅视觉） */
.window-cta{
  inset:auto;
  left: var(--box-left);
  top: var(--box-top);
  width: var(--box-width);
  height: calc(var(--box-height) * 0.965);
  clip-path:none;

  pointer-events:auto;

  display:grid; place-items:center; cursor:pointer; border:1px solid rgba(0,234,255,.45);
  background:
    radial-gradient(60% 80% at 50% 50%, rgba(0,210,255,.16), rgba(0,0,0,0) 60%),
    linear-gradient(180deg, rgba(10,18,36,.65), rgba(10,18,36,.35));
  box-shadow: 0 0 18px rgba(0,238,255,.18) inset, 0 0 14px rgba(0,238,255,.12);
  backdrop-filter: blur(2px); color:#eaf8ff;
}
.window-cta:disabled{ cursor:not-allowed; opacity:.75; }
.window-cta .cta-text{ font-size:30px; font-weight:900; letter-spacing:.4px; text-shadow:0 0 14px rgba(0,220,255,.35), 0 0 22px rgba(0,120,255,.18); }
.window-cta .cta-sub{ margin-top:8px; font-size:13px; color:#c6eeff; opacity:.92; }
.window-cta .pulse, .window-cta .pulse.delay{
  position:absolute; width:30%; aspect-ratio:1; border-radius:999px;
  border:1px solid rgba(0,234,255,.55); box-shadow:0 0 12px rgba(0,238,255,.35);
  animation:pulse 2.4s ease-out infinite;
}
.window-cta .pulse.delay{ animation-delay:.9s; }
@keyframes pulse{ 0%{transform:scale(.8);opacity:.85;} 70%{transform:scale(2);opacity:0;} 100%{transform:scale(2);opacity:0;} }

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
.file-btn{ position:relative; overflow:hidden; }

/* 能力炫酷字 */
.ability-badge{
  position:absolute; top: var(--ability-top); left: var(--ability-left); transform: translateX(var(--ability-translate-x));
  z-index:3; font-weight:900; letter-spacing:.6px; user-select:none; font-size:36px;
  text-shadow:0 0 14px rgba(0,220,255,.35), 0 0 26px rgba(0,120,255,.18);
}
.ability-badge.lvl-high{ color:#2affd5; text-shadow:0 0 16px rgba(42,255,213,.45), 0 0 28px rgba(0,180,160,.25); }
.ability-badge.lvl-mid { color:#ffd257; text-shadow:0 0 16px rgba(255,210,87,.45), 0 0 28px rgba(180,120,0,.25); }
.ability-badge.lvl-low { color:#ff5a5a; text-shadow:0 0 16px rgba(255,90,90,.45), 0 0 28px rgba(180,0,0,.25); }

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

/* 对话：透明，位置/尺寸可调 —— 字号统一 12px */
.chat-module{
  position:absolute; left: var(--chat-left); top: var(--chat-top); transform: translateX(var(--chat-translate-x));
  width: var(--chat-w); height: var(--chat-h); display:flex; flex-direction:column; z-index:3;
}
.chat-module.bare{ background:transparent; border:none; box-shadow:none; backdrop-filter:none; }
.chat-window{ flex:1; overflow-y:auto; padding:10px; scrollbar-width:thin; font-size:12px; }
.chat-window.bare{ background:transparent; }
.chat-msg{ margin-bottom:8px; line-height:1.4; }
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

/* ===== 霓虹滚动条（仅作用于本页面 .stage 容器内） ===== */
.stage *{
  scrollbar-width: thin;
  scrollbar-color: rgba(0,234,255,.6) rgba(10,18,36,.25);
}
.stage *::-webkit-scrollbar{
  width:10px; height:10px;
}
.stage *::-webkit-scrollbar-track{
  background: linear-gradient(180deg, rgba(10,18,36,.25), rgba(10,18,36,.05));
  border-radius:12px;
}
.stage *::-webkit-scrollbar-thumb{
  background: linear-gradient(180deg, #2af6ff, #14b7ff);
  border:1px solid rgba(0,234,255,.55);
  border-radius:12px;
  box-shadow: 0 0 10px rgba(0,238,255,.35) inset, 0 0 8px rgba(0,238,255,.35);
}
.stage *::-webkit-scrollbar-thumb:hover{
  filter: brightness(1.1);
}
</style>
