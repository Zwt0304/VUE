<!-- src/components/TeacherDashboard.vue -->
<template>
  <div class="stage">
    <!-- 背景（与学生端一致） -->
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

    <!-- 顶部 HUD（按钮可点、空白不拦截） -->
    <header class="topbar">
      <div class="left-controls">
        <button class="hud-btn" @click="goHome">首页</button>
        <button class="hud-btn" @click="goBack">返回</button>
        <span class="hud-datetime">{{ dateTimeFull }}</span>
      </div>
      <div class="right-controls">
        <label class="hud-btn file-btn" title="选择 Excel（.xls/.xlsx）">
          选择文件
          <input type="file" accept=".xls,.xlsx" @change="handleFile" hidden />
        </label>
        <button class="hud-btn" :disabled="!teacherData" @click="resetData">重置数据</button>
      </div>
    </header>

    <!-- 四角图表 -->
    <div id="radar" class="chart box-left-top"></div>
    <div id="line"  class="chart box-right-top"></div>
    <div id="emo"   class="chart box-left-bottom"></div>
    <div id="cog"   class="chart box-right-bottom"></div>

    <!-- 中心列：迷你分布图（性别 + 年级） + 表格 -->
    <div class="center-content">
      <div class="mini-row">
        <div id="genderPie" class="chart mini-chart"></div>
        <div id="gradePie"  class="chart mini-chart"></div>
      </div>

      <div
        ref="tableContainer"
        class="table-container"
        @mouseenter="hovering = true"
        @mouseleave="hovering = false"
        @wheel="onWheel"
      >
        <table>
          <thead>
            <tr>
              <th>序号</th><th>姓名</th><th>性别</th><th>年级</th><th>水平</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!teacherData">
              <td colspan="5" class="empty">等待上传数据…</td>
            </tr>
            <tr
              v-else
              v-for="(stu, i) in teacherData.students"
              :key="i"
              @click="goStudent(i)"
            >
              <td :style="styleIndex(i)">{{ i + 1 }}</td>
              <td>{{ stu.姓名 || '未知' }}</td>
              <td :style="styleGender(stu.性别)">{{ stu.性别 || '未知' }}</td>
              <td :style="styleGrade(stu.年级)">{{ stu.年级 || '未知' }}</td>
              <td :style="styleLevel(stu.预测元认知能力)">{{ levelMap[stu.预测元认知能力] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 智能对话（无边框、透明背景、同位置尺寸） -->
    <div class="chat-module bare">
      <div class="chat-window bare" ref="chatWindow">
        <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-msg', msg.sender]">
          <span>{{ msg.text }}</span>
          <span v-if="msg.typing" class="chat-caret"></span>
        </div>
      </div>
      <div class="chat-input bare">
        <input
          v-model="userInput"
          :disabled="isChatLoading"
          @keyup.enter="sendMessage"
          placeholder="输入你的问题..."
        />
        <button @click="sendMessage" :disabled="isChatLoading">
          {{ isChatLoading ? '发送中…' : '发送' }}
        </button>
      </div>
    </div>

    <NavBar class="nav" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import NavBar from './NavBar.vue';
import * as echarts from 'echarts';
if (!window.echarts) window.echarts = echarts;

/* ===== 常量：统一字号 ===== */
const FONT_12 = 12;

/* ===== 映射（显示中文；数据键保留英文以便取值） ===== */
const NAME_MAP = {
  CEM:'明确评价方式', CLT:'明确学习任务', VC:'查看课程', RA:'资源访问', DI:'讨论互动',
  TC:'任务完成', SH:'寻求帮助', PM:'过程监控', LR:'学习反思', LE:'学习评价',
  Affect:'情感体验', PosEmo:'积极情绪', CogMech:'认知能力', Insight:'反思能力'
};
const behavior_freq_cols = ['CEM','CLT','VC','RA','DI','TC','PM','LR']; // 以你现有数据为准
const behavior_seq_cols = [
  'CEM→CEM','CLT→VC','CLT→TC','CLT→LR',
  'VC→CLT','VC→VC','RA→CEM','RA→RA',
  'DI→DI','DI→LR','TC→TC','TC→PM',
  'PM→VC','PM→TC','PM→PM','LR→LR'
];
const emotion_cols   = ['Affect','PosEmo'];
const cognition_cols = ['CogMech','Insight'];
const SEQ_CN = behavior_seq_cols.map(k => k.split('→').map(p => NAME_MAP[p] || p).join('→'));
const levelMap = ['低','中','高'];

/* ===== 配色 ===== */
const COLOR_ME = '#19e4ff';
const COLOR_ME_AREA = 'rgba(25,228,255,0.14)';
const COLOR_ME_SHADOW = 'rgba(25,228,255,0.65)';
const LEVEL_COLOR = { 0:'#ff5a5a', 1:'#ffd257', 2:'#2affd5' };
const genderColorMap = { '男':'#22c8ff', '女':'#ff86de' };
const gradeColorMap = ref({});

/* ===== 工具 ===== */
const format3 = v => (typeof v === 'number' ? Number(v).toFixed(3) : v);
function hudAxis(){
  return {
    axisLine:{ lineStyle:{ color:'rgba(120,220,255,0.65)', width:1.2 } },
    axisTick:{ show:false },
    axisLabel:{ color:'#cfeeff', fontSize:FONT_12, fontWeight:600, fontFamily:'Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui' },
    splitLine:{ lineStyle:{ color:'rgba(0,180,255,0.18)', width:1 } }
  };
}
function valueAxisFmt(){ return { ...hudAxis().axisLabel, formatter: v => (typeof v === 'number' ? Number(v).toFixed(3) : v) }; }
function hudTooltip(){
  return {
    trigger:'axis', triggerOn:'mousemove|click',
    backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10,
    textStyle:{ color:'#dff7ff', fontSize:FONT_12, fontWeight:600 },
    axisPointer:{ type:'line', snap:true, lineStyle:{ color:'#00eaff', width:1, type:'dashed' }, z:99 },
    extraCssText:'backdrop-filter: blur(4px);', confine:true
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

/* —— 单维点位系列 —— */
function buildRadarPointSeries(name, values, color){
  const n = values.length; const list = [];
  for(let i=0; i<n; i++){
    const vec = new Array(n).fill(null); vec[i] = values[i];
    list.push({
      name: `${name}-p${i}`,
      type:'radar',
      data:[{ value: vec, name }],
      lineStyle:{ opacity:0 }, areaStyle:{ opacity:0 },
      symbol:'circle', symbolSize:6, itemStyle:{ color }, z:20, silent:false
    });
  }
  return list;
}

/* ===== 动画参数 ===== */
const ENTER_MS = 2400;
const UPDATE_MS = 1200;
const DELAY_STEP = 80;
const delayByIndex = i => i * DELAY_STEP;

/* ===== 时钟 ===== */
const dateTimeFull = ref('');
let clockTimer = null;
function pad(n){ return n<10 ? '0'+n : ''+n; }
function fmt(now){
  const y=now.getFullYear(), m=pad(now.getMonth()+1), d=pad(now.getDate());
  const hh=pad(now.getHours()), mm=pad(now.getMinutes()), ss=pad(now.getSeconds());
  const wk=now.toLocaleDateString('zh-CN',{ weekday:'long' }).replace('周','星期');
  return `${y}-${m}-${d} ${hh}:${mm}:${ss} ${wk}`;
}
function tick(){ dateTimeFull.value = fmt(new Date()); }

/* ===== 路由 ===== */
const router = useRouter();
function goHome(){ router.push('/'); }
function goBack(){ router.back(); }

/* ===== 状态 ===== */
const teacherData = ref(null);

/* ===== 图表实例 ===== */
let radar=null, line=null, emo=null, cog=null, pie=null, gender=null, ro=null;

function disposeAll(){
  const ec = window.echarts;
  if (!ec) return;
  [radar,line,emo,cog,pie,gender].forEach(ins => { if (ins) ec.dispose(ins); });
  radar=line=emo=cog=pie=gender=null;
}
function makeChart(id){
  const ec = window.echarts; if (!ec) return null;
  const el = document.getElementById(id);
  if (!el) return null;
  const old = ec.getInstanceByDom(el); if (old) ec.dispose(old);
  const DPR = Math.min(window.devicePixelRatio || 1, 2.5);
  return ec.init(el, null, { backgroundColor:'transparent', renderer:'canvas', devicePixelRatio:DPR });
}
function initChartsBase(){
  disposeAll();
  radar = makeChart('radar'); line = makeChart('line'); emo = makeChart('emo'); cog = makeChart('cog');
  gender = makeChart('genderPie'); pie = makeChart('gradePie');
  window.addEventListener('resize', resizeAll, { passive:true });
  if (ro) ro.disconnect(); ro = new ResizeObserver(resizeAll);
  const host = document.querySelector('.stage'); if (host) ro.observe(host);
}
function resizeAll(){ [radar,line,emo,cog,pie,gender].forEach(ins => ins && ins.resize()); }

/* ===== 占位 ===== */
function renderPlaceholders(){
  const placeholder = '等待上传数据…';
  [radar,line,emo,cog,gender,pie].forEach(ins => {
    if(!ins) return; ins.clear();
    ins.setOption({ textStyle:{ fontSize: FONT_12 }, graphic:[{ type:'text', left:'center', top:'middle', style:{ text: placeholder, fill:'#a8d9ff', font:`700 ${FONT_12}px Rajdhani, system-ui` } }] });
  });
}

/* ===== 内嵌 SVG：小人符号（返回 image://data-uri） ===== */
function personSymbol(fillColor = '#22c8ff'){
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
      <circle cx="32" cy="12" r="8" fill="${fillColor}"/>
      <rect x="26" y="22" width="12" height="18" rx="6" fill="${fillColor}"/>
      <rect x="20" y="40" width="8" height="18" rx="4" fill="${fillColor}"/>
      <rect x="36" y="40" width="8" height="18" rx="4" fill="${fillColor}"/>
      <rect x="14" y="26" width="12" height="6" rx="3" fill="${fillColor}"/>
      <rect x="38" y="26" width="12" height="6" rx="3" fill="${fillColor}"/>
    </svg>`;
  return 'image://data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}

/* ===== 上传并绘制 ===== */
async function handleFile(e){
  const f = e.target.files && e.target.files[0]; if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  try{
    const res = await axios.post('/api/analyze', fd);
    if (res.data.role !== 'teacher') { alert(res.data.error || '请上传教师数据'); return; }
    teacherData.value = res.data;
    sessionStorage.setItem('teacherData', JSON.stringify(res.data));

    // 构建并保存“全局聊天上下文”（用于连续对话）
    saveGlobalContext(buildTeacherContext(res.data));

    drawAllCharts(); setupAutoScroll();
    await appendAnalysisSummary(); // 分析成功后，逐字输出本地汇总
  }catch(err){
    alert((err && err.response && err.response.data && err.response.data.error) || err.message || '上传失败');
  }
}
async function resetData(){
  sessionStorage.removeItem('teacherData');
  sessionStorage.removeItem('teacherAnalysisSummaryPosted');
  teacherData.value = null;
  await nextTick(); initChartsBase(); renderPlaceholders();
}

/* ===== 年级排序与颜色 ===== */
const GRADE_FIXED_ORDER = ['大一','大二','大三','大四'];
const GRADE_STRONG_BLUE = ['#BFE2FF','#6EC1FF','#1E90FF','#004AAD'];
function sortGrades(names){
  const set = new Set(names);
  const first = GRADE_FIXED_ORDER.filter(n=>set.has(n));
  const rest  = names.filter(n=>!GRADE_FIXED_ORDER.includes(n)).sort();
  return [...first, ...rest];
}
function buildGradeColors(gradeNames){
  const map = {};
  GRADE_FIXED_ORDER.forEach((g,i)=>{ if(gradeNames.includes(g)) map[g] = GRADE_STRONG_BLUE[i]; });
  const alt = ['#F95F62','#FFA600','#7AD66E','#9A5AFF','#23D5D5','#FF7AB6'];
  let idx = 0;
  gradeNames.forEach(n=>{ if(!map[n]){ map[n] = alt[idx % alt.length]; idx++; } });
  return map;
}

/* ===== 绘制班级平均 ===== */
function drawAllCharts(){
  if(!teacherData.value){ renderPlaceholders(); return; }
  initChartsBase();
  const ec = window.echarts; if (!ec) return;
  const feats = teacherData.value.features;
  const avg = cols => cols.map(c => { const arr = feats[c] || []; return arr.length ? arr.reduce((a,b)=>a+b)/arr.length : 0; });
  const af  = avg(behavior_freq_cols);
  const asq = avg(behavior_seq_cols);
  const ae  = avg(emotion_cols);
  const ac  = avg(cognition_cols);

  /* === 雷达：行为频次（中文指标名） === */
  const freqIndicators = behavior_freq_cols.map((c)=>({ name: NAME_MAP[c] || c, max:1 }));
  radar.setOption({
    textStyle:{ fontSize: FONT_12 },
    animation:true, animationDuration:ENTER_MS, animationEasing:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:FONT_12 }, data:['班级平均'] },
    tooltip:{
      trigger:'item', triggerOn:'mousemove|click', confine:true,
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10,
      textStyle:{ color:'#dff7ff', fontSize:FONT_12, fontWeight:600 },
      formatter: p=>{
        const sn = p.seriesName || ''; const k = sn.indexOf('-p');
        if(k === -1){
          return behavior_freq_cols.map((n,i)=>`${NAME_MAP[n]||n}：${format3(af[i])}`).join('<br/>');
        }
        const i = +sn.slice(k+2);
        return `${NAME_MAP[behavior_freq_cols[i]]||behavior_freq_cols[i]}：${format3(af[i])}`;
      }
    },
    radar:{
      indicator: freqIndicators,
      axisName:{ color:'#cfeeff', fontSize: FONT_12, fontFamily:'Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui', fontWeight:700 },
      splitArea:{ show:true, areaStyle:{ color:['rgba(0,180,255,0.05)','rgba(0,180,255,0.02)'] } },
      splitLine:{ lineStyle:{ color:'rgba(0,210,255,0.25)' } },
      axisLine:{ lineStyle:{ color:'rgba(0,210,255,0.25)' } }
    },
    series:[{
      name:'班级平均', type:'radar', data:[{ value: af, name:'班级平均' }],
      lineStyle:{ width:2.6, shadowBlur:14, shadowColor:COLOR_ME_SHADOW, color:COLOR_ME },
      itemStyle:{ color:COLOR_ME }, areaStyle:{ color:COLOR_ME_AREA },
      symbol:'circle', symbolSize:6, emphasis:{ focus:'series' }, silent:false,
      universalTransition:true, animationDelay: delayByIndex
    }].concat(buildRadarPointSeries('班级平均', af, COLOR_ME))
  }, { notMerge:true });

  /* === 折线：行为序列（横轴 1~16；悬停中文序列名） === */
  const xcats = asq.map((_,i)=>i+1);
  line.setOption({
    textStyle:{ fontSize: FONT_12 },
    animation:true, animationDuration:ENTER_MS, animationEasing:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:FONT_12 }, data:['班级平均'] },
    tooltip:{ ...hudTooltip(), triggerOn:'mousemove|click',
      formatter:(ps)=>{ const idx=(ps&&ps[0])?ps[0].dataIndex:0; return `${SEQ_CN[idx]}：${format3(asq[idx])}`; } },
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: xcats, ...hudAxis() },
    yAxis:{ type:'value', axisLabel: valueAxisFmt(), ...hudAxis() },
    series:[{
      name:'班级平均', type:'line', data: asq, smooth:true, showAllSymbol:true,
      symbol:'circle', symbolSize:6, lineStyle:neonLine(ec),
      itemStyle:{ color:'#21ffe3', shadowBlur:10, shadowColor:'rgba(0,255,214,0.8)' },
      areaStyle:{ color:'rgba(0,238,255,0.08)' },
      emphasis:{ focus:'series' }, silent:false,
      universalTransition:true, animationDelay: delayByIndex
    }]
  }, { notMerge:true });

  /* === 柱：情感（中文） === */
  const emoCats = emotion_cols.map(c=>NAME_MAP[c]||c);
  emo.setOption({
    textStyle:{ fontSize: FONT_12 },
    animation:true, animationDuration:ENTER_MS, animationEasing:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:FONT_12 }, data:['班级平均'] },
    tooltip:{
      trigger:'axis', triggerOn:'mousemove|click', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:FONT_12, fontWeight:600 },
      formatter:(ps)=>{ const idx=(ps&&ps[0])?ps[0].dataIndex:0; return `${emoCats[idx]}：${format3(ae[idx])}`; }
    },
    grid:{ left:40, right:20, top:30, bottom:24, containLabel:true },
    xAxis:{ type:'category', data: emoCats, ...hudAxis() },
    yAxis:{ type:'value', axisLabel: valueAxisFmt(), ...hudAxis() },
    series:[{
      name:'班级平均', type:'bar', data: ae,
      itemStyle:neonBar(ec), barWidth:'42%',
      emphasis:{ focus:'series' }, silent:false,
      universalTransition:true, animationDelay: delayByIndex
    }]
  }, { notMerge:true });

  /* === 条：认知（中文） === */
  const cogCats = cognition_cols.map(c=>NAME_MAP[c]||c);
  cog.setOption({
    textStyle:{ fontSize: FONT_12 },
    animation:true, animationDuration:ENTER_MS, animationEasing:'cubicOut',
    legend:{ top:6, right:8, textStyle:{ color:'#cfeeff', fontSize:FONT_12 }, data:['班级平均'] },
    tooltip:{
      trigger:'axis', triggerOn:'mousemove|click', axisPointer:{ type:'shadow' },
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:10, confine:true,
      textStyle:{ color:'#dff7ff', fontSize:FONT_12, fontWeight:600 },
      formatter:(ps)=>{ const idx=(ps&&ps[0])?ps[0].dataIndex:0; return `${cogCats[idx]}：${format3(ac[idx])}`; }
    },
    grid:{ left:60, right:20, top:30, bottom:24, containLabel:true },
    yAxis:{ type:'category', data: cogCats,
      axisLabel: hudAxis().axisLabel, axisLine: hudAxis().axisLine, splitLine:{ show:false } },
    xAxis:{ type:'value', axisLabel: valueAxisFmt(), ...hudAxis() },
    series:[{
      name:'班级平均', type:'bar', data: ac,
      itemStyle:neonBar(ec), barWidth:'42%',
      emphasis:{ focus:'series' }, silent:false,
      universalTransition:true, animationDelay: delayByIndex
    }]
  }, { notMerge:true });

  /* === 迷你：性别分布 === */
  const gs = teacherData.value.gender_stat || {}; const male = gs['男']||0; const female = gs['女']||0;
  const totalG = male + female || 1;
  const malePct = +(male * 100 / totalG).toFixed(1);
  const femalePct = +(female * 100 / totalG).toFixed(1);
  const maleSymbol = personSymbol(genderColorMap['男']);
  const femaleSymbol = personSymbol(genderColorMap['女']);
  const bgSymbol    = personSymbol('rgba(255,255,255,0.12)');

  gender.setOption({
    textStyle:{ fontSize: FONT_12 },
    animation:true, animationDuration:ENTER_MS, animationEasing:'cubicOut',
    title:{ text:'性别分布', left:'center', top:2, textStyle:{ color:'#cfeeff', fontWeight:800, fontSize:FONT_12 } },
    tooltip:{
      trigger:'item',
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:8,
      textStyle:{ color:'#dff7ff', fontSize:FONT_12, fontWeight:700 },
      formatter: p => {
        const name = p.name || '';
        const cnt  = name==='男' ? male : (name==='女' ? female : 0);
        const pct  = name==='男' ? malePct : femalePct;
        return `${name}：${cnt}人（${pct}%）`;
      }
    },
    grid:{ left:12, right:12, top:26, bottom:10, containLabel:true },
    xAxis:{ max:100, splitLine:{show:false}, axisLine:{show:false}, axisTick:{show:false}, axisLabel:{show:false} },
    yAxis:{ type:'category', data:['男','女'], axisLine:{show:false}, axisTick:{show:false},
      axisLabel:{ color:'#cfeeff', fontWeight:800, fontSize: FONT_12 } },
    series:[
      { name:'bg', type:'pictorialBar', symbol: bgSymbol, symbolBoundingData:100, symbolRepeat:true,
        symbolSize:[12,22], symbolMargin:2, data:[100,100], z:1, animation:false },
      { name:'gender', type:'pictorialBar', symbolBoundingData:100, symbolRepeat:true,
        symbolSize:[12,22], symbolMargin:2, symbolClip:true, z:10,
        data:[
          { name:'男', value: malePct, symbol: maleSymbol },
          { name:'女', value: femalePct, symbol: femaleSymbol }
        ]
      }
    ]
  }, { notMerge:true });

  /* === 迷你：年级分布 === */
  const gradeObjRaw = teacherData.value.grade_stat || {};
  const rawNames = Object.keys(gradeObjRaw);
  const gradeNames = sortGrades(rawNames);
  const totalS = gradeNames.reduce((s,k)=>s+(gradeObjRaw[k]||0),0) || 1;
  const gmap = buildGradeColors(gradeNames);
  gradeColorMap.value = gmap;
  const pdata = gradeNames.map(n => ({ name:n, value: gradeObjRaw[n]||0 }));

  pie.setOption({
    textStyle:{ fontSize: FONT_12 },
    animation:true, animationDuration:ENTER_MS, animationEasing:'cubicOut',
    title:{ text:'年级分布', left:'center', top:2, textStyle:{ color:'#cfeeff', fontWeight:800, fontSize:FONT_12 } },
    tooltip:{
      trigger:'item',
      backgroundColor:'rgba(10,18,36,0.92)', borderColor:'#00eaff', borderWidth:1, padding:8,
      textStyle:{ color:'#dff7ff', fontSize:FONT_12, fontWeight:700 },
      formatter: p => {
        const cnt = p && p.value ? p.value : 0;
        const pct = p && typeof p.percent === 'number' ? p.percent.toFixed(1) : ((cnt*100/totalS).toFixed(1));
        return `${p.name}：${cnt}人（${pct}%）`;
      }
    },
    color: gradeNames.map(n => gmap[n]),
    series:[{
      type:'pie',
      radius:['46%','72%'], center:['50%','56%'],
      label:{ show:false }, labelLine:{ show:false },
      itemStyle:{
        borderWidth:1.2, borderColor:'rgba(0,234,255,.28)',
        shadowBlur:18, shadowColor:'rgba(0,238,255,.28)'
      },
      data: pdata
    }]
  }, { notMerge:true });
}

/* ===== 表格配色 ===== */
function styleIndex(){ return { color: '#2affd5' }; }
function styleGender(g){ return { color: genderColorMap[g] || '#cfeeff' }; }
function styleGrade(gr){ return { color: gradeColorMap.value[gr] || '#cfeeff' }; }
function styleLevel(lev){ const c = LEVEL_COLOR[Number(lev)] || '#cfeeff'; return { color: c, fontWeight: 800 }; }

/* ===== 自动滚动表格 ===== */
const tableContainer = ref(null); const hovering = ref(false); let scrollInt = null;
function setupAutoScroll(){ clearInterval(scrollInt); scrollInt = setInterval(()=>{ if (!hovering.value && tableContainer.value) tableContainer.value.scrollTop += 1; }, 200); }
function onWheel(e){ if(tableContainer.value) tableContainer.value.scrollTop += e.deltaY; }
onBeforeUnmount(()=>clearInterval(scrollInt));

/* ===== 学生行点击 ===== */
function goStudent(idx){
  if (!teacherData.value) return;
  const stu = teacherData.value.students[idx];
  const feats = teacherData.value.features;

  const name = (stu && (stu.姓名 || stu.name || stu.studentName)) || `学生${idx + 1}`;
  const id   = (stu && (stu.学号 || stu.studentId || stu.id)) || String(idx + 1);
  sessionStorage.setItem('selectedStudentName', name);
  sessionStorage.setItem('selectedStudentRow', JSON.stringify(stu || {}));
  sessionStorage.setItem('selectedStudentId', id);

  const data = {
    ability: stu.预测元认知能力,
    behavior_freq: behavior_freq_cols.map(c=>[NAME_MAP[c]||c, feats[c]?.[idx]||0]),  // 存中文名
    behavior_seq: behavior_seq_cols.map((c,i)=>[SEQ_CN[i], feats[c]?.[idx]||0]),    // 存中文序列
    emotion:       emotion_cols.map(c=>[NAME_MAP[c]||c, feats[c]?.[idx]||0]),
    cognition:     cognition_cols.map(c=>[NAME_MAP[c]||c, feats[c]?.[idx]||0])
  };
  sessionStorage.setItem('studentData', JSON.stringify(data));

  // 将“当前所选学生”加入全局上下文，便于后续连续对话
  mergeGlobalContext({ current_student: { id, name, ability: data.ability, features: data } });

  router.push({ path: `/teacher/student/${idx}`, query: { name, id } });
}

/* ===== 对话：全局共享（与学生详情页共用同一会话） ===== */
const CHAT_KEY = 'globalChatMessages';
const WELCOME_KEY = 'teacherChatWelcomed';
const CTX_KEY = 'globalChatContext';

const messages = ref([]);
const userInput = ref('');
const isChatLoading = ref(false);
const chatWindow = ref(null);
const typingTimers = [];

function scrollChatBottom(){
  nextTick(() => {
    const el = chatWindow.value;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  });
}
function pickSpeed(len){
  if (len > 500) return 6;
  if (len > 200) return 10;
  return 18;
}
function saveChat(){
  const plain = messages.value.map(m => ({ sender: m.sender, text: m.text }));
  sessionStorage.setItem(CHAT_KEY, JSON.stringify(plain));
}
function loadChat(){
  const raw = sessionStorage.getItem(CHAT_KEY);
  try{ return raw ? JSON.parse(raw) : []; }catch{ return []; }
}
function typeBot(text, speed){
  return new Promise(resolve => {
    const chars = Array.from(text);
    const msg = { sender:'bot', text:'', typing:true };
    messages.value.push(msg); saveChat(); scrollChatBottom();

    let i = 0; const base = typeof speed === 'number' ? speed : pickSpeed(chars.length);
    const step = () => {
      if (i < chars.length) {
        const chunk = (chars.length > 400) ? 2 : 1;
        msg.text += chars.slice(i, i + chunk).join('');
        i += chunk;
        saveChat(); scrollChatBottom();
        const jitter = Math.floor(Math.random() * 7);
        const id = setTimeout(step, base + jitter);
        typingTimers.push(id);
      } else {
        msg.typing = false;
        saveChat(); scrollChatBottom();
        resolve();
      }
    };
    step();
  });
}
async function sendMessage(){
  const txt = (userInput.value || '').trim(); if (!txt || isChatLoading.value) return;
  messages.value.push({ sender:'user', text: txt }); saveChat(); userInput.value = '';
  try{
    isChatLoading.value = true;
    const ctx = loadGlobalContext();
    const res = await axios.post('/api/chat', { message: txt, scene:'teacher', context: ctx });
    const answer = (res.data && res.data.reply) ? res.data.reply : '未收到回复';
    await typeBot(answer + ' 🤖');
  }catch{
    await typeBot('对话出错：无法连接到智能体服务，请检查后端 /api/chat。');
  }finally{
    isChatLoading.value = false;
  }
}

/* ===== 分析完成总结（逐字打字；仅首次贴一次） ===== */
async function appendAnalysisSummary(){
  if (!teacherData.value) return;
  const postedKey = 'teacherAnalysisSummaryPosted';
  if (sessionStorage.getItem(postedKey) === '1') return;

  const td = teacherData.value;
  const students = td.students || [];
  const total = students.length || 0;

  const gs = td.gender_stat || {};
  const male = gs['男'] || 0, female = gs['女'] || 0;
  const malePct = total ? (male*100/total).toFixed(1) : '0.0';
  const femalePct = total ? (female*100/total).toFixed(1) : '0.0';

  const gr = td.grade_stat || {};
  const gradeNames = sortGrades(Object.keys(gr));
  const gradeStr = gradeNames.map(n=>{
    const c = gr[n] || 0;
    const p = total ? (c*100/total).toFixed(1) : '0.0';
    return `${n}${c ? ` ${c}人（${p}%）` : ' 0人（0.0%）'}`;
  }).join('、');

  const levelCnt = {0:0,1:0,2:0};
  students.forEach(s=>{
    const k = Number(s.预测元认知能力);
    if (k===0 || k===1 || k===2) levelCnt[k] += 1;
  });
  const lowP  = total ? (levelCnt[0]*100/total).toFixed(1) : '0.0';
  const midP  = total ? (levelCnt[1]*100/total).toFixed(1) : '0.0';
  const highP = total ? (levelCnt[2]*100/total).toFixed(1) : '0.0';

  const summary =
    `分析完成 ✅ 共 ${total} 名学生。`+
    `性别：男 ${male}（${malePct}%）、女 ${female}（${femalePct}%）。`+
    `年级：${gradeStr || '无' }。`+
    `元认知能力：高 ${levelCnt[2]}（${highP}%）、中 ${levelCnt[1]}（${midP}%）、低 ${levelCnt[0]}（${lowP}%）。`+
    ` 提示：点击表格行查看单个学生。`;

  await typeBot(summary);
  sessionStorage.setItem(postedKey, '1');
}

/* ===== 构建/保存 全局聊天上下文（支持连续对话） ===== */
function buildTeacherContext(td){
  const feats = td.features || {};
  const avg = cols => cols.map(c => {
    const arr = feats[c] || []; return arr.length ? arr.reduce((a,b)=>a+b)/arr.length : 0;
  });
  const ctx = {
    role: 'teacher',
    n_students: (td.students || []).length || 0,
    gender_stat: td.gender_stat || {},
    grade_stat: td.grade_stat || {},
    features_avg: {
      行为频次: Object.fromEntries(behavior_freq_cols.map((k,i)=>[NAME_MAP[k]||k, format3(avg(behavior_freq_cols)[i])])),
      行为序列: Object.fromEntries(behavior_seq_cols.map((k,i)=>[SEQ_CN[i], format3(avg(behavior_seq_cols)[i])])),
      情感:       Object.fromEntries(emotion_cols.map((k,i)=>[NAME_MAP[k]||k, format3(avg(emotion_cols)[i])])),
      认知:       Object.fromEntries(cognition_cols.map((k,i)=>[NAME_MAP[k]||k, format3(avg(cognition_cols)[i])]))
    }
  };
  return ctx;
}
function saveGlobalContext(obj){
  sessionStorage.setItem(CTX_KEY, JSON.stringify(obj || {}));
}
function mergeGlobalContext(obj){
  const now = loadGlobalContext();
  saveGlobalContext({ ...(now||{}), ...(obj||{}) });
}
function loadGlobalContext(){
  const raw = sessionStorage.getItem(CTX_KEY);
  try{ return raw ? JSON.parse(raw) : {}; }catch{ return {}; }
}

/* ===== 生命周期 ===== */
onMounted(async ()=>{
  // 时钟
  tick(); clockTimer = setInterval(tick, 1000);

  // 图表
  initChartsBase();
  const saved = sessionStorage.getItem('teacherData');
  if (saved) {
    try{
      teacherData.value = JSON.parse(saved);
      drawAllCharts(); setupAutoScroll();
      await appendAnalysisSummary();
      // 确保有上下文
      if (!sessionStorage.getItem(CTX_KEY)) saveGlobalContext(buildTeacherContext(teacherData.value));
    } catch {
      teacherData.value = null; renderPlaceholders();
    }
  } else {
    renderPlaceholders();
  }

  // 聊天：全局共享，仅教师页首次欢迎
  messages.value = loadChat();
  if (!messages.value.length && sessionStorage.getItem(WELCOME_KEY) !== '1') {
    await typeBot('你好，我是智能分析助手 🤖✨  已就绪，问我任何问题都可以～');
    sessionStorage.setItem(WELCOME_KEY, '1');
  }
});
onBeforeUnmount(()=>{
  clearInterval(clockTimer);
  disposeAll();
  if (ro) ro.disconnect();
  typingTimers.forEach(id => clearTimeout(id));
});
</script>

<style scoped>
/* ====== 全局参数（不改你的布局） ====== */
.stage{
  --hud-top: 1.0%;
  --box-left: 37%; --box-top: 9%; --box-width: 26%; --box-height: 57%;
  --center-left: 50%;
  --center-top: 9%;
  --center-width: var(--box-width);
  --center-height: 55%;
  --center-translate-x: -50%;
  --mini-h: 110px;
  --mini-gap: 8px;
  --gender-w: 48%;
  --grade-w: 52%;
  --chat-left: 50%;
  --chat-top: 70%;
  --chat-w: 25%;
  --chat-h: 25%;
  --chat-translate-x: -50%;

  position:relative; width:100vw; margin:0 auto; aspect-ratio:16/9; overflow:hidden;
  color:#eaf8ff; background:#000;
  font-family: Rajdhani, Orbitron, DIN Alternate, Segoe UI, system-ui, -apple-system, "PingFang SC", "Microsoft YaHei";
}

/* 背景 */
.bg{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; object-position:center; z-index:0; pointer-events:none; }

/* 顶部 HUD */
.topbar{ position:absolute; top:var(--hud-top); left:2%; right:2%; z-index:100; display:flex; justify-content:space-between; align-items:center; font-size:14px; pointer-events:none; }
.topbar .hud-btn, .topbar .file-btn, .topbar input, .topbar label, .topbar .left-controls > *, .topbar .right-controls > *{ pointer-events:auto; }
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

/* 四角图表 */
.chart{ position:absolute; z-index:120; background:transparent!important; border-radius:14px; isolation:isolate; pointer-events:auto; }
.box-left-top{     left:3.5%;  top:14%;   width:30%; height:37%; }
.box-left-bottom{  left:3.5%;  top:58.5%; width:30%; height:37%; }
.box-right-top{    left:66.6%; top:14%;   width:30%; height:37%; }
.box-right-bottom{ left:66.6%; top:58.5%; width:30%; height:37%; }

/* 中心列 */
.center-content{
  position:absolute;
  top: var(--center-top);
  left: var(--center-left);
  transform: translateX(var(--center-translate-x));
  width: var(--center-width);
  height: var(--center-height);
  display:flex; flex-direction:column; gap:10px;
  z-index:90; pointer-events:auto;
}
.mini-row{
  display:grid;
  grid-template-columns: var(--gender-w) var(--grade-w);
  grid-auto-rows: var(--mini-h);
  gap: var(--mini-gap);
  align-items:stretch;
}
.mini-chart{
  position:relative; height:100%;
  border:1px solid rgba(0,234,255,.22); border-radius:12px;
  backdrop-filter: blur(2px);
  box-shadow: 0 0 14px rgba(0,238,255,.12) inset;
}

/* 表格 */
.table-container{
  flex:1; overflow-y:auto;
  border:1px solid rgba(0,234,255,.2);
  background:rgba(10,18,36,.20);
  border-radius:12px; backdrop-filter: blur(2px);
  pointer-events:auto; z-index:90; position:relative;
  -webkit-overflow-scrolling: touch;
}
table{ width:100%; border-collapse:separate; border-spacing:0; }
th,td{ padding:8px 8px; border-bottom:1px solid rgba(0,234,255,.12); text-align:center; font-weight:700; color:#eaf8ff; }
thead th{
  position:sticky; top:0; z-index:3;
  background: linear-gradient(180deg, #0C2F4F 0%, #113B64 100%);
  border-bottom: 1px solid rgba(0,234,255,.35);
  color:#DDF4FF;
  text-shadow: 0 0 8px rgba(0,190,255,.25);
}
tr{ cursor:pointer; }
tr:hover{ background:rgba(25,228,255,0.08); }
.empty{ color:#88c8ff; text-align:center; cursor:default; }

/* 对话模块（统一 12px） */
.chat-module{
  position:absolute;
  left: var(--chat-left);
  top: var(--chat-top);
  transform: translateX(var(--chat-translate-x));
  width: var(--chat-w);
  height: var(--chat-h);
  display:flex; flex-direction:column;
  z-index:200;
}
.chat-module.bare{ background:transparent; border:none; box-shadow:none; backdrop-filter:none; }
.chat-window{
  flex:1; overflow-y:auto; padding:10px; scrollbar-width:thin;
  font-size: 12px; line-height: 1.6;
}
.chat-window.bare{ background:transparent; }
.chat-msg{ margin-bottom:8px; }
.chat-msg.user{ text-align:right; color:#a7f0ff; text-shadow:0 0 10px rgba(20,220,255,.25); }
.chat-msg.bot{  text-align:left;  color:#eaf8ff; text-shadow:0 0 10px rgba(255,255,255,.15); }
.chat-input{ display:flex; }
.chat-input.bare{ border:none; background:transparent; }
.chat-input input{
  flex:1; padding:8px; background:rgba(8,14,28,.35); color:#eaf8ff;
  border:1px solid rgba(0,234,255,.25); border-radius:10px 0 0 10px; outline:none;
  font-size: 12px;
}
.chat-input button{
  padding:8px 12px; color:#001a22; background:linear-gradient(90deg,#35f5ff,#22c8ff);
  border:none; border-left:1px solid rgba(0,234,255,.35); border-radius:0 10px 10px 0;
  cursor:pointer; font-weight:800; letter-spacing:.3px;
  font-size: 12px;
}
.chat-input button:disabled{ opacity:.6; cursor:not-allowed; }

/* 打字光标 */
.chat-caret{
  display:inline-block;
  width:10px;
  border-left:2px solid rgba(255,255,255,.9);
  margin-left:2px;
  animation: caretBlink 1s steps(1) infinite;
  vertical-align: baseline;
}
@keyframes caretBlink { 50% { opacity: 0; } }

/* 导航条 */
.nav{ position:absolute; right:8px; bottom:8px; z-index:40; pointer-events:auto; }

/* 兜底：确保 ECharts 画布能收到事件 */
:deep(#radar), :deep(#line), :deep(#emo), :deep(#cog), :deep(#genderPie), :deep(#gradePie){ pointer-events:auto; }
:deep(#radar canvas), :deep(#line canvas), :deep(#emo canvas), :deep(#cog canvas), :deep(#genderPie canvas), :deep(#gradePie canvas){ pointer-events:auto !important; }

/* ===== 霓虹滚动条（仅 .stage 作用域内） ===== */
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
