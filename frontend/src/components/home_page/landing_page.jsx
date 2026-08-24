import { useEffect, useRef, useState } from "react";

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

  .twn{
    --bg: #FFFFFF;
    --bg-alt: #F7F9FC;
    --ink: #1B2233;
    --ink-soft: #4B5565;
    --ink-faint: #8891A3;
    --line: #E4E8F1;
    --indigo-1: #4F46E5;
    --indigo-2: #6366F1;
    --indigo-soft: #EEF0FE;
    --signal: #22D3EE;
    --radius: 14px;
    --wrap: 1180px;
    font-family: 'Inter', sans-serif;
    color: var(--ink);
    background: var(--bg);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }

  @media (prefers-reduced-motion: reduce){
    .twn *{ animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; }
  }

  .twn *{ box-sizing: border-box; }
  .twn h1, .twn h2, .twn h3{ font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.01em; margin: 0; }
  .twn p{ margin: 0; }
  .twn ul{ margin:0; }
  .twn a{ color: inherit; text-decoration: none; }
  .twn section{ position: relative; }
  .twn .wrap{ max-width: var(--wrap); margin: 0 auto; padding: 0 28px; }

  .twn .eyebrow{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12.5px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--indigo-1);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-weight: 500;
    margin-bottom: 14px;
  }
  .twn .eyebrow::before{
    content:"";
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--indigo-1);
    box-shadow: 0 0 0 3px var(--indigo-soft);
  }

  .twn .btn{
    display: inline-flex; align-items: center; gap: 10px;
    padding: 13px 26px;
    border-radius: 999px;
    font-weight: 600;
    font-size: 15px;
    cursor: pointer;
    border: 1px solid transparent;
    transition: transform .18s ease, box-shadow .18s ease, background .18s ease;
  }
  .twn .btn-primary{
    background: linear-gradient(135deg, var(--indigo-1), var(--indigo-2));
    color: #fff;
    box-shadow: 0 8px 20px -8px rgba(79,70,229,0.55);
  }
  .twn .btn-primary:hover{ transform: translateY(-2px); box-shadow: 0 12px 26px -8px rgba(79,70,229,0.65); }
  .twn .btn-ghost{ background: transparent; color: var(--ink); border-color: var(--line); }
  .twn .btn-ghost:hover{ border-color: var(--indigo-2); color: var(--indigo-1); }

  /* ---------- NAV ---------- */
  .twn header{
    position: fixed; top:0; left:0; right:0; z-index: 100;
    padding: 18px 0;
    transition: background .25s ease, box-shadow .25s ease, padding .25s ease, backdrop-filter .25s ease;
  }
  .twn header.scrolled{
    background: rgba(255,255,255,0.82);
    backdrop-filter: blur(14px);
    box-shadow: 0 1px 0 var(--line);
    padding: 12px 0;
  }
  .twn nav{ display:flex; align-items:center; justify-content: space-between; }
  .twn .brand{ display:flex; align-items:center; gap: 11px; }
  .twn .brand-mark{
    width: 34px; height: 34px; border-radius: 9px;
    background: linear-gradient(135deg, var(--indigo-1), var(--signal));
    position: relative; flex-shrink:0;
  }
  .twn .brand-mark::before, .twn .brand-mark::after{
    content:""; position:absolute; background:#fff; border-radius:2px;
  }
  .twn .brand-mark::before{ width: 14px; height: 2px; top: 12px; left: 10px; transform: rotate(20deg); }
  .twn .brand-mark::after{ width: 2px; height: 14px; top: 10px; left: 16px; transform: rotate(20deg); }
  .twn .brand-text{ display:flex; flex-direction:column; line-height:1.15; }
  .twn .brand-text .name{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size: 16.5px; }
  .twn .brand-text .tag{ font-family:'IBM Plex Mono',monospace; font-size: 10.5px; color: var(--ink-faint); letter-spacing:0.04em; }
  .twn .nav-links{ display:flex; gap: 30px; }
  .twn .nav-links a{ font-size: 14.5px; font-weight: 500; color: var(--ink-soft); transition: color .15s; }
  .twn .nav-links a:hover{ color: var(--indigo-1); }
  .twn .nav-right{ display:flex; align-items:center; gap: 22px; }
  .twn .nav-cta{ padding: 10px 20px; font-size: 14px; }

  @media (max-width: 940px){ .twn .nav-links{ display:none; } }

  /* ---------- HERO ---------- */
  .twn .hero{
    padding: 168px 0 100px;
    background:
      radial-gradient(1100px 480px at 82% -10%, #EEF0FE 0%, rgba(238,240,254,0) 60%),
      var(--bg);
    overflow: hidden;
  }
  .twn .hero-grid{ display:grid; grid-template-columns: 1.05fr 0.95fr; gap: 56px; align-items:center; }
  .twn .hero h1{ font-size: clamp(34px, 4.6vw, 58px); font-weight: 700; line-height: 1.08; color: var(--ink); }
  .twn .hero h1 .grad{
    background: linear-gradient(100deg, var(--indigo-1), #7C6BFB 55%, var(--signal));
    -webkit-background-clip: text; background-clip:text; color: transparent;
  }
  .twn .hero p.lead{ margin-top: 22px; font-size: 17.5px; color: var(--ink-soft); max-width: 520px; }
  .twn .hero-actions{ display:flex; gap: 14px; margin-top: 34px; flex-wrap: wrap; }
  .twn .trust-line{ display:flex; gap: 26px; margin-top: 30px; flex-wrap: wrap; }
  .twn .trust-line span{ display:flex; align-items:center; gap: 8px; font-size: 13.5px; color: var(--ink-faint); font-weight: 500; }
  .twn .trust-line svg{ flex-shrink:0; }

  .twn .hero-graphic{
    position: relative; height: 460px;
    border-radius: 20px;
    background: linear-gradient(160deg, #10132A 0%, #1C2142 55%, #262B52 100%);
    overflow: hidden;
    box-shadow: 0 30px 60px -25px rgba(30,27,75,0.45);
  }

  /* ---------- HERO GRAPHIC v2: doc-in, cited-answer-out ---------- */
  .twn .hg-stage{ position:absolute; inset:0; padding: 34px; }
  .twn .hg-doc{
    position:absolute;
    width: 132px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 10px;
    padding: 10px 12px;
    color: #C9CCF0;
  }
  .twn .hg-doc .fname{
    font-family:'IBM Plex Mono',monospace; font-size: 10.5px; color:#fff; font-weight:600;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
  }
  .twn .hg-doc .bars{ margin-top:8px; display:flex; flex-direction:column; gap:5px; }
  .twn .hg-doc .bars span{ display:block; height:4px; border-radius:2px; background: rgba(255,255,255,0.16); }
  .twn .hg-doc.d1{ top: 46px; left: 34px; transform: rotate(-4deg); z-index:2; }
  .twn .hg-doc.d2{ top: 92px; left: 58px; transform: rotate(3deg); z-index:1; opacity:0.7; }

  .twn .hg-answer{
    position:absolute; right: 30px; bottom: 40px;
    width: 260px;
    background: #fff;
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 20px 40px -16px rgba(0,0,0,0.5);
  }
  .twn .hg-answer .q{ font-size: 11.5px; color: var(--indigo-1); font-weight:700; font-family:'IBM Plex Mono',monospace; }
  .twn .hg-answer .qtext{ font-size: 13px; color: var(--ink); font-weight:600; margin-top:4px; line-height:1.35; }
  .twn .hg-answer .atext{ font-size: 12.3px; color: var(--ink-soft); margin-top:8px; line-height:1.45; }
  .twn .hg-answer .cites{ display:flex; gap:6px; margin-top:11px; flex-wrap:wrap; }
  .twn .hg-answer .cite{
    font-family:'IBM Plex Mono',monospace; font-size: 9.5px; font-weight:600;
    background: var(--indigo-soft); color: var(--indigo-1);
    padding: 3px 8px; border-radius: 999px;
  }

  .twn .hg-path{ position:absolute; inset:0; width:100%; height:100%; }
  .twn .hg-badge{
    position:absolute; top: 26px; right: 30px;
    background: rgba(34,211,238,0.14); border: 1px solid rgba(34,211,238,0.35);
    color: #B6F3FF; font-family:'IBM Plex Mono',monospace; font-size: 10.5px; font-weight:600;
    padding: 6px 11px; border-radius: 999px;
  }

  @media (max-width: 560px){
    .twn .hg-answer{ width: 210px; right: 16px; }
    .twn .hg-doc.d1{ left: 16px; }
    .twn .hg-doc.d2{ left: 34px; }
  }

  /* ---------- SECTION HEAD ---------- */
  .twn .section-head{ max-width: 640px; }
  .twn .section-head h2{ font-size: clamp(28px,3.4vw,40px); font-weight:700; margin-top: 2px; }
  .twn .section-head p{ margin-top: 16px; color: var(--ink-soft); font-size: 16.5px; }
  .twn .section-head.center{ max-width: 680px; margin: 0 auto; text-align:center; }
  .twn .section-head.center .eyebrow{ justify-content:center; }

  /* ---------- OVERVIEW ---------- */
  .twn .overview{ padding: 120px 0; }
  .twn .overview-grid{ display:grid; grid-template-columns: 1fr 0.85fr; gap: 60px; align-items:center; }

  /* ---------- OVERVIEW DIAGRAM v2: unstructured -> engine -> grounded ---------- */
  .twn .flow{
    display:flex; flex-direction:column; align-items:center; gap: 6px;
    max-width: 340px; margin: 0 auto;
  }
  .twn .flow-panel{
    width: 100%; display:flex; align-items:center; gap: 14px;
    background:#fff; border: 1px solid var(--line); border-radius: 14px;
    padding: 16px 18px; box-shadow: 0 10px 26px -18px rgba(20,20,40,0.25);
  }
  .twn .flow-panel .ic{
    width: 42px; height:42px; border-radius: 10px; flex-shrink:0;
    display:flex; align-items:center; justify-content:center;
    background: var(--indigo-soft);
  }
  .twn .flow-panel .tt{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size: 14.5px; }
  .twn .flow-panel .ds{ font-size: 12px; color: var(--ink-soft); margin-top: 2px; }
  .twn .flow-panel.core{
    background: linear-gradient(135deg, var(--indigo-1), var(--indigo-2));
    color:#fff; box-shadow: 0 16px 30px -14px rgba(79,70,229,0.55);
  }
  .twn .flow-panel.core .ic{ background: rgba(255,255,255,0.16); }
  .twn .flow-panel.core .tt{ color:#fff; }
  .twn .flow-panel.core .ds{ color: rgba(255,255,255,0.8); }
  .twn .flow-arrow{ color: var(--ink-faint); }

  @media (max-width: 880px){ .twn .overview-grid{ grid-template-columns:1fr; } }

  /* ---------- RAG ARCHITECTURE (pipeline) ---------- */
  .twn .pipeline{ padding: 130px 0 100px; background: var(--bg-alt); }
  .twn .pipe-chain{ margin-top: 60px; display:flex; align-items:flex-start; gap: 0; overflow-x: auto; padding-bottom: 20px; }
  .twn .pipe-node{ flex: 1 1 0; min-width: 118px; text-align:center; position:relative; padding: 0 6px; }
  .twn .pipe-node .dot{
    width: 52px; height: 52px; border-radius: 50%; margin: 0 auto 14px;
    background: #fff; border: 2px solid var(--indigo-2);
    display:flex; align-items:center; justify-content:center;
    font-family:'Space Grotesk',sans-serif; font-weight:700; color: var(--indigo-1); font-size: 17px;
    position: relative; z-index:2;
    transition: transform .3s ease, background .3s ease, color .3s ease;
  }
  .twn .pipe-node.active .dot{
    background: linear-gradient(135deg, var(--indigo-1), var(--indigo-2));
    color:#fff; transform: scale(1.08);
    box-shadow: 0 10px 22px -10px rgba(79,70,229,0.6);
  }
  .twn .pipe-node .label{ font-size: 12.8px; font-weight:600; color: var(--ink); line-height:1.25; }
  .twn .pipe-line{ position:absolute; top: 26px; left: -50%; width: 100%; height: 2px; background: var(--line); z-index:1; }
  .twn .pipe-line .pulse{
    position:absolute; top:-3px; width: 8px; height:8px; border-radius:50%;
    background: var(--signal); box-shadow: 0 0 10px 2px rgba(34,211,238,0.6);
    animation: twn-travel 3.2s linear infinite;
  }
  @keyframes twn-travel{ from{ left: 0%; } to{ left: 100%; } }
  .twn .pipe-node:first-child .pipe-line{ display:none; }

  .twn .pipeline-note{
    margin-top: 44px; max-width: 780px; color: var(--ink-soft); font-size: 15.5px;
    padding: 22px 24px; background: #fff; border-left: 3px solid var(--indigo-2); border-radius: 8px;
  }

  @media (max-width: 880px){
    .twn .pipe-chain{ flex-direction:column; align-items:stretch; gap: 26px; overflow: visible; }
    .twn .pipe-node{ display:flex; align-items:center; gap: 16px; text-align:left; padding:0; }
    .twn .pipe-node .dot{ margin:0; flex-shrink:0; }
    .twn .pipe-line{ display:none !important; }
  }

  /* ---------- KEY FEATURES ---------- */
  .twn .features{ padding: 120px 0; }
  .twn .feature-grid{ display:grid; grid-template-columns: repeat(3,1fr); gap: 18px; margin-top: 48px; }
  .twn .feature-card{
    background:#fff; border:1px solid var(--line); border-radius: var(--radius);
    padding: 26px 24px; transition: border-color .2s, transform .2s;
  }
  .twn .feature-card:hover{ border-color: var(--indigo-2); transform: translateY(-3px); }
  .twn .feature-card .icon{
    width: 38px; height: 38px; border-radius: 10px;
    background: var(--indigo-soft); display:flex; align-items:center; justify-content:center;
    margin-bottom: 16px;
  }
  .twn .feature-card h3{ font-size: 16px; font-weight:700; }
  .twn .feature-card p{ margin-top: 8px; font-size: 13.8px; color: var(--ink-soft); }

  @media (max-width: 980px){ .twn .feature-grid{ grid-template-columns: 1fr 1fr; } }
  @media (max-width: 600px){ .twn .feature-grid{ grid-template-columns: 1fr; } }

  /* ---------- TECH STACK ---------- */
  .twn .stack{ padding: 100px 0; background: var(--bg-alt); }
  .twn .stack-grid{ display:grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-top: 46px; }
  .twn .stack-card{
    background:#fff; border:1px solid var(--line); border-radius: 12px;
    padding: 22px; transition: border-color .2s, transform .2s;
  }
  .twn .stack-card:hover{ border-color: var(--indigo-2); transform: translateY(-3px); }
  .twn .stack-card .name{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size: 16px; }
  .twn .stack-card .role{ font-family:'IBM Plex Mono',monospace; font-size: 11.5px; color: var(--indigo-1); margin-top: 6px; letter-spacing:0.04em; text-transform:uppercase; }

  @media (max-width: 880px){ .twn .stack-grid{ grid-template-columns: 1fr 1fr; } }

  /* ---------- BUSINESS IMPACT (timeline) ---------- */
  .twn .impact{ padding: 130px 0; }
  .twn .timeline-track{ position:relative; margin-top: 60px; }
  .twn .timeline-track::before{
    content:""; position:absolute; left:50%; top:0; bottom:0; width:2px;
    background: var(--line); transform: translateX(-50%);
  }
  .twn .t-item{ display:grid; grid-template-columns: 1fr 40px 1fr; align-items:center; margin-bottom: 46px; }
  .twn .t-item .spot{
    width: 16px; height:16px; border-radius:50%; background:#fff; border: 3px solid var(--indigo-2);
    margin: 0 auto; position:relative; z-index:2;
  }
  .twn .t-card{ background:#fff; border:1px solid var(--line); border-radius: 14px; padding: 22px 24px; max-width: 420px; }
  .twn .t-card h3{ font-size: 16.5px; font-weight:700; margin-bottom: 8px; }
  .twn .t-card p{ font-size: 14px; color: var(--ink-soft); }
  .twn .t-item.odd .t-card{ margin-left: auto; text-align:right; }
  .twn .t-item.even .t-card{ grid-column: 3; }

  @media (max-width: 780px){
    .twn .timeline-track::before{ left: 18px; }
    .twn .t-item{ grid-template-columns: 40px 1fr; }
    .twn .t-item .spot{ margin: 0; }
    .twn .t-item.odd .t-card, .twn .t-item.even .t-card{ grid-column: 2; margin-left:0; text-align:left; max-width:none; }
    .twn .t-item .t-hide{ display:none; }
  }

  /* ---------- FINAL CTA ---------- */
  .twn .final-cta{
    margin: 0 28px 90px; border-radius: 26px;
    background: linear-gradient(135deg, #201C4D, var(--indigo-1) 55%, var(--indigo-2));
    padding: 90px 40px; text-align:center; color:#fff; position:relative; overflow:hidden;
  }
  .twn .final-cta::after{
    content:""; position:absolute; inset:0;
    background: radial-gradient(500px 260px at 80% 0%, rgba(34,211,238,0.25), transparent 60%);
  }
  .twn .final-cta > *{ position:relative; z-index:1; }
  .twn .final-cta .eyebrow{ justify-content:center; color: var(--signal); }
  .twn .final-cta .eyebrow::before{ background: var(--signal); box-shadow: 0 0 0 3px rgba(34,211,238,0.2); }
  .twn .final-cta h2{ font-size: clamp(28px,4vw,42px); font-weight:700; max-width: 640px; margin: 0 auto; }
  .twn .final-cta p{ margin-top: 16px; color: #D7D9F5; font-size: 16.5px; }
  .twn .final-cta .btn{ margin-top: 32px; }
  .twn .final-cta .btn-primary{ background:#fff; color: var(--indigo-1); box-shadow: 0 12px 26px -10px rgba(0,0,0,0.35); }
  .twn .final-cta .btn-primary:hover{ transform: translateY(-2px); }

  /* reveal-on-scroll */
  .twn .reveal{ opacity:0; transform: translateY(18px); transition: opacity .7s ease, transform .7s ease; }
  .twn .reveal.in{ opacity:1; transform:none; }
`;

const PIPELINE_STAGES = [
  "Workflow Documents",
  "Markdown Processing",
  "Chunking",
  "Embeddings",
  "FAISS Vector DB",
  "Semantic Retrieval",
  "Cross Encoder Re-rank",
  "LLM",
  "Accurate Response",
];

const FEATURES = [
  { title: "Workflow Exploration", copy: "Browse and query every indexed telecom process in plain language." },
  { title: "Approval Chains", copy: "Trace who approves what, and in which order, for any given step." },
  { title: "Step-by-Step Guidance", copy: "Get the exact sequence of actions for a procedure, on demand." },
  { title: "Business Rules", copy: "Surface the conditions and policies that govern a workflow." },
  { title: "Exception Handling", copy: "Understand what to do when a process deviates from the norm." },
  { title: "Cross-Workflow Understanding", copy: "Connect related steps and dependencies across documents." },
];

const STACK_ITEMS = [
  { name: "FastAPI", role: "Backend" },
  { name: "React", role: "Frontend" },
  { name: "Sentence Transformers", role: "Embeddings" },
  { name: "FAISS", role: "Vector DB" },
  { name: "Cross Encoder", role: "Re-ranking" },
  { name: "RAG", role: "Architecture" },
  { name: "SQLite", role: "Storage" },
  { name: "Langfuse", role: "Observability" },
];

const IMPACT_ITEMS = [
  { title: "Business Impact", copy: "Turns tribal documentation into a measurable operational asset." },
  { title: "Knowledge Digitization", copy: "Every workflow indexed, versioned, and searchable in one place." },
  { title: "Reduced Search Time", copy: "Answers in seconds instead of minutes of manual document scanning." },
  { title: "Faster Training", copy: "New joiners ramp up with a conversational domain expert on-call." },
  { title: "Operational Consistency", copy: "Everyone gets the same grounded, source-backed answer." },
  { title: "AI-powered Decision Support", copy: "Context-aware guidance across steps, approvals, and edge cases." },
];

const NAV_LINKS = [
  { href: "#overview", label: "Overview" },
  { href: "#architecture", label: "Architecture" },
  { href: "#features", label: "Features" },
  { href: "#stack", label: "Stack" },
  { href: "#impact", label: "Impact" },
];

function FeatureIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M8 12.5l2.5 2.5L16 9" stroke="#4F46E5" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M6 3.5h8l4 4V20a1 1 0 01-1 1H6a1 1 0 01-1-1V4.5a1 1 0 011-1Z" stroke="#4F46E5" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M14 3.5V8h4" stroke="#4F46E5" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M8 12.5h8M8 16h5" stroke="#4F46E5" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function EngineIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path
        d="M9.5 2a3.5 3.5 0 00-3.5 3.5v.6A3 3 0 004 9v1a3 3 0 002 2.83V15a3.5 3.5 0 003.5 3.5M14.5 2A3.5 3.5 0 0118 5.5v.6A3 3 0 0120 9v1a3 3 0 01-2 2.83V15a3.5 3.5 0 01-3.5 3.5M12 5.5v13"
        stroke="#fff"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function AnswerIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path d="M4 5.5A1.5 1.5 0 015.5 4h13A1.5 1.5 0 0120 5.5v9a1.5 1.5 0 01-1.5 1.5H9l-4 3.5V16H5.5A1.5 1.5 0 014 14.5v-9Z" stroke="#4F46E5" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 9.5l2.2 2.2L16 6.5" stroke="#4F46E5" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DownArrow() {
  return (
    <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
      <path d="M8 1v15.5M8 16.5l-4.5-4.5M8 16.5l4.5-4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Reveal({ children, className = "", ...rest }) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setInView(true);
        });
      },
      { threshold: 0.15 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} className={`reveal${inView ? " in" : ""} ${className}`} {...rest}>
      {children}
    </div>
  );
}

export default function TelecomWorkflowNavigatorLanding() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const pipeRefs = useRef([]);
  useEffect(() => {
    const nodes = pipeRefs.current.filter(Boolean);
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const idx = nodes.indexOf(entry.target);
            setTimeout(() => entry.target.classList.add("active"), idx * 90);
          }
        });
      },
      { threshold: 0.5 }
    );
    nodes.forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, []);

  return (
    <div className="twn">
      <style>{CSS}</style>

      <header className={scrolled ? "scrolled" : ""}>
        <div className="wrap">
          <nav>
            <div className="brand">
              <div className="brand-mark"></div>
              <div className="brand-text">
                <span className="name">Telecom Workflow Navigator</span>
                <span className="tag">Operations Workflow Copilot</span>
              </div>
            </div>

            <div className="nav-links">
              {NAV_LINKS.map((link) => (
                <a key={link.href} href={link.href}>{link.label}</a>
              ))}
            </div>

            <div className="nav-right">
              <a href="/chat" className="btn btn-primary nav-cta">Open Navigator</a>
            </div>
          </nav>
        </div>
      </header>

      {/* HERO */}
      <section className="hero">
        <div className="wrap hero-grid" >
          <div>
            <div className="eyebrow">✦ Enterprise AI · RAG · Telecom Operations</div>
            <h1>
              Navigate Complex <span className="grad">Telecom Workflows</span> with AI
            </h1>
            <p className="lead">
              An enterprise-grade AI copilot that transforms complex telecom operational workflows into
              instant, conversational knowledge — reducing search time, improving process understanding,
              and enabling faster decision making.
            </p>
            <div className="hero-actions">
              <a href="/chat" className="btn btn-primary">Open Navigator</a>
              <a href="#overview" className="btn btn-ghost">Learn More</a>
            </div>

          </div>

          {/* HERO GRAPHIC v2 — shows what actually happens: real docs go in,
              a grounded, cited answer comes out. No abstract particle graph. */}
          <div className="hero-graphic">
            <div className="hg-badge">RAG · re-ranked & cited</div>

            <div className="hg-stage">
              <div className="hg-doc d2">
                <div className="fname">upgrade_workflow.md</div>
                <div className="bars"><span style={{ width: "80%" }}></span><span style={{ width: "55%" }}></span></div>
              </div>
              <div className="hg-doc d1">
                <div className="fname">tenancy_cancellation.md</div>
                <div className="bars"><span style={{ width: "90%" }}></span><span style={{ width: "60%" }}></span><span style={{ width: "70%" }}></span></div>
              </div>

              <svg className="hg-path" viewBox="0 0 500 460" preserveAspectRatio="none">
                <path id="hgPath" d="M150,130 C 260,160 300,260 340,320" stroke="rgba(255,255,255,0.18)" strokeWidth="1.6" fill="none" strokeDasharray="1 7" strokeLinecap="round" />
                <circle r="3.6" fill="#22D3EE">
                  <animateMotion dur="3s" repeatCount="indefinite" path="M150,130 C 260,160 300,260 340,320" />
                </circle>
              </svg>

              <div className="hg-answer">
                <div className="q">Q</div>
                <div className="qtext">Who approves RFI (B) for an Upgrade?</div>
                <div className="atext">The Customer approves RFI (B) once billing-stage inspection is raised by Sales.</div>
                <div className="cites">
                  <span className="cite">Upgrade Workflow · 0.91</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* PROJECT OVERVIEW */}
      <section className="overview" id="overview">
        <div className="wrap overview-grid">
          <Reveal>
            <div className="section-head">
              <div className="eyebrow">Project overview</div>
              <h2>Enterprise AI Assistant for Telecom Operations</h2>
              <p>
                Telecom Workflow Navigator converts lengthy telecom workflow documentation into an
                intelligent conversational assistant using Retrieval-Augmented Generation (RAG). Ask
                natural language questions, get grounded answers with citations across every indexed
                process — no more digging through PDFs to find the right step or approval.
              </p>
            </div>
          </Reveal>

          {/* OVERVIEW DIAGRAM v2 — a literal top-to-bottom flow instead of
              floating labels around decorative rings: scattered documents in,
              the engine in the middle, one confident cited answer out. */}
          <Reveal className="flow">
            <div className="flow-panel">
              <div className="ic"><DocIcon /></div>
              <div>
                <div className="tt">Unstructured Docs</div>
                <div className="ds">SOPs, approval chains, edge cases</div>
              </div>
            </div>
            <div className="flow-arrow"><DownArrow /></div>
            <div className="flow-panel core">
              <div className="ic"><EngineIcon /></div>
              <div>
                <div className="tt">RAG Engine</div>
                <div className="ds">Retrieve · re-rank · generate</div>
              </div>
            </div>
            <div className="flow-arrow"><DownArrow /></div>
            <div className="flow-panel">
              <div className="ic"><AnswerIcon /></div>
              <div>
                <div className="tt">Grounded Answer</div>
                <div className="ds">Cited, verifiable, instant</div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* RAG ARCHITECTURE */}
      <section className="pipeline" id="architecture">
        <div className="wrap">
          <Reveal className="section-head">
            <div className="eyebrow">RAG architecture</div>
            <h2>The RAG Pipeline, End-to-End</h2>
            <p>
              Each stage is engineered for grounded, accurate answers — from document ingestion to a
              re-ranked LLM response.
            </p>
          </Reveal>
          <div className="pipe-chain" style={{ padding: "10px 0px 0px 0px" }}>
            {PIPELINE_STAGES.map((stage, i) => (
              <div className="pipe-node" key={stage} ref={(el) => (pipeRefs.current[i] = el)}>
                {i > 0 && (
                  <div className="pipe-line">
                    <div className="pulse" style={{ animationDelay: `${(i - 1) * 0.3}s` }}></div>
                  </div>
                )}
                <div className="dot">{i + 1}</div>
                <div className="label">{stage}</div>
              </div>
            ))}
          </div>
          <Reveal className="pipeline-note">
            Documents are parsed, chunked with semantic awareness, and embedded into a FAISS vector
            store. Queries retrieve the most relevant chunks, which are then re-ranked by a
            cross-encoder before the LLM composes a grounded, citation-backed answer.
          </Reveal>
        </div>
      </section>

      {/* KEY FEATURES — previously defined (FEATURES array + CSS) but never rendered */}
      <section className="features" id="features">
        <div className="wrap">
          <Reveal className="section-head center">
            <div className="eyebrow">Key features</div>
            <h2>What It Actually Does</h2>
            <p>Every feature ties back to one goal: never make someone dig through a document manually again.</p>
          </Reveal>
          <div className="feature-grid">
            {FEATURES.map((f) => (
              <Reveal className="feature-card" key={f.title}>
                <div className="icon"><FeatureIcon /></div>
                <h3>{f.title}</h3>
                <p>{f.copy}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* TECH STACK */}
      <section className="stack" id="stack">
        <div className="wrap">
          <Reveal className="section-head">
            <div className="eyebrow">Under the hood</div>
            <h2>Behind the Intelligence</h2>
            <p>A carefully chosen stack for retrieval quality, latency, and long-term maintainability.</p>
          </Reveal>
          <div className="stack-grid">
            {STACK_ITEMS.map((item) => (
              <Reveal className="stack-card" key={item.name}>
                <div className="name">{item.name}</div>
                <div className="role">{item.role}</div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* BUSINESS IMPACT — previously defined (IMPACT_ITEMS array + CSS) but never rendered */}
      <section className="impact" id="impact">
        <div className="wrap">
          <Reveal className="section-head center">
            <div className="eyebrow">Business impact</div>
            <h2>Why This Matters Beyond the Demo</h2>
            <p>A working prototype is one thing — here's the operational case for it.</p>
          </Reveal>
          <div className="timeline-track">
            {IMPACT_ITEMS.map((item, i) => (
              <Reveal className={`t-item ${i % 2 === 0 ? "odd" : "even"}`} key={item.title}>
                {i % 2 === 0 && (
                  <div className="t-card">
                    <h3>{item.title}</h3>
                    <p>{item.copy}</p>
                  </div>
                )}
                <div className="spot"></div>
                {i % 2 !== 0 && (
                  <div className="t-card">
                    <h3>{item.title}</h3>
                    <p>{item.copy}</p>
                  </div>
                )}
                {i % 2 === 0 && <div className="t-hide"></div>}
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* OPEN NAVIGATOR CTA */}
      <section style={{ padding: "0px 0px 40px 0px" }}>
        <Reveal className="final-cta">
          <div className="eyebrow">Get started</div>
          <h2>Ready to Explore Telecom Workflows?</h2>
          <p>Start asking natural language questions and navigate telecom operations effortlessly.</p>
          <a href="/chat" className="btn btn-primary">Open Navigator</a>
        </Reveal>
      </section>
    </div>
  );
}