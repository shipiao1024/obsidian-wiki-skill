/* ============================================================
   Knowledge Graph — Clean, information-first design
   ============================================================ */
(function () {
  "use strict";

  const helpers = window.WikiGraphWashHelpers;
  if (!helpers) {
    console.error("[wiki] graph-wash-helpers.js is missing or failed to load");
    return;
  }
  const { truncateLabel, cardDims } = helpers;

  // ---------- Parse embedded data ----------
  const dataEl = document.getElementById("graph-data");
  let DATA;
  try {
    DATA = dataEl ? JSON.parse(dataEl.textContent) : {};
  } catch (_) {
    DATA = { meta: {}, nodes: [], edges: [], communities: [], contradictions: [], questions: [], insights: {} };
  }

  // ---------- SVG setup ----------
  const svg = d3.select("#canvas");
  const svgNode = svg.node();

  // ---------- State ----------
  const state = {
    selected: null,
    hover: null,
    nodes: [],
    links: [],
    byId: {},
    communities: [],
    insights: { bridgeNodes: [], isolatedNodes: [], contradictions: [], summary: [] },
    contradictions: [],
    questions: [],
    searchIndex: [],
    activeMode: "global",
    activeCommunityId: null,
    pathStep: 0,
  };

  // ---------- D3 layers ----------
  let simulation, zoomBehavior;
  const rootG = svg.append("g").attr("class", "root");
  const blobLayer = rootG.append("g").attr("class", "blob-layer");
  const edgeLayer = rootG.append("g").attr("class", "edge-group");
  const nodeLayer = rootG.append("g").attr("class", "node-layer");
  const commLabelLayer = rootG.append("g").attr("class", "comm-label-layer");

  // ---------- Data preparation ----------
  function prepareData() {
    state.nodes = (DATA.nodes || []).map((n, i) => Object.assign({}, n, { idx: i }));
    state.links = (DATA.edges || []).map(e => Object.assign({}, e, {
      source: e.source,
      target: e.target,
    }));
    state.communities = DATA.communities || [];
    state.contradictions = DATA.contradictions || [];
    state.questions = DATA.questions || [];

    // Normalize insights
    const raw = DATA.insights || {};
    state.insights = {
      bridgeNodes: Array.isArray(raw.bridgeNodes) ? raw.bridgeNodes : [],
      isolatedNodes: Array.isArray(raw.isolatedNodes) ? raw.isolatedNodes : [],
      contradictions: Array.isArray(raw.contradictions) ? raw.contradictions : [],
      summary: Array.isArray(raw.summary) ? raw.summary : [],
    };

    // Build lookup
    state.byId = {};
    state.nodes.forEach(n => { state.byId[n.id] = n; });

    // Build community map (id → { nodes, color, label })
    state.communityMap = {};
    state.nodes.forEach(n => {
      const c = n.community || "—";
      if (!state.communityMap[c]) {
        const commData = state.communities.find(cm => cm.label === c) || {};
        state.communityMap[c] = {
          id: c,
          label: c,
          color: n.communityColor || commData.color || "#8a8a8a",
          nodes: [],
        };
      }
      state.communityMap[c].nodes.push(n);
      n.commColor = state.communityMap[c].color;
    });

    // Search index
    state.searchIndex = state.nodes.map(n => ({
      node: n,
      haystack: `${(n.label || n.id || "").toLowerCase()}\n${(n.content || "").slice(0, 500).toLowerCase()}`,
    }));
  }

  // ---------- Node geometry ----------
  function nodeRadius(n) {
    return 12 + Math.sqrt(Math.max(n.degree || 0, 1)) * 4;
  }

  function nodeStrokeColor(n) {
    return n.typeColor || "#8a8a8a";
  }

  function communityColor(communityId) {
    const cm = state.communityMap[communityId];
    return cm ? cm.color : "#8a8a8a";
  }

  // ---------- Force simulation ----------
  function initSim() {
    const w = svgNode.clientWidth || 1000;
    const h = svgNode.clientHeight || 600;
    const cx = w / 2, cy = h / 2;
    const R = Math.min(w, h) * 0.3;

    state.nodes.forEach((n, i) => {
      const a = (i / state.nodes.length) * Math.PI * 2;
      n.x = cx + Math.cos(a) * R;
      n.y = cy + Math.sin(a) * R;
    });

    simulation = d3.forceSimulation(state.nodes)
      .force("link", d3.forceLink(state.links).id(d => d.id)
        .distance(l => {
          const src = state.byId[l.source.id || l.source];
          const tgt = state.byId[l.target.id || l.target];
          const sameComm = src && tgt && src.community === tgt.community;
          return sameComm ? 120 : 200;
        })
        .strength(0.4))
      .force("charge", d3.forceManyBody().strength(-500).distanceMax(800))
      .force("x", d3.forceX(cx).strength(0.05))
      .force("y", d3.forceY(cy).strength(0.05))
      .force("collide", d3.forceCollide().radius(d => {
        const dim = cardDims(d);
        return Math.max(dim.w, dim.h) * 0.5 + 12;
      }).strength(0.9))
      .force("comm", communityForce(0.04))
      .alphaDecay(0.025)
      .velocityDecay(0.5);

    simulation.on("tick", tick);

    for (let i = 0; i < 80; i++) simulation.tick();
    tick();

    let fitted = false;
    simulation.on("tick.fit", () => {
      if (!fitted && simulation.alpha() < 0.5) {
        fitted = true;
        document.getElementById("loading").setAttribute("data-hide", "1");
        setTimeout(() => {
          fitToView();
          document.getElementById("loading").style.display = "none";
        }, 150);
      }
    });
    simulation.on("end", () => {
      document.getElementById("loading").setAttribute("data-hide", "1");
      document.getElementById("loading").style.display = "none";
      if (!fitted) { fitted = true; fitToView(); }
    });
    setTimeout(() => {
      if (!fitted) {
        fitted = true;
        document.getElementById("loading").setAttribute("data-hide", "1");
        document.getElementById("loading").style.display = "none";
        fitToView();
      }
    }, 3000);
  }

  function communityForce(strength) {
    let nodes = [];
    function force(alpha) {
      const cent = {};
      nodes.forEach(n => {
        const c = n.community || "—";
        if (!cent[c]) cent[c] = { x: 0, y: 0, n: 0 };
        cent[c].x += n.x; cent[c].y += n.y; cent[c].n++;
      });
      Object.keys(cent).forEach(k => {
        cent[k].x /= cent[k].n; cent[k].y /= cent[k].n;
      });
      nodes.forEach(n => {
        const c = n.community || "—";
        const t = cent[c];
        n.vx += (t.x - n.x) * strength * alpha * 4;
        n.vy += (t.y - n.y) * strength * alpha * 4;
      });
    }
    force.initialize = (n) => { nodes = n; };
    return force;
  }

  // ---------- Tick: update positions ----------
  function tick() {
    // Edges
    edgeLayer.selectAll("path.edge").each(function (d) {
      const s = d.source, t = d.target;
      if (s.x == null || t.x == null) return;
      d3.select(this).attr("d", `M${s.x},${s.y} L${t.x},${t.y}`);
    });

    // Nodes
    nodeLayer.selectAll("g.node-group")
      .attr("transform", d => `translate(${d.x},${d.y})`);

    if (simulation.alpha() < 0.15) renderBlobs();
  }

  // ---------- Render edges ----------
  function renderEdges() {
    const vis = state.links;

    const paths = edgeLayer.selectAll("path.edge")
      .data(vis, d => d.id);

    paths.exit().remove();

    paths.enter().append("path")
      .attr("class", "edge")
      .attr("data-type", d => d.type || "mentions")
      .style("stroke", d => d.color || "#aaaaaa")
      .style("stroke-width", d => d.width || 1)
      .style("stroke-dasharray", d => d.dash ? "6 4" : "none")
      .style("opacity", 0.5)
      .merge(paths)
      .attr("data-type", d => d.type || "mentions")
      .style("stroke", d => d.color || "#aaaaaa")
      .style("stroke-width", d => d.width || 1)
      .style("stroke-dasharray", d => d.dash ? "6 4" : "none");
  }

  // ---------- Render nodes ----------
  function renderNodes() {
    const g = nodeLayer.selectAll("g.node-group")
      .data(state.nodes, d => d.id);
    g.exit().remove();

    const enter = g.enter().append("g")
      .attr("class", "node-group")
      .attr("data-id", d => d.id)
      .attr("data-node-class", d => d.nodeClass || "detail")
      .on("mouseenter", (ev, d) => { state.hover = d.id; applyHighlight(); })
      .on("mouseleave", () => { state.hover = null; applyHighlight(); })
      .on("click", (ev, d) => { ev.stopPropagation(); selectNode(d.id, true); })
      .call(d3.drag()
        .on("start", (ev, d) => { if (!ev.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag",  (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
        .on("end",   (ev, d) => { if (!ev.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    // Card: rect + type badge + label
    enter.each(function (d) {
      const gg = d3.select(this);
      const dim = cardDims(d);

      // Question nodes: diamond shape
      if (d.type === "question") {
        const r = 14;
        gg.append("polygon")
          .attr("class", "node-diamond")
          .attr("points", `0,${-r} ${r},0 0,${r} ${-r},0`)
          .style("stroke", d.typeColor || "#6a6a8a")
          .style("fill", "var(--bg-card)");
      } else {
        gg.append("rect")
          .attr("class", "node-rect")
          .attr("x", -dim.w / 2)
          .attr("y", -dim.h / 2)
          .attr("width", dim.w)
          .attr("height", dim.h)
          .style("stroke", d.typeColor || "#8a8a8a");
      }

      // Type badge (small colored circle)
      gg.append("circle")
        .attr("class", "node-type-badge-bg")
        .attr("cx", d.type === "question" ? 0 : -dim.w / 2 + 8)
        .attr("cy", d.type === "question" ? 0 : -dim.h / 2 + 8)
        .attr("r", 4)
        .style("fill", d.typeColor || "#8a8a8a");

      // Label
      const label = d.label || d.id;
      const { text: displayLabel } = truncateLabel(label, d.type === "question" ? 100 : 160);
      if (d.type === "question") {
        gg.append("text")
          .attr("class", "node-label")
          .attr("text-anchor", "middle")
          .attr("dy", "0.35em")
          .style("font-size", "11px")
          .text(displayLabel);
      } else {
        gg.append("text")
          .attr("class", "node-label")
          .attr("text-anchor", "middle")
          .attr("dy", "0.35em")
          .text(displayLabel);
      }

      if (label.length > displayLabel.length) {
        gg.append("title").text(label);
      }
    });
  }

  // ---------- Community blobs ----------
  function renderBlobs() {
    blobLayer.selectAll("*").remove();
    commLabelLayer.selectAll("*").remove();

    const mode = state.activeMode;

    Object.values(state.communityMap).forEach(c => {
      if (c.nodes.length < 2) return;

      const isActive = mode === "community" && state.activeCommunityId === c.id;
      const isGlobal = mode === "global";

      const padding = 40;
      const pts = c.nodes.filter(n => n.x != null).map(n => {
        const dim = cardDims(n);
        const r = Math.max(dim.w, dim.h) * 0.5 + padding;
        const out = [];
        for (let i = 0; i < 10; i++) {
          const a = (i / 10) * Math.PI * 2;
          out.push([n.x + Math.cos(a) * r, n.y + Math.sin(a) * r]);
        }
        return out;
      }).flat();

      if (pts.length < 3) return;
      const hull = d3.polygonHull(pts);
      if (!hull) return;

      const line = d3.line().curve(d3.curveCatmullRomClosed.alpha(0.9));
      const pathD = line(hull);

      // Opacity varies by mode
      let fillAlpha = 0.04;
      let strokeAlpha = 0.15;
      if (isGlobal) { fillAlpha = 0.06; strokeAlpha = 0.25; }
      if (isActive) { fillAlpha = 0.10; strokeAlpha = 0.35; }
      if (mode === "community" && !isActive) { fillAlpha = 0.02; strokeAlpha = 0.06; }
      if (mode === "path") { fillAlpha = 0.02; strokeAlpha = 0.08; }

      blobLayer.append("path")
        .attr("class", "community-blob")
        .attr("d", pathD)
        .style("fill", hexToRgba(c.color, fillAlpha))
        .style("stroke", hexToRgba(c.color, strokeAlpha));

      const centroid = d3.polygonCentroid(hull);
      const topMost = hull.reduce((a, b) => a[1] < b[1] ? a : b);
      const labelAlpha = isGlobal ? 0.8 : (isActive ? 0.9 : (mode === "path" ? 0.3 : 0.5));
      commLabelLayer.append("text")
        .attr("class", "community-label")
        .attr("x", centroid[0])
        .attr("y", topMost[1] - 8)
        .attr("text-anchor", "middle")
        .style("fill", hexToRgba(c.color, labelAlpha))
        .style("font-size", isGlobal ? "15px" : "13px")
        .text(c.label);
    });
  }

  function hexToRgba(hex, a) {
    const h = hex.replace("#", "");
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return `rgba(${r},${g},${b},${a})`;
  }

  // ---------- Zoom / pan ----------
  function setupZoom() {
    zoomBehavior = d3.zoom()
      .scaleExtent([0.25, 3])
      .on("zoom", (ev) => {
        rootG.attr("transform", ev.transform);
      });
    svg.call(zoomBehavior);
  }

  function fitToView() {
    if (!state.nodes.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    state.nodes.forEach(n => {
      const dim = cardDims(n);
      const r = Math.max(dim.w, dim.h) * 0.5 + 20;
      if (n.x - r < minX) minX = n.x - r;
      if (n.y - r < minY) minY = n.y - r;
      if (n.x + r > maxX) maxX = n.x + r;
      if (n.y + r > maxY) maxY = n.y + r;
    });
    const pad = 60;
    const bw = maxX - minX + pad * 2;
    const bh = maxY - minY + pad * 2;
    const rect = svgNode.getBoundingClientRect();
    const k = Math.min(rect.width / bw, rect.height / bh, 1.3);
    const tx = rect.width / 2 - ((minX + maxX) / 2) * k;
    const ty = rect.height / 2 - ((minY + maxY) / 2) * k;
    svg.transition().duration(600).call(
      zoomBehavior.transform,
      d3.zoomIdentity.translate(tx, ty).scale(k)
    );
  }

  // ---------- Highlight on hover/select ----------
  function applyHighlight() {
    const focus = state.selected || state.hover;
    if (!focus) {
      rootG.classed("graph-dim", false);
      nodeLayer.selectAll("g.node-group").classed("focus", false).classed("neighbor", false);
      edgeLayer.selectAll("path.edge").classed("edge--hi", false).classed("edge--dim", false);
      return;
    }

    const neighbors = new Set([focus]);
    state.links.forEach(l => {
      const s = l.source.id || l.source;
      const t = l.target.id || l.target;
      if (s === focus) neighbors.add(t);
      if (t === focus) neighbors.add(s);
    });

    rootG.classed("graph-dim", true);
    nodeLayer.selectAll("g.node-group")
      .classed("focus", d => d.id === focus)
      .classed("neighbor", d => neighbors.has(d.id) && d.id !== focus);
    edgeLayer.selectAll("path.edge")
      .classed("edge--hi", d => {
        const s = d.source.id || d.source;
        const t = d.target.id || d.target;
        return s === focus || t === focus;
      })
      .classed("edge--dim", d => {
        const s = d.source.id || d.source;
        const t = d.target.id || d.target;
        return s !== focus && t !== focus;
      });

    nodeLayer.selectAll("g.node-group")
      .attr("data-selected", d => d.id === state.selected ? "1" : "0")
      .attr("data-hover", d => d.id === state.hover ? "1" : "0");
  }

  // ---------- Selection + drawer ----------
  function selectNode(id, openDrawer) {
    state.selected = id;
    applyHighlight();
    pulseNode(id);
    renderNavPanel();
    if (openDrawer) openDetailDrawer(id);
  }

  function pulseNode(id) {
    const g = nodeLayer.select(`g.node-group[data-id="${cssEscape(id)}"]`);
    g.classed("pulse", false);
    void g.node()?.getBBox();
    g.classed("pulse", true);
    setTimeout(() => g.classed("pulse", false), 1300);
  }

  function cssEscape(s) { return String(s).replace(/"/g, '\\"'); }

  function openDetailDrawer(id) {
    const n = state.byId[id];
    if (!n) return;

    document.getElementById("app").classList.add("drawer-open");
    document.getElementById("drawer").setAttribute("aria-hidden", "false");

    // Kicker: type label
    document.getElementById("dr-kicker").textContent = n.typeLabel || n.type || "—";

    // Title
    document.getElementById("dr-title").textContent = n.label || n.id;

    // Community + degree
    const commEl = document.getElementById("dr-community");
    if (n.community) {
      commEl.textContent = n.community;
      commEl.hidden = false;
    } else {
      commEl.hidden = true;
    }
    document.getElementById("dr-degree").textContent = `${n.degree || 0} 条关联`;

    // Body: structured content by type
    const body = document.getElementById("dr-body");
    body.innerHTML = "";
    body.scrollTop = 0;

    const content = n.content || "";
    if (content) {
      // Split by newlines to create sections
      const parts = content.split("\n").filter(p => p.trim());
      parts.forEach(part => {
        if (part.includes("：")) {
          const sepIdx = part.indexOf("：");
          const sectionTitle = part.substring(0, sepIdx);
          const sectionBody = part.substring(sepIdx + 1);
          const h2 = document.createElement("h2");
          h2.textContent = sectionTitle;
          body.appendChild(h2);
          const p = document.createElement("p");
          p.textContent = sectionBody;
          body.appendChild(p);
        } else {
          const p = document.createElement("p");
          p.textContent = part;
          body.appendChild(p);
        }
      });
    } else {
      const p = document.createElement("p");
      p.style.color = "var(--ink-faint)";
      p.textContent = "暂无摘要内容";
      body.appendChild(p);
    }

    // Source path hint
    if (n.source_path) {
      const pathEl = document.createElement("div");
      pathEl.style.cssText = "margin-top:12px; font-family:var(--font-mono); font-size:11px; color:var(--ink-faint);";
      pathEl.textContent = n.source_path;
      body.appendChild(pathEl);
    }

    // Neighbors
    const neighbors = [];
    state.links.forEach(l => {
      const s = l.source.id || l.source;
      const t = l.target.id || l.target;
      if (s === id) neighbors.push({ other: state.byId[t], type: l.type, color: l.color });
      else if (t === id) neighbors.push({ other: state.byId[s], type: l.type, color: l.color });
    });

    const nb = document.getElementById("nb-list");
    nb.innerHTML = "";
    if (!neighbors.length || neighbors.every(o => !o.other)) {
      const empty = document.createElement("div");
      empty.style.cssText = "color:var(--ink-faint); padding:8px; font-size:12px;";
      empty.textContent = "（孤立节点）";
      nb.appendChild(empty);
    } else {
      neighbors.forEach(o => {
        if (!o.other) return;
        const el = document.createElement("div");
        el.className = "nb-item";
        const typeLabel = o.type || "mentions";
        el.innerHTML = `
          <span class="nb-item__type" style="background:${o.other.typeColor || '#8a8a8a'}"></span>
          <span class="nb-item__name">${escapeHtml(o.other.label || o.other.id)}</span>
          <span class="nb-item__rel">${escapeHtml(typeLabel)}</span>
        `;
        el.addEventListener("click", () => {
          selectNode(o.other.id, true);
          svg.transition().duration(450).call(zoomBehavior.translateTo, o.other.x, o.other.y);
        });
        nb.appendChild(el);
      });
    }
  }

  function closeDrawer() {
    document.getElementById("app").classList.remove("drawer-open");
    document.getElementById("drawer").setAttribute("aria-hidden", "true");
    state.selected = null;
    applyHighlight();
    renderNavPanel();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[c]);
  }

  // ---------- Toast ----------
  let toastTimer;
  function toast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.setAttribute("data-show", "1");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.setAttribute("data-show", "0"), 1800);
  }

  function focusNode(nodeId, openDrawer) {
    const hit = state.byId[nodeId];
    if (!hit) return;
    selectNode(hit.id, openDrawer !== false);
    svg.transition().duration(450).call(zoomBehavior.translateTo, hit.x, hit.y);
  }

  // ---------- Nav panel rendering ----------
  function renderNavPanel() {
    const mode = state.activeMode;

    // Communities — show in global & community modes
    const navCommunities = document.getElementById("nav-communities");
    if (navCommunities) {
      navCommunities.innerHTML = "";
      const showCommunities = (mode === "global" || mode === "community");
      if (!showCommunities) {
        navCommunities.innerHTML = '<div class="nav-empty">切换到全景或聚焦模式查看</div>';
      } else {
        const sorted = Object.values(state.communityMap).sort((a, b) => b.nodes.length - a.nodes.length);
        if (!sorted.length) {
          navCommunities.innerHTML = '<div class="nav-empty">暂无社区信息</div>';
        } else {
          sorted.forEach(c => {
            const el = document.createElement("div");
            el.className = "nav-item nav-item--accent";
            el.setAttribute("data-on", state.activeCommunityId === c.id ? "1" : "0");
            el.innerHTML = `
              <div class="nav-item__title">${escapeHtml(c.label)}</div>
              <div class="nav-item__meta">${c.nodes.length} 个节点</div>
            `;
            el.addEventListener("click", () => {
              state.activeCommunityId = c.id;
              setLearningMode("community");
              const best = c.nodes.reduce((a, b) => (a.degree || 0) >= (b.degree || 0) ? a : b);
              focusNode(best.id);
            });
            navCommunities.appendChild(el);
          });
        }
      }
    }

    // Bridge nodes — show in global mode only
    const navBridges = document.getElementById("nav-bridges");
    if (navBridges) {
      navBridges.innerHTML = "";
      if (mode !== "global") {
        navBridges.innerHTML = '<div class="nav-empty">切换到全景模式查看</div>';
      } else {
        const bridges = state.insights.bridgeNodes || [];
        if (!bridges.length) {
          navBridges.innerHTML = '<div class="nav-empty">暂无桥梁节点</div>';
        } else {
          bridges.forEach(b => {
            const node = state.byId[b.id];
            if (!node) return;
            const el = document.createElement("div");
            el.className = "nav-item nav-item--accent";
            el.innerHTML = `
              <div class="nav-item__title">${escapeHtml(node.label || node.id)}</div>
              <div class="nav-item__meta">连接 ${b.communityCount || "?"} 个社区</div>
            `;
            el.addEventListener("click", () => focusNode(b.id));
            navBridges.appendChild(el);
          });
        }
      }
    }

    // Isolated nodes — show in global mode only
    const navIsolated = document.getElementById("nav-isolated");
    if (navIsolated) {
      navIsolated.innerHTML = "";
      if (mode !== "global") {
        navIsolated.innerHTML = '<div class="nav-empty">切换到全景模式查看</div>';
      } else {
        const isolated = state.insights.isolatedNodes || [];
        if (!isolated.length) {
          navIsolated.innerHTML = '<div class="nav-empty">暂无孤立节点</div>';
        } else {
          isolated.forEach(iso => {
            const node = state.byId[iso.id];
            if (!node) return;
            const el = document.createElement("div");
            el.className = "nav-item nav-item--warning";
            el.innerHTML = `
              <div class="nav-item__title">${escapeHtml(node.label || node.id)}</div>
              <div class="nav-item__meta">仅 1 个连接</div>
            `;
            el.addEventListener("click", () => focusNode(iso.id));
            navIsolated.appendChild(el);
          });
        }
      }
    }

    // Contradictions — always visible, most important signal
    const navContradictions = document.getElementById("nav-contradictions");
    if (navContradictions) {
      navContradictions.innerHTML = "";
      const contrad = state.contradictions || [];
      if (!contrad.length) {
        navContradictions.innerHTML = '<div class="nav-empty">暂无矛盾关系</div>';
      } else {
        contrad.forEach(c => {
          const srcNode = state.byId[c.source];
          const tgtNode = state.byId[c.target];
          if (!srcNode || !tgtNode) return;
          const el = document.createElement("div");
          el.className = "nav-item nav-item--danger";
          el.innerHTML = `
            <div class="nav-item__title">${escapeHtml(srcNode.label || c.source)}</div>
            <div class="nav-item__meta">反驳 ← ${escapeHtml(tgtNode.label || c.target)}</div>
          `;
          el.addEventListener("click", () => {
            focusNode(c.source);
            setTimeout(() => {
              selectNode(c.source, true);
            }, 100);
          });
          navContradictions.appendChild(el);
        });
      }
    }

    // Questions — show in community & path modes
    const navQuestions = document.getElementById("nav-questions");
    if (navQuestions) {
      navQuestions.innerHTML = "";
      if (mode === "global") {
        navQuestions.innerHTML = '<div class="nav-empty">切换到聚焦或起点模式查看</div>';
      } else {
        const questions = state.questions || [];
        if (!questions.length) {
          navQuestions.innerHTML = '<div class="nav-empty">暂无开放问题</div>';
        } else {
          questions.forEach(q => {
            const node = state.byId[q.id];
            const el = document.createElement("div");
            el.className = "nav-item nav-item--accent";
            el.innerHTML = `
              <div class="nav-item__title">${escapeHtml(q.title || q.id)}</div>
              <div class="nav-item__meta">${q.status === "partial" ? "部分回答" : "开放"}</div>
            `;
            el.addEventListener("click", () => {
              if (node) focusNode(q.id);
            });
            navQuestions.appendChild(el);
          });
        }
      }
    }

    // Learning path — show in path mode
    const navPath = document.getElementById("nav-path");
    if (navPath) {
      navPath.innerHTML = "";
      const pathData = (DATA.learning && DATA.learning.path) || [];
      if (mode !== "path") {
        navPath.innerHTML = '<div class="nav-empty">切换到起点模式查看</div>';
      } else if (!pathData.length) {
        navPath.innerHTML = '<div class="nav-empty">暂无学习路径</div>';
      } else {
        pathData.forEach((step, i) => {
          const el = document.createElement("div");
          el.className = "nav-item nav-item--path-step";
          if (i <= state.pathStep) {
            el.style.background = "var(--bg-card)";
            el.style.borderColor = "var(--accent)";
          }
          el.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="path-step-number">${i + 1}</span>
              <div>
                <div class="nav-item__title">${escapeHtml(step.label || step.id)}</div>
                <div class="nav-item__meta">${escapeHtml(step.reason || "")}</div>
              </div>
            </div>
          `;
          el.addEventListener("click", () => {
            state.pathStep = i;
            applyModeVisuals();
            focusNode(step.id, true);
            renderNavPanel();
          });
          navPath.appendChild(el);
        });
        // Next step button if not at end
        if (state.pathStep < pathData.length - 1) {
          const nextBtn = document.createElement("div");
          nextBtn.className = "nav-item";
          nextBtn.style.borderLeft = "3px solid var(--accent)";
          nextBtn.style.cursor = "pointer";
          nextBtn.innerHTML = `
            <div class="nav-item__title" style="color:var(--accent);">下一步 →</div>
            <div class="nav-item__meta">${escapeHtml(pathData[state.pathStep + 1].label || "")}</div>
          `;
          nextBtn.addEventListener("click", () => {
            state.pathStep = Math.min(state.pathStep + 1, pathData.length - 1);
            applyModeVisuals();
            focusNode(pathData[state.pathStep].id, true);
            renderNavPanel();
          });
          navPath.appendChild(nextBtn);
        }
      }
    }
  }

  // ---------- Learning mode ----------
  function setLearningMode(mode) {
    state.activeMode = mode;

    // Update mode buttons
    document.querySelectorAll("#mode-switch .mode-btn").forEach(btn => {
      btn.setAttribute("data-on", btn.dataset.mode === mode ? "1" : "0");
    });

    // Apply visual treatment
    applyModeVisuals();
    renderNavPanel();
    updateFooter();

    if (mode === "global") {
      fitToView();
    } else {
      setTimeout(() => fitProminentToView(), 150);
    }
  }

  function applyModeVisuals() {
    const mode = state.activeMode;

    // Remove all mode classes first
    svgNode.classList.remove("mode-global", "mode-community", "mode-path");

    // Clear all per-node/per-edge mode attributes
    nodeLayer.selectAll("g.node-group")
      .classed("on-path", false)
      .classed("on-path-neighbor", false)
      .classed("in-active-community", false)
      .style("display", null);

    edgeLayer.selectAll("path.edge")
      .classed("on-path", false)
      .classed("in-active-community", false)
      .style("display", null);

    if (mode === "global") {
      svgNode.classList.add("mode-global");
      // Global: all nodes visible, skeleton prominent, detail subdued
      // CSS handles opacity via .mode-global selectors

    } else if (mode === "community" && state.activeCommunityId) {
      svgNode.classList.add("mode-community");
      // Community: mark nodes in active community
      const cm = state.communityMap[state.activeCommunityId];
      if (cm) {
        const communityNodeIds = new Set(cm.nodes.map(n => n.id));
        nodeLayer.selectAll("g.node-group").each(function (d) {
          d3.select(this).classed("in-active-community", communityNodeIds.has(d.id));
        });
        edgeLayer.selectAll("path.edge").each(function (d) {
          const s = d.source.id || d.source;
          const t = d.target.id || d.target;
          d3.select(this).classed("in-active-community",
            communityNodeIds.has(s) || communityNodeIds.has(t));
        });
      }

    } else if (mode === "path") {
      svgNode.classList.add("mode-path");
      // Path: highlight nodes up to current step + their neighbors
      const pathData = (DATA.learning && DATA.learning.path) || [];
      if (!pathData.length || state.pathStep >= pathData.length) return;

      const onPathIds = new Set();
      const neighborIds = new Set();

      for (let i = 0; i <= state.pathStep; i++) {
        const stepId = pathData[i].id;
        onPathIds.add(stepId);
        state.links.forEach(l => {
          const s = l.source.id || l.source;
          const t = l.target.id || l.target;
          if (s === stepId && !onPathIds.has(t)) neighborIds.add(t);
          if (t === stepId && !onPathIds.has(s)) neighborIds.add(s);
        });
      }

      nodeLayer.selectAll("g.node-group").each(function (d) {
        const el = d3.select(this);
        el.classed("on-path", onPathIds.has(d.id));
        el.classed("on-path-neighbor", neighborIds.has(d.id) && !onPathIds.has(d.id));
      });

      edgeLayer.selectAll("path.edge").each(function (d) {
        const s = d.source.id || d.source;
        const t = d.target.id || d.target;
        d3.select(this).classed("on-path", onPathIds.has(s) && onPathIds.has(t));
      });
    }

    // Re-render community blobs after mode change
    renderBlobs();
  }

  function fitProminentToView() {
    // Fit view to the nodes that are visually prominent in the current mode
    const mode = state.activeMode;
    let prominent = [];

    if (mode === "community" && state.activeCommunityId) {
      const cm = state.communityMap[state.activeCommunityId];
      if (cm) prominent = cm.nodes;
    } else if (mode === "path") {
      const pathData = (DATA.learning && DATA.learning.path) || [];
      const onPathIds = new Set();
      for (let i = 0; i <= state.pathStep && i < pathData.length; i++) {
        onPathIds.add(pathData[i].id);
      }
      prominent = state.nodes.filter(n => onPathIds.has(n.id));
    }

    if (!prominent.length) prominent = state.nodes;
    if (!prominent.length) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    prominent.forEach(n => {
      const dim = cardDims(n);
      const r = Math.max(dim.w, dim.h) * 0.5 + 20;
      if (n.x - r < minX) minX = n.x - r;
      if (n.y - r < minY) minY = n.y - r;
      if (n.x + r > maxX) maxX = n.x + r;
      if (n.y + r > maxY) maxY = n.y + r;
    });
    const pad = 60;
    const bw = maxX - minX + pad * 2;
    const bh = maxY - minY + pad * 2;
    const rect = svgNode.getBoundingClientRect();
    const k = Math.min(rect.width / bw, rect.height / bh, 1.3);
    const tx = rect.width / 2 - ((minX + maxX) / 2) * k;
    const ty = rect.height / 2 - ((minY + maxY) / 2) * k;
    svg.transition().duration(600).call(
      zoomBehavior.transform,
      d3.zoomIdentity.translate(tx, ty).scale(k)
    );
  }

  // ---------- Search ----------
  function setupSearch() {
    const input = document.getElementById("search");
    const dd = document.getElementById("search-dropdown");
    let activeIdx = -1;
    let results = [];

    function render() {
      if (!results.length) {
        dd.innerHTML = '<div style="padding:10px;color:var(--ink-faint);font-size:12px;">无匹配</div>';
        dd.setAttribute("data-open", "1");
        return;
      }
      dd.innerHTML = "";
      results.slice(0, 10).forEach((n, i) => {
        const el = document.createElement("div");
        el.className = "search__item";
        if (i === activeIdx) el.setAttribute("data-active", "1");
        el.innerHTML = `
          <span class="type-dot" style="background:${n.typeColor || '#8a8a8a'}"></span>
          <span class="name">${escapeHtml(n.label || n.id)}</span>
          <span class="meta">${n.typeLabel || n.type || ""}</span>
        `;
        el.addEventListener("click", () => {
          input.value = n.label || n.id;
          dd.setAttribute("data-open", "0");
          selectNode(n.id, true);
          svg.transition().duration(450).call(zoomBehavior.translateTo, n.x, n.y);
        });
        dd.appendChild(el);
      });
      dd.setAttribute("data-open", "1");
    }

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { dd.setAttribute("data-open", "0"); return; }
      results = state.searchIndex
        .filter(entry => entry.haystack.includes(q))
        .map(entry => entry.node);
      activeIdx = 0;
      render();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); activeIdx = Math.min(results.length - 1, activeIdx + 1); render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); activeIdx = Math.max(0, activeIdx - 1); render(); }
      else if (e.key === "Enter") {
        e.preventDefault();
        if (results[activeIdx]) {
          const n = results[activeIdx];
          input.value = n.label || n.id;
          dd.setAttribute("data-open", "0");
          selectNode(n.id, true);
          svg.transition().duration(450).call(zoomBehavior.translateTo, n.x, n.y);
        }
      } else if (e.key === "Escape") {
        input.value = "";
        dd.setAttribute("data-open", "0");
      }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".search")) dd.setAttribute("data-open", "0");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== input) {
        const tag = document.activeElement.tagName;
        if (tag !== "INPUT" && tag !== "TEXTAREA") {
          e.preventDefault();
          input.focus();
          input.select();
        }
      } else if (e.key === "Escape") {
        if (document.getElementById("app").classList.contains("drawer-open")) closeDrawer();
      }
    });
  }

  // ---------- Canvas click (close drawer) ----------
  svg.on("click", () => {
    if (state.selected) closeDrawer();
  });

  // ---------- Zoom buttons ----------
  document.getElementById("btn-fit").addEventListener("click", fitToView);

  document.getElementById("dr-close").addEventListener("click", closeDrawer);

  // ---------- Footer ----------
  function updateFooter() {
    document.getElementById("n-nodes").textContent = state.nodes.length;
    document.getElementById("n-edges").textContent = state.links.length;
    document.getElementById("n-date").textContent = DATA.meta ? DATA.meta.build_date : "—";

    const modeLabels = { global: "全景", community: "聚焦", path: "起点" };
    const modeLabel = modeLabels[state.activeMode] || state.activeMode;

    document.getElementById("foot-shown").textContent = state.nodes.length;
    document.getElementById("foot-total").textContent = state.nodes.length;
    document.getElementById("foot-communities").textContent = Object.keys(state.communityMap).length;

    // Growth indicator
    const growthEl = document.getElementById("footer-growth");
    if (growthEl && DATA.meta) {
      const total = DATA.meta.total_nodes || 0;
      const edges = DATA.meta.total_edges || 0;
      const contrad = DATA.meta.total_contradictions || 0;
      const questions = DATA.meta.total_questions || 0;

      let text = `${modeLabel} · ${total} 节点 · ${edges} 关联`;
      if (contrad) text += ` · ${contrad} 矛盾`;
      if (questions) text += ` · ${questions} 问题`;

      if (state.activeMode === "path") {
        const pathData = (DATA.learning && DATA.learning.path) || [];
        text += ` · 步骤 ${state.pathStep + 1}/${pathData.length}`;
      }

      growthEl.textContent = text;
    }
  }

  // ---------- Resize ----------
  window.addEventListener("resize", () => {
    if (simulation) {
      simulation.force("center", d3.forceCenter(svgNode.clientWidth / 2, svgNode.clientHeight / 2).strength(0.05));
      simulation.alpha(0.2).restart();
    }
  });

  // ---------- Boot ----------
  prepareData();
  document.getElementById("wiki-title").textContent = DATA.meta ? DATA.meta.wiki_title : "Knowledge Base";
  setupZoom();
  renderEdges();
  renderNodes();
  initSim();
  setupSearch();
  renderNavPanel();
  updateFooter();

  // Mode switch buttons
  document.querySelectorAll("#mode-switch .mode-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      setLearningMode(btn.dataset.mode);
    });
  });

  // Bootstrap: start in "global" mode (map overview first)
  setTimeout(() => {
    setLearningMode("global");
  }, 600);
})();
